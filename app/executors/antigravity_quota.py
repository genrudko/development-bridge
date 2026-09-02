from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True, slots=True)
class QuotaSnapshot:
    remaining_fraction: float
    reset_time: datetime | None
    model: str | None
    bucket: str


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _model_name(payload: dict[str, object]) -> str | None:
    model = payload.get("model")
    if not isinstance(model, dict):
        return None
    for key in ("display_name", "id"):
        value = model.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _valid_buckets(payload: dict[str, object]) -> list[tuple[str, float, datetime | None]]:
    quota = payload.get("quota")
    if not isinstance(quota, dict):
        return []
    result: list[tuple[str, float, datetime | None]] = []
    observed_at = _parse_time(payload.get("observed_at"))
    for name, raw in quota.items():
        if not isinstance(name, str) or not isinstance(raw, dict):
            continue
        remaining = raw.get("remaining_fraction")
        if isinstance(remaining, bool) or not isinstance(remaining, (int, float)):
            continue
        remaining = float(remaining)
        if not math.isfinite(remaining) or not 0 <= remaining <= 1:
            continue
        reset_time = _parse_time(raw.get("reset_time"))
        if reset_time is None and observed_at is not None:
            seconds = raw.get("reset_in_seconds")
            if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and seconds >= 0:
                reset_time = observed_at + timedelta(seconds=float(seconds))
        result.append((name, remaining, reset_time))
    return result


def _limiting_bucket(payload: dict[str, object]) -> tuple[str, float, datetime | None] | None:
    buckets = _valid_buckets(payload)
    if not buckets:
        return None
    model = (_model_name(payload) or "").lower()
    if "gemini" in model:
        matching = [item for item in buckets if item[0].lower().startswith("gemini")]
        if matching:
            buckets = matching
    return min(buckets, key=lambda item: item[1])


def _atomic_json_write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def capture_statusline_payload(payload: dict[str, object], cache_path: Path, *, now: datetime | None = None) -> str:
    observed = (now or _utc_now()).astimezone(UTC)
    sanitized: dict[str, object] = {
        "observed_at": observed.isoformat(),
        "model": payload.get("model"),
        "plan_tier": payload.get("plan_tier"),
        "quota": payload.get("quota"),
    }
    _atomic_json_write(cache_path, sanitized)
    limiting = _limiting_bucket(sanitized)
    if limiting is None:
        return "AG quota ?"
    _, remaining, reset_time = limiting
    text = f"AG {remaining * 100:.0f}%"
    if reset_time is not None:
        seconds = max(0, int((reset_time - observed).total_seconds()))
        hours, remainder = divmod(seconds, 3600)
        minutes = remainder // 60
        text += f" · {hours}h{minutes:02d}m"
    return text


def load_quota_snapshot(cache_path: Path, *, max_age_seconds: float, now: datetime | None = None) -> QuotaSnapshot | None:
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    observed_at = _parse_time(payload.get("observed_at"))
    current = (now or _utc_now()).astimezone(UTC)
    if observed_at is None:
        return None
    age = (current - observed_at).total_seconds()
    if age < -60 or age > max_age_seconds:
        return None
    limiting = _limiting_bucket(payload)
    if limiting is None:
        return None
    bucket, remaining, reset_time = limiting
    return QuotaSnapshot(remaining, reset_time, _model_name(payload), bucket)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 2
        print(capture_statusline_payload(payload, args.cache))
    except (UnicodeDecodeError, json.JSONDecodeError, OSError):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
