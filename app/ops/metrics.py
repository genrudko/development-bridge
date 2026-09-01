from __future__ import annotations

import asyncio
import os
import shutil
import time

_START_TIME = time.time()
_process_counts_cache: tuple[float, dict[str, int]] = (0.0, {"chromium": 0, "xvfb": 0})


def memory_snapshot() -> dict[str, float]:
    values: dict[str, int] = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                parts = line.split(":", 1)
                if len(parts) == 2 and parts[0] in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
                    values[parts[0]] = int(parts[1].strip().split()[0]) * 1024
    except OSError:
        return {}
    gib = 1024**3
    return {
        "total_gib": round(values.get("MemTotal", 0) / gib, 2),
        "available_gib": round(values.get("MemAvailable", 0) / gib, 2),
        "swap_used_gib": round(
            (values.get("SwapTotal", 0) - values.get("SwapFree", 0)) / gib, 2
        ),
    }


def disk_snapshot() -> dict[str, float]:
    try:
        usage = shutil.disk_usage("/")
        gib = 1024**3
        return {
            "total_gib": round(usage.total / gib, 1),
            "free_gib": round(usage.free / gib, 1),
            "used_percent": round((usage.used / usage.total) * 100, 1) if usage.total else 0.0,
        }
    except OSError:
        return {}


def load_snapshot() -> list[float]:
    try:
        return [round(val, 2) for val in os.getloadavg()]
    except OSError:
        return [0.0, 0.0, 0.0]


def _scan_process_counts() -> dict[str, int]:
    counts = {"chromium": 0, "xvfb": 0}
    try:
        my_uid = os.getuid()
        for entry in os.scandir("/proc"):
            if not entry.name.isdigit():
                continue
            try:
                stat_path = os.path.join(entry.path, "status")
                with open(stat_path, "r", encoding="utf-8") as f:
                    content = f.read()
                uid_line = [l for l in content.splitlines() if l.startswith("Uid:")]
                if not uid_line or int(uid_line[0].split()[1]) != my_uid:
                    continue
                cmd_path = os.path.join(entry.path, "cmdline")
                with open(cmd_path, "rb") as f:
                    cmd = f.read().decode("utf-8", errors="ignore").lower()
                if "chromium" in cmd or "chrome" in cmd:
                    counts["chromium"] += 1
                if "xvfb" in cmd:
                    counts["xvfb"] += 1
            except (OSError, ValueError, IndexError):
                continue
    except OSError:
        pass
    return counts


def process_counts(cache_ttl_seconds: float = 5.0) -> dict[str, int]:
    global _process_counts_cache
    now = time.monotonic()
    last_time, cached = _process_counts_cache
    if now - last_time < cache_ttl_seconds:
        return dict(cached)
    res = _scan_process_counts()
    _process_counts_cache = (now, res)
    return dict(res)


async def async_process_counts(cache_ttl_seconds: float = 5.0) -> dict[str, int]:
    global _process_counts_cache
    now = time.monotonic()
    last_time, cached = _process_counts_cache
    if now - last_time < cache_ttl_seconds:
        return dict(cached)
    res = await asyncio.to_thread(_scan_process_counts)
    _process_counts_cache = (now, res)
    return dict(res)


def uptime_seconds() -> int:
    return int(time.time() - _START_TIME)
