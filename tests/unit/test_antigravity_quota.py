from datetime import UTC, datetime, timedelta
import json

from app.executors.antigravity_quota import capture_statusline_payload, load_quota_snapshot


def payload(**changes):
    value = {
        "model": {"id": "Gemini 3.7 Flash (High)", "display_name": "Gemini 3.7 Flash (High)"},
        "plan_tier": "Google AI Pro",
        "email": "private@example.test",
        "quota": {
            "3p-5h": {"remaining_fraction": 0.05, "reset_time": "2026-08-31T04:00:00Z"},
            "gemini-5h": {"remaining_fraction": 0.18, "reset_time": "2026-08-31T03:34:10Z"},
            "gemini-weekly": {"remaining_fraction": 0.82, "reset_time": "2026-09-06T22:34:10Z"},
        },
    }
    value.update(changes)
    return value


def test_capture_is_sanitized_and_load_prefers_matching_model_buckets(tmp_path):
    cache = tmp_path / "quota.json"
    now = datetime(2026, 8, 31, 0, 0, tzinfo=UTC)
    rendered = capture_statusline_payload(payload(), cache, now=now)
    saved = json.loads(cache.read_text())
    assert set(saved) == {"observed_at", "model", "plan_tier", "quota"}
    assert "email" not in cache.read_text()
    snapshot = load_quota_snapshot(cache, max_age_seconds=120, now=now + timedelta(seconds=30))
    assert snapshot is not None
    assert snapshot.remaining_fraction == 0.18
    assert snapshot.reset_time == datetime(2026, 8, 31, 3, 34, 10, tzinfo=UTC)
    assert snapshot.model == "Gemini 3.7 Flash (High)"
    assert snapshot.bucket == "gemini-5h"
    assert rendered.startswith("AG 18%")


def test_load_uses_most_constraining_bucket_when_model_family_has_no_match(tmp_path):
    cache = tmp_path / "quota.json"
    now = datetime(2026, 8, 31, 0, 0, tzinfo=UTC)
    unknown = payload(model={"id": "Other Model", "display_name": "Other Model"})
    capture_statusline_payload(unknown, cache, now=now)
    snapshot = load_quota_snapshot(cache, max_age_seconds=120, now=now)
    assert snapshot is not None
    assert snapshot.remaining_fraction == 0.05
    assert snapshot.bucket == "3p-5h"


def test_stale_or_malformed_cache_is_unknown(tmp_path):
    cache = tmp_path / "quota.json"
    now = datetime(2026, 8, 31, 0, 0, tzinfo=UTC)
    capture_statusline_payload(payload(), cache, now=now)
    assert load_quota_snapshot(cache, max_age_seconds=10, now=now + timedelta(seconds=11)) is None
    cache.write_text("not-json")
    assert load_quota_snapshot(cache, max_age_seconds=120, now=now) is None
