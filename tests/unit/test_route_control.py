from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.coordinator.route_control import RouteControlService
from app.coordinator.route_control_diagnostics import RouteControlTraceStore
from app.coordinator.routes import RouteRegistry


@pytest.fixture
def test_setup(tmp_path: Path):
    reg_path = tmp_path / "routes.json"
    registry = RouteRegistry(reg_path)
    trace_store = RouteControlTraceStore(tmp_path / "traces")
    service = RouteControlService(
        registry,
        trace_store,
        public_base_url="https://bridge.example.com",
        endpoint_prefix="/x/route-control",
    )
    # Bootstrap a route
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-initial",
        "telegram-bridge-g0",
        "Development Bridge Infra",
    )
    return registry, trace_store, service


def test_prepare_bind_returns_safe_descriptor_and_opaque_url(test_setup):
    _registry, trace_store, service = test_setup

    prepared = service.prepare_bind("bridge", session_id="session-1")
    assert prepared["route_id"] == "bridge"
    assert prepared["state"] == "bind_pending"
    assert prepared["generation"] == 0
    assert "operation_id" in prepared
    assert "diagnostic_id" in prepared
    assert prepared["operation_url"].startswith("https://bridge.example.com/x/route-control/bind/")
    assert prepared["operation_id"] in prepared["operation_url"]

    # Invariant: No raw physical conversation or token exposed in model-visible fields
    dumped = json.dumps(prepared)
    assert "conv-initial" not in dumped
    assert "g-p-infra" not in dumped
    assert "marker" not in dumped

    # Verify trace started and widget_external_open is NOT staged in prepare
    sanitized = trace_store.sanitized(prepared["diagnostic_id"])
    assert sanitized is not None
    assert sanitized["status"] == "in_progress"
    assert sanitized["route_id"] == "bridge"
    assert len(sanitized["stages"]) == 0
    assert not any(st["name"] == "widget_external_open" for st in sanitized["stages"])


def test_accept_bind_return_records_candidate_without_mutating_active_route(test_setup):
    registry, _trace_store, service = test_setup

    prepared = service.prepare_bind("bridge", session_id="session-1")
    op_id = prepared["operation_id"]

    return_target = "https://chatgpt.com/g/g-p-infra/c/conv-new-target"
    accepted = service.accept_bind_return(op_id, return_target)

    assert accepted["route_id"] == "bridge"
    assert accepted["state"] == "candidate"
    assert accepted["operation_id"] == op_id
    assert "diagnostic_id" in accepted

    # Crucial Invariant: active route in registry is UNCHANGED by GET/accept stage
    current = registry.resolve("bridge")
    assert current["conversation_id"] == "conv-initial"
    assert current["generation"] == 0

    # No physical URL in accepted safe result
    dumped = json.dumps(accepted)
    assert "conv-new-target" not in dumped
    assert "g-p-infra" not in dumped


def test_commit_bind_consumes_candidate_and_mutates_route(test_setup):
    registry, trace_store, service = test_setup

    prepared = service.prepare_bind("bridge", session_id="session-1")
    op_id = prepared["operation_id"]
    return_target = "https://chatgpt.com/g/g-p-infra/c/conv-new-target"
    service.accept_bind_return(op_id, return_target)

    result = service.commit_bind(op_id)
    assert result["route_id"] == "bridge"
    assert result["state"] == "bound"
    assert result["generation"] == 1
    assert result["channel_id"] == "telegram-bridge-g1"
    assert result["changed"] is True
    assert "diagnostic_id" in result

    # Registry now reflects the new target
    updated = registry.resolve("bridge")
    assert updated["conversation_id"] == "conv-new-target"
    assert updated["generation"] == 1
    assert updated["binding_state"] == "bound"

    # Trace is completed with ok status
    sanitized = trace_store.sanitized(result["diagnostic_id"])
    assert sanitized["status"] == "ok"


def test_commit_bind_is_single_use_replay_fails(test_setup):
    _registry, trace_store, service = test_setup

    prepared = service.prepare_bind("bridge", session_id="session-1")
    op_id = prepared["operation_id"]
    return_target = "https://chatgpt.com/g/g-p-infra/c/conv-new-target"
    service.accept_bind_return(op_id, return_target)

    service.commit_bind(op_id)

    # Second commit must fail closed
    with pytest.raises(BridgeError) as exc_info:
        service.commit_bind(op_id)
    assert exc_info.value.code in {ErrorCode.INVALID_ARGUMENT, ErrorCode.POLICY_VIOLATION}

    # Replay must NOT mutate or corrupt the completed successful trace
    sanitized = trace_store.sanitized(prepared["diagnostic_id"])
    assert sanitized is not None
    assert sanitized["status"] == "ok"
    assert sanitized["error_code"] is None
    for stage in sanitized["stages"]:
        assert stage["status"] == "ok"


def test_commit_bind_replay_on_failed_trace_does_not_corrupt_history(test_setup):
    _registry, trace_store, service = test_setup

    prepared = service.prepare_bind("bridge", session_id="session-1")
    op_id = prepared["operation_id"]

    # Trigger failure during accept
    with pytest.raises(BridgeError):
        service.accept_bind_return(op_id, "https://malicious.com/bad")

    # Attempting commit on failed op should fail closed and preserve original error code
    with pytest.raises(BridgeError):
        service.commit_bind(op_id)

    sanitized = trace_store.sanitized(prepared["diagnostic_id"])
    assert sanitized["status"] == "failed"
    assert sanitized["error_code"] == "TARGET_PARSE_FAILED"


def test_commit_expired_token_fails_with_token_expired(test_setup):
    registry, trace_store, service = test_setup

    prepared = service.prepare_bind("bridge", session_id="session-1")
    op_id = prepared["operation_id"]
    return_target = "https://chatgpt.com/g/g-p-infra/c/conv-new-target"
    service.accept_bind_return(op_id, return_target)

    # Expire the pending bind in the registry
    data = registry._load()
    data["current_binds"]["bridge"]["created_at"] = "2020-01-01T00:00:00+00:00"
    registry._save(data)

    with pytest.raises(BridgeError) as exc_info:
        service.commit_bind(op_id)
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT

    sanitized = trace_store.sanitized(prepared["diagnostic_id"])
    assert sanitized["status"] == "failed"
    assert sanitized["error_code"] == "TOKEN_EXPIRED"


def test_same_target_bind_is_idempotent(test_setup):
    _registry, _trace_store, service = test_setup

    prepared = service.prepare_bind("bridge", session_id="session-1")
    op_id = prepared["operation_id"]
    # Return same target that is already bound
    service.accept_bind_return(op_id, "https://chatgpt.com/g/g-p-infra/c/conv-initial")

    result = service.commit_bind(op_id)
    assert result["route_id"] == "bridge"
    assert result["state"] == "already_bound"
    assert result["generation"] == 0
    assert result["changed"] is False


def test_accept_missing_return_target_fails_and_records_trace(test_setup):
    _registry, trace_store, service = test_setup

    prepared = service.prepare_bind("bridge", session_id="session-1")
    op_id = prepared["operation_id"]

    with pytest.raises(BridgeError) as exc_info:
        service.accept_bind_return(op_id, None)
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT

    sanitized = trace_store.sanitized(prepared["diagnostic_id"])
    assert sanitized["status"] == "failed"
    assert sanitized["error_code"] == "RETURN_TARGET_MISSING"


def test_accept_malformed_return_target_fails_and_records_trace(test_setup):
    _registry, trace_store, service = test_setup

    prepared = service.prepare_bind("bridge", session_id="session-1")
    op_id = prepared["operation_id"]

    with pytest.raises(BridgeError) as exc_info:
        service.accept_bind_return(op_id, "https://malicious.com/not-chatgpt")
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT

    sanitized = trace_store.sanitized(prepared["diagnostic_id"])
    assert sanitized["status"] == "failed"
    assert sanitized["error_code"] == "TARGET_PARSE_FAILED"


def test_accept_cross_project_mismatch_fails_and_records_trace(test_setup):
    _registry, trace_store, service = test_setup

    prepared = service.prepare_bind("bridge", session_id="session-1", allow_project_change=False)
    op_id = prepared["operation_id"]

    with pytest.raises(BridgeError) as exc_info:
        service.accept_bind_return(op_id, "https://chatgpt.com/g/g-p-otherproject/c/conv-other")
    assert exc_info.value.code == ErrorCode.POLICY_VIOLATION

    sanitized = trace_store.sanitized(prepared["diagnostic_id"])
    assert sanitized["status"] == "failed"
    assert sanitized["error_code"] == "PROJECT_MISMATCH"


def test_commit_before_accept_fails_closed(test_setup):
    _registry, trace_store, service = test_setup

    prepared = service.prepare_bind("bridge", session_id="session-1")
    op_id = prepared["operation_id"]

    with pytest.raises(BridgeError) as exc_info:
        service.commit_bind(op_id)
    assert exc_info.value.code == ErrorCode.POLICY_VIOLATION

    sanitized = trace_store.sanitized(prepared["diagnostic_id"])
    assert sanitized["status"] == "failed"
    assert sanitized["error_code"] == "CANDIDATE_NOT_READY"


def test_generation_race_fails_closed(test_setup):
    registry, _trace_store, service = test_setup

    prepared = service.prepare_bind("bridge", session_id="session-1")
    op_id = prepared["operation_id"]

    # Concurrently bump route generation
    registry.unbind("bridge", expected_generation=0)

    with pytest.raises(BridgeError) as exc_info:
        service.accept_bind_return(op_id, "https://chatgpt.com/g/g-p-infra/c/conv-new")
    assert exc_info.value.code in {ErrorCode.INVALID_ARGUMENT, ErrorCode.POLICY_VIOLATION}


def test_safe_status_reports_truthful_state_and_not_checked_wake_counts(test_setup):
    _registry, _trace_store, service = test_setup

    status = service.safe_status("bridge")
    assert status["route_id"] == "bridge"
    assert status["state"] == "bound"
    assert status["generation"] == 0
    assert status["channel_id"] == "telegram-bridge-g0"
    # Ledger ruling: wake counts and target probe remain "not_checked" until Task 5
    assert status["pending_coordinator_wakes"] == "not_checked"
    assert status["pending_durable_waiters"] == "not_checked"
    assert status["target_probe"] == "not_checked"

    dumped = json.dumps(status)
    assert "conv-initial" not in dumped
    assert "https://chatgpt.com" not in dumped
    assert "g-p-infra" not in dumped


def test_safe_status_reports_bind_pending_and_unbound(test_setup):
    registry, _trace_store, service = test_setup

    service.prepare_bind("bridge", session_id="session-1")
    status = service.safe_status("bridge")
    assert status["state"] == "bind_pending"

    # Now unbind
    registry.unbind("bridge", expected_generation=0)
    status_unbound = service.safe_status("bridge")
    assert status_unbound["state"] == "unbound"


def test_container_builds_route_control(tmp_path: Path):
    from app.container import build_container
    from app.settings import BridgeSettings

    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
        "server": {"public_base_url": "https://bridge.example.com"},
    })
    container = build_container(settings)
    assert container.route_control is not None
    assert container.route_control_trace_store is not None
    assert container.route_control.public_base_url == "https://bridge.example.com"


def test_persistence_reload(tmp_path: Path):
    reg_path = tmp_path / "routes.json"
    registry1 = RouteRegistry(reg_path)
    trace_store1 = RouteControlTraceStore(tmp_path / "traces")
    service1 = RouteControlService(registry1, trace_store1)

    registry1.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-1",
        "telegram-bridge-g0",
    )
    prepared = service1.prepare_bind("bridge", session_id="session-1")
    service1.accept_bind_return(prepared["operation_id"], "https://chatgpt.com/g/g-p-infra/c/conv-2")

    # Reload from disk in a fresh service instance
    registry2 = RouteRegistry(reg_path)
    trace_store2 = RouteControlTraceStore(tmp_path / "traces")
    service2 = RouteControlService(registry2, trace_store2)

    status = service2.safe_status("bridge")
    assert status["state"] == "bind_pending"

    commit_res = service2.commit_bind(prepared["operation_id"])
    assert commit_res["state"] == "bound"
    assert commit_res["generation"] == 1
    assert registry2.resolve("bridge")["conversation_id"] == "conv-2"
