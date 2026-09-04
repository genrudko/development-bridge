from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.coordinator.route_control_diagnostics import RouteControlTraceStore


def test_trace_lifecycle_and_sanitization(tmp_path: Path):
    store = RouteControlTraceStore(tmp_path / "traces")
    diag_id = store.start("bind", route_id="bridge", operation_id="bind_op_token_123")
    assert diag_id.startswith("rc_") or "-" in diag_id

    # Record stages with sensitive physical details
    store.stage(
        diag_id,
        "widget_external_open",
        "ok",
        duration_ms=12.5,
    )
    store.stage(
        diag_id,
        "return_received",
        "ok",
        details={"raw_redirect_url": "https://chatgpt.com/g/g-p-infra123/c/conv-secret-uuid-456"},
    )
    store.stage(
        diag_id,
        "target_parse",
        "ok",
        details={"conversation_id": "conv-secret-uuid-456", "project_id": "g-p-infra123"},
    )
    store.finish(diag_id, status="ok")

    # 1. Raw file on disk exists, has mode 0600, contains raw details
    raw_file = tmp_path / "traces" / f"{diag_id}.json"
    assert raw_file.exists()
    assert (raw_file.stat().st_mode & 0o777) == 0o600
    raw_content = json.loads(raw_file.read_text(encoding="utf-8"))
    assert raw_content["diagnostic_id"] == diag_id
    assert raw_content["operation_type"] == "bind"
    assert raw_content["route_id"] == "bridge"
    assert raw_content["status"] == "ok"
    assert len(raw_content["stages"]) == 3

    # 2. Sanitized trace excludes all forbidden physical identity values
    sanitized = store.sanitized(diag_id)
    assert sanitized is not None
    assert sanitized["diagnostic_id"] == diag_id
    assert sanitized["operation_type"] == "bind"
    assert sanitized["route_id"] == "bridge"
    assert sanitized["status"] == "ok"
    assert len(sanitized["stages"]) == 3

    for st in sanitized["stages"]:
        assert "name" in st
        assert "status" in st
        assert "details" not in st

    dumped = json.dumps(sanitized)
    assert "conv-secret-uuid-456" not in dumped
    assert "https://chatgpt.com" not in dumped
    assert "g-p-infra123" not in dumped
    assert "bind_op_token_123" not in dumped


def test_failed_stage_and_stable_error_codes(tmp_path: Path):
    store = RouteControlTraceStore(tmp_path / "traces")
    diag_id = store.start("bind", route_id="bridge", operation_id="op_fail_1")
    store.stage(
        diag_id,
        "return_received",
        "failed",
        error_code="RETURN_TARGET_MISSING",
    )
    store.finish(diag_id, status="failed", error_code="RETURN_TARGET_MISSING")

    sanitized = store.sanitized(diag_id)
    assert sanitized is not None
    assert sanitized["status"] == "failed"
    assert sanitized["error_code"] == "RETURN_TARGET_MISSING"
    assert sanitized["stages"][0]["error_code"] == "RETURN_TARGET_MISSING"
    assert sanitized["stages"][0]["status"] == "failed"


def test_purge_expired_traces(tmp_path: Path):
    store = RouteControlTraceStore(tmp_path / "traces", raw_ttl_seconds=3600)
    diag_old = store.start("bind", route_id="bridge", operation_id="op_old")
    store.finish(diag_old, status="ok")

    diag_fresh = store.start("bind", route_id="bridge", operation_id="op_fresh")
    store.finish(diag_fresh, status="ok")

    old_file = tmp_path / "traces" / f"{diag_old}.json"
    old_mtime = time.time() - 7200
    os.utime(old_file, (old_mtime, old_mtime))

    deleted = store.purge_expired()
    assert deleted == 1
    assert not old_file.exists()
    assert (tmp_path / "traces" / f"{diag_fresh}.json").exists()


def test_find_by_operation_id(tmp_path: Path):
    store = RouteControlTraceStore(tmp_path / "traces")
    diag_id = store.start("bind", route_id="bridge", operation_id="my-op-token-xyz")
    found = store.find_by_operation_id("my-op-token-xyz")
    assert found == diag_id

    assert store.find_by_operation_id("non-existent-op") is None


def test_sanitized_nonexistent_returns_none(tmp_path: Path):
    store = RouteControlTraceStore(tmp_path / "traces")
    assert store.sanitized("non-existent-diag-id") is None


def test_raw_trace_ttl_enforced_on_normal_reads(tmp_path: Path):
    store = RouteControlTraceStore(tmp_path / "traces", raw_ttl_seconds=3600)
    diag_id = store.start("bind", route_id="bridge", operation_id="op_ttl_read")
    store.finish(diag_id, status="ok")

    # Set mtime to past TTL
    trace_file = tmp_path / "traces" / f"{diag_id}.json"
    assert trace_file.exists()
    old_mtime = time.time() - 7200
    os.utime(trace_file, (old_mtime, old_mtime))

    # Finding 3: sanitized(), find_by_operation_id(), latest_diagnostic_id_for_route() must enforce TTL
    assert store.sanitized(diag_id) is None
    assert store.find_by_operation_id("op_ttl_read") is None
    assert store.latest_diagnostic_id_for_route("bridge") is None


def test_raw_trace_0600_fails_closed_if_permission_insecure(tmp_path: Path, monkeypatch):
    store = RouteControlTraceStore(tmp_path / "traces")

    # Mock os.fchmod to simulate failure to set permissions
    def fake_fchmod(fd, mode):
        raise OSError("Permission denied / operation not permitted")

    monkeypatch.setattr(os, "fchmod", fake_fchmod)

    with pytest.raises((BridgeError, OSError)):
        store.start("bind", route_id="bridge", operation_id="op_perm_fail")


def test_diagnostic_id_entropy_and_collision_safety(tmp_path: Path):
    store = RouteControlTraceStore(tmp_path / "traces")
    diag_ids = {store.start("bind", route_id="bridge", operation_id=f"op_{i}") for i in range(50)}
    assert len(diag_ids) == 50

    # Strong entropy check: opaque diagnostic ID must contain substantial randomness (> 16 bits / at least 8 hex bytes)
    for diag_id in diag_ids:
        parts = diag_id.split("-")
        assert len(parts) >= 2
        random_part = parts[-1]
        assert len(random_part) >= 16  # at least 16 hex chars (64 bits of entropy)


def test_start_deterministic_forced_collision_preserves_existing_trace_bytes(tmp_path: Path, monkeypatch):
    store = RouteControlTraceStore(tmp_path / "traces")

    # 1. Create an existing trace with specific sentinel payload
    existing_id = "bind-deterministic-collision-target"
    store.start("bind", route_id="bridge", diagnostic_id=existing_id, operation_id="original_op")
    store.finish(existing_id, status="ok")

    trace_file = tmp_path / "traces" / f"{existing_id}.json"
    assert trace_file.exists()
    original_bytes = trace_file.read_bytes()
    original_mtime_ns = trace_file.stat().st_mtime_ns

    # 2. Attempting to start with explicit existing diagnostic_id must fail closed with POLICY_VIOLATION
    # and MUST NOT modify existing trace bytes
    with pytest.raises(BridgeError) as exc_info:
        store.start("bind", route_id="bridge", diagnostic_id=existing_id, operation_id="clobber_attempt")
    assert exc_info.value.code == ErrorCode.POLICY_VIOLATION
    assert trace_file.read_bytes() == original_bytes
    assert trace_file.stat().st_mtime_ns == original_mtime_ns

    # 3. Simulate race/collision where token_hex produces existing_id on first attempt, then new_id on second attempt
    import app.coordinator.route_control_diagnostics as rcd_mod

    seq = ["deterministic-collision-target", "new-unique-token-value-1234"]
    real_token_hex = rcd_mod.token_hex

    def fake_token_hex(n):
        if n == 12:
            return seq.pop(0)
        return real_token_hex(n)

    monkeypatch.setattr(rcd_mod, "token_hex", fake_token_hex)

    # store.start() should encounter collision, retry without mutating existing file, and return second candidate
    new_diag_id = store.start("bind", route_id="bridge", operation_id="retry_op")
    assert new_diag_id == "bind-new-unique-token-value-1234"
    assert trace_file.read_bytes() == original_bytes
    assert trace_file.stat().st_mtime_ns == original_mtime_ns

    # Verify new trace was created independently
    new_file = tmp_path / "traces" / f"{new_diag_id}.json"
    assert new_file.exists()

    # 4. If all 10 candidate attempts collide, store.start() fails closed with INTERNAL_ERROR and does not mutate target
    def always_collide(n):
        if n == 12:
            return "deterministic-collision-target"
        return real_token_hex(n)

    monkeypatch.setattr(rcd_mod, "token_hex", always_collide)

    with pytest.raises(BridgeError) as exc_info:
        store.start("bind", route_id="bridge", operation_id="exhaust_op")
    assert exc_info.value.code == ErrorCode.INTERNAL_ERROR
    assert trace_file.read_bytes() == original_bytes
    assert trace_file.stat().st_mtime_ns == original_mtime_ns


def test_atomic_no_clobber_creation_prevents_overwrite_on_simulated_race(tmp_path: Path, monkeypatch):
    store = RouteControlTraceStore(tmp_path / "traces")
    diag_id = "bind-race-test-123"

    # Pre-create the file to simulate another process creating it concurrently
    target_path = tmp_path / "traces" / f"{diag_id}.json"
    tmp_path.joinpath("traces").mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(b"INITIAL_UNTOUCHED_BYTES_SENTINEL\n")
    initial_bytes = target_path.read_bytes()

    # Even if existence check is bypassed (simulating race window between check and write),
    # atomic creation must fail and never overwrite target
    with pytest.raises((BridgeError, FileExistsError)):
        # Directly call atomic creation or start
        if hasattr(store, "_create_raw"):
            store._create_raw({"diagnostic_id": diag_id, "operation_type": "bind"})
        else:
            # Old implementation without _create_raw would fail here
            pytest.fail("store lacks atomic _create_raw")
    assert target_path.read_bytes() == initial_bytes
