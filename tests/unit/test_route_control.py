from __future__ import annotations

import asyncio
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


def test_accept_bind_return_unknown_operation_does_not_allocate_trace(test_setup):
    _registry, trace_store, service = test_setup

    with pytest.raises(BridgeError, match="invalid or stale"):
        service.accept_bind_return(
            "bind_attacker_supplied_operation",
            "https://chatgpt.com/g/g-p-infra/c/conv-attacker",
        )

    assert not trace_store.state_dir.exists()


def test_accept_bind_return_expired_operation_finishes_existing_trace(test_setup):
    registry, trace_store, service = test_setup
    prepared = service.prepare_bind("bridge", session_id="session-1")
    data = registry._load()
    data["current_binds"]["bridge"]["created_at"] = "2020-01-01T00:00:00+00:00"
    registry._save(data)

    with pytest.raises(BridgeError, match="invalid or stale"):
        service.accept_bind_return(
            prepared["operation_id"],
            "https://chatgpt.com/g/g-p-infra/c/conv-expired",
        )

    sanitized = trace_store.sanitized(prepared["diagnostic_id"])
    assert sanitized["status"] == "failed"
    assert sanitized["error_code"] == "TOKEN_EXPIRED"
    assert sanitized["stages"][-1]["name"] == "token_check"
    assert sanitized["stages"][-1]["error_code"] == "TOKEN_EXPIRED"
    assert registry.pending_current_bind("bridge") is None


def test_accept_bind_return_expired_operation_does_not_reallocate_trace(test_setup):
    registry, trace_store, service = test_setup
    prepared = service.prepare_bind("bridge", session_id="session-1")
    trace_store._trace_path(prepared["diagnostic_id"]).unlink()
    data = registry._load()
    data["current_binds"]["bridge"]["created_at"] = "2020-01-01T00:00:00+00:00"
    registry._save(data)

    with pytest.raises(BridgeError, match="invalid or stale"):
        service.accept_bind_return(
            prepared["operation_id"],
            "https://chatgpt.com/g/g-p-infra/c/conv-expired",
        )

    assert list(trace_store.state_dir.glob("*.json")) == []


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


def test_commit_bind_result_survives_post_commit_diagnostic_failure(test_setup, monkeypatch):
    registry, trace_store, service = test_setup
    prepared = service.prepare_bind("bridge", session_id="session-1")
    service.accept_bind_return(
        prepared["operation_id"],
        "https://chatgpt.com/g/g-p-infra/c/conv-new-target",
    )

    def fail_finish(*_args, **_kwargs):
        raise OSError("diagnostic storage unavailable")

    monkeypatch.setattr(trace_store, "finish", fail_finish)
    result = service.commit_bind(prepared["operation_id"])

    assert result["state"] == "bound"
    assert registry.resolve("bridge")["conversation_id"] == "conv-new-target"


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
    registry, trace_store, service = test_setup

    prepared = service.prepare_bind("bridge", session_id="session-1")
    op_id = prepared["operation_id"]

    with pytest.raises(BridgeError) as exc_info:
        service.accept_bind_return(op_id, None)
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT

    sanitized = trace_store.sanitized(prepared["diagnostic_id"])
    assert sanitized["status"] == "failed"
    assert sanitized["error_code"] == "RETURN_TARGET_MISSING"
    assert registry.pending_current_bind("bridge") is None

    retried = service.prepare_bind("bridge", session_id="session-1")
    assert retried["operation_id"] != op_id


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


def test_project_scoped_same_conversation_accepts_projectless_host_return(test_setup):
    registry, _trace_store, service = test_setup
    before = registry.resolve("bridge")
    assert before["project_id"] == "g-p-infra"
    assert before["conversation_id"] == "conv-initial"

    prepared = service.prepare_bind(
        "bridge", session_id="session-project-normalized", allow_project_change=False
    )
    service.accept_bind_return(
        prepared["operation_id"], "https://chatgpt.com/c/conv-initial"
    )
    result = service.commit_bind(prepared["operation_id"])

    assert result["state"] == "already_bound"
    assert result["changed"] is False
    assert result["generation"] == 0
    after = registry.resolve("bridge")
    assert after["project_id"] == "g-p-infra"
    assert after["conversation_id"] == "conv-initial"
    assert after["url"] == before["url"]


def test_project_scoped_same_conversation_rejects_explicit_other_project(test_setup):
    registry, trace_store, service = test_setup
    prepared = service.prepare_bind(
        "bridge", session_id="session-project-spoof", allow_project_change=False
    )

    with pytest.raises(BridgeError) as exc_info:
        service.accept_bind_return(
            prepared["operation_id"],
            "https://chatgpt.com/g/g-p-otherproject/c/conv-initial",
        )
    assert exc_info.value.code == ErrorCode.POLICY_VIOLATION
    sanitized = trace_store.sanitized(prepared["diagnostic_id"])
    assert sanitized["status"] == "failed"
    assert sanitized["error_code"] == "PROJECT_MISMATCH"
    current = registry.resolve("bridge")
    assert current["project_id"] == "g-p-infra"
    assert current["conversation_id"] == "conv-initial"


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


def test_safe_status_does_not_report_expired_bind_as_pending(test_setup):
    registry, _trace_store, service = test_setup
    service.prepare_bind("bridge", session_id="session-1")
    data = registry._load()
    data["current_binds"]["bridge"]["created_at"] = "2020-01-01T00:00:00+00:00"
    registry._save(data)

    status = service.safe_status("bridge")

    assert status["state"] == "bound"
    assert registry.pending_current_bind("bridge") is None


class _RecordingCancellationCoordinator:
    def __init__(self) -> None:
        self.cancelled = False

    async def cancel_pending(self, _channel_id: str) -> dict:
        self.cancelled = True
        return {"cancelled": True}


@pytest.mark.asyncio
async def test_cancel_result_survives_post_mutation_diagnostic_failure(test_setup, monkeypatch):
    registry, trace_store, _service = test_setup
    coordinator = _RecordingCancellationCoordinator()
    service = RouteControlService(registry, trace_store, coordinator=coordinator)

    def fail_finish(*_args, **_kwargs):
        raise OSError("diagnostic storage unavailable")

    monkeypatch.setattr(trace_store, "finish", fail_finish)
    result = await service.cancel_wakes("bridge")

    assert result["state"] == "wakes_cancelled"
    assert coordinator.cancelled is True


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["unbind", "unbind_and_cancel"])
async def test_unbind_result_survives_post_commit_diagnostic_failure(
    test_setup, monkeypatch, operation
):
    registry, trace_store, service = test_setup

    def fail_finish(*_args, **_kwargs):
        raise OSError("diagnostic storage unavailable")

    monkeypatch.setattr(trace_store, "finish", fail_finish)
    result = await getattr(service, operation)("bridge")

    assert result["state"] == "unbound"
    assert registry.is_bound(registry.resolve("bridge")) is False


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


@pytest.mark.asyncio
async def test_cancel_wakes_clears_coordinator_and_durable_waiters(tmp_path: Path):
    from app.capabilities import CapabilityPolicy
    from app.coordinator import CoordinatorService
    from app.jobs import JobService, JobStore
    from app.projects import ProjectRegistry
    from app.settings import BridgeSettings
    from app.tasks import TaskRegistry
    from tests.fixtures.repositories import create_git_repository

    repo_path = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate(
        {
            "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
            "projects": [{
                "id": "project",
                "name": "Project",
                "repositories": [{
                    "id": "repository",
                    "path": repo_path,
                    "capabilities": {"execute": True},
                    "tasks": [{
                        "id": "task",
                        "name": "Task",
                        "executable": "/bin/echo",
                        "arguments": ["done"],
                    }],
                }],
            }],
        }
    )
    projects = ProjectRegistry.from_settings(settings)
    job_store = JobStore(settings.jobs.database_path)
    job_store.initialize()
    jobs = JobService(
        job_store,
        TaskRegistry.from_settings(settings),
        projects,
        CapabilityPolicy(),
        None,
    )
    jobs.register_durable_terminal_handler("coordinator", lambda p, r, s: None)
    coordinator = CoordinatorService(tmp_path / "coordinator-wakes.json")
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-1",
        "telegram-bridge-g0",
    )
    trace_store = RouteControlTraceStore(tmp_path / "traces")
    service = RouteControlService(
        registry,
        trace_store,
        coordinator=coordinator,
        jobs=jobs,
    )

    # 1. Arm coordinator wake
    await coordinator.arm("test wake", channel_id="telegram-bridge-g0", delay_seconds=10)
    assert (await coordinator.status("telegram-bridge-g0"))["state"] == "pending"

    # 2. Arm durable job waiter
    repo = projects.repositories.get("project", "repository")
    job = await jobs.start_task(repo, "task", "req-1")
    await jobs.wake_on_jobs_durable(
        repo,
        (job.job_id,),
        "all_terminal",
        "coordinator",
        {"route_id": "bridge", "generation": 0, "channel_id": "telegram-bridge-g0"},
    )
    assert len(job_store.terminal_waiters()) == 1

    # 3. Cancel wakes
    res = await service.cancel_wakes("bridge")
    assert res["route_id"] == "bridge"
    assert res["state"] == "wakes_cancelled"
    assert res["generation"] == 0
    assert res["cancelled_coordinator_wakes"] == 1
    assert res["cancelled_durable_waiters"] == 1
    assert "conv-1" not in json.dumps(res)

    # Invariants: coordinator is idle, durable waiters are 0, job is NOT cancelled
    assert (await coordinator.status("telegram-bridge-g0"))["state"] == "idle"
    assert len(job_store.terminal_waiters()) == 0
    assert jobs.status(repo, job.job_id).status.value == "queued"


@pytest.mark.asyncio
async def test_ordinary_unbind_refuses_when_wake_producing_state_exists(tmp_path: Path):
    from app.capabilities import CapabilityPolicy
    from app.coordinator import CoordinatorService
    from app.jobs import JobService, JobStore
    from app.projects import ProjectRegistry
    from app.settings import BridgeSettings
    from app.tasks import TaskRegistry
    from tests.fixtures.repositories import create_git_repository

    repo_path = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate(
        {
            "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
            "projects": [{
                "id": "project",
                "name": "Project",
                "repositories": [{
                    "id": "repository",
                    "path": repo_path,
                    "capabilities": {"execute": True},
                    "tasks": [{
                        "id": "task",
                        "name": "Task",
                        "executable": "/bin/echo",
                        "arguments": ["done"],
                    }],
                }],
            }],
        }
    )
    projects = ProjectRegistry.from_settings(settings)
    job_store = JobStore(settings.jobs.database_path)
    job_store.initialize()
    jobs = JobService(
        job_store,
        TaskRegistry.from_settings(settings),
        projects,
        CapabilityPolicy(),
        None,
    )
    jobs.register_durable_terminal_handler("coordinator", lambda p, r, s: None)
    coordinator = CoordinatorService(tmp_path / "coordinator-wakes.json")
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-1",
        "telegram-bridge-g0",
    )
    trace_store = RouteControlTraceStore(tmp_path / "traces")
    service = RouteControlService(
        registry,
        trace_store,
        coordinator=coordinator,
        jobs=jobs,
    )

    # Coordinator wake exists -> unbind must fail closed
    await coordinator.arm("test wake", channel_id="telegram-bridge-g0", delay_seconds=10)
    with pytest.raises(BridgeError) as exc_info:
        await service.unbind("bridge")
    assert exc_info.value.code == ErrorCode.POLICY_VIOLATION
    assert exc_info.value.details.get("error_code") == "PENDING_WAKES"
    assert registry.is_bound(registry.resolve("bridge"))

    # Cancel coordinator wake
    await coordinator.cancel_pending("telegram-bridge-g0")

    # Durable waiter exists -> unbind must fail closed
    repo = projects.repositories.get("project", "repository")
    job = await jobs.start_task(repo, "task", "req-1")
    await jobs.wake_on_jobs_durable(
        repo,
        (job.job_id,),
        "all_terminal",
        "coordinator",
        {"route_id": "bridge", "generation": 0, "channel_id": "telegram-bridge-g0"},
    )
    with pytest.raises(BridgeError) as exc_info:
        await service.unbind("bridge")
    assert exc_info.value.code == ErrorCode.POLICY_VIOLATION
    assert exc_info.value.details.get("error_code") == "PENDING_WAKES"
    assert registry.is_bound(registry.resolve("bridge"))

    # Clean state -> unbind succeeds
    await jobs.cancel_durable_waiters(handler_name="coordinator", payload_match={"route_id": "bridge", "generation": 0})
    unbound = await service.unbind("bridge")
    assert unbound["state"] == "unbound"
    assert unbound["generation"] == 0
    assert not registry.is_bound(registry.resolve("bridge"))


@pytest.mark.asyncio
async def test_unbind_and_cancel_clears_wakes_and_unbinds_cleanly(tmp_path: Path):
    from app.capabilities import CapabilityPolicy
    from app.coordinator import CoordinatorService
    from app.jobs import JobService, JobStore
    from app.projects import ProjectRegistry
    from app.settings import BridgeSettings
    from app.tasks import TaskRegistry
    from tests.fixtures.repositories import create_git_repository

    repo_path = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate(
        {
            "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
            "projects": [{
                "id": "project",
                "name": "Project",
                "repositories": [{
                    "id": "repository",
                    "path": repo_path,
                    "capabilities": {"execute": True},
                    "tasks": [{
                        "id": "task",
                        "name": "Task",
                        "executable": "/bin/echo",
                        "arguments": ["done"],
                    }],
                }],
            }],
        }
    )
    projects = ProjectRegistry.from_settings(settings)
    job_store = JobStore(settings.jobs.database_path)
    job_store.initialize()
    jobs = JobService(
        job_store,
        TaskRegistry.from_settings(settings),
        projects,
        CapabilityPolicy(),
        None,
    )
    jobs.register_durable_terminal_handler("coordinator", lambda p, r, s: None)
    coordinator = CoordinatorService(tmp_path / "coordinator-wakes.json")
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-1",
        "telegram-bridge-g0",
    )
    trace_store = RouteControlTraceStore(tmp_path / "traces")
    service = RouteControlService(
        registry,
        trace_store,
        coordinator=coordinator,
        jobs=jobs,
    )


    # Arm both coordinator wake and durable job waiter
    await coordinator.arm("test wake", channel_id="telegram-bridge-g0", delay_seconds=10)
    repo = projects.repositories.get("project", "repository")
    job = await jobs.start_task(repo, "task", "req-1")
    await jobs.wake_on_jobs_durable(
        repo,
        (job.job_id,),
        "all_terminal",
        "coordinator",
        {"route_id": "bridge", "generation": 0, "channel_id": "telegram-bridge-g0"},
    )

    result = await service.unbind_and_cancel("bridge")
    assert result["route_id"] == "bridge"
    assert result["state"] == "unbound"
    assert result["cancelled_coordinator_wakes"] == 1
    assert result["cancelled_durable_waiters"] == 1

    # Verify state in all subsystems
    assert not registry.is_bound(registry.resolve("bridge"))
    assert (await coordinator.status("telegram-bridge-g0"))["state"] == "idle"
    assert len(job_store.terminal_waiters()) == 0

    # Idempotent repeat call
    repeat = await service.unbind_and_cancel("bridge")
    assert repeat["state"] == "unbound"
    assert repeat["cancelled_coordinator_wakes"] == 0
    assert repeat["cancelled_durable_waiters"] == 0


@pytest.mark.asyncio
async def test_resume_coordinator_waiter_stale_generation_or_unbound_is_safe_noop(tmp_path: Path):
    from app.container import build_container
    from app.settings import BridgeSettings
    from tests.fixtures.repositories import create_git_repository

    repo_path = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate(
        {
            "coordinator": {"route_registry_path": tmp_path / "routes.json"},
            "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
            "projects": [{
                "id": "project",
                "name": "Project",
                "repositories": [{
                    "id": "repository",
                    "path": repo_path,
                    "capabilities": {"execute": True},
                    "tasks": [{
                        "id": "task",
                        "name": "Task",
                        "executable": "/bin/echo",
                        "arguments": ["done"],
                    }],
                }],
            }],
        }
    )
    container = build_container(settings)
    container.jobs._store.initialize()
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-1",
        "telegram-bridge-g0",
    )
    # Rebind to generation 1
    container.route_registry.takeover("bridge", "https://chatgpt.com/g/g-p-infra/c/conv-2")
    route_g1 = container.route_registry.resolve("bridge")
    assert route_g1["generation"] == 1
    assert route_g1["channel_id"] == "telegram-bridge-g1"

    # Now simulate a waiter from generation 0 firing
    repo = container.projects.repositories.get("project", "repository")
    job = await container.jobs.start_task(repo, "task", "req-stale")

    # Call resume_coordinator_waiter directly via registered handler
    handler = container.jobs._durable_terminal_handlers["coordinator"]

    # 1. Stale generation waiter (gen 0 vs current gen 1) -> must be safe no-op
    await handler(
        {"route_id": "bridge", "generation": 0, "channel_id": "telegram-bridge-g0"},
        (job,),
        "all_terminal",
    )
    # Check that NO wake was armed on either channel
    assert (await container.coordinator.status("telegram-bridge-g0"))["state"] == "idle"
    assert (await container.coordinator.status("telegram-bridge-g1"))["state"] == "idle"

    # 2. A legacy channel-only waiter must not wake a route channel that later became current.
    await handler(
        {"channel_id": "telegram-bridge-g1", "message": "unpinned future wake"},
        (job,),
        "all_terminal",
    )
    assert (await container.coordinator.status("telegram-bridge-g1"))["state"] == "idle"

    # 3. Unbound route -> must be safe no-op
    container.route_registry.unbind("bridge", expected_generation=1)
    await handler(
        {"route_id": "bridge", "generation": 1, "channel_id": "telegram-bridge-g1"},
        (job,),
        "all_terminal",
    )
    assert (await container.coordinator.status("telegram-bridge-g1"))["state"] == "idle"


@pytest.mark.asyncio
async def test_job_finishes_after_unbind_and_cancel_without_wake_and_remains_queryable(tmp_path: Path):
    import sys

    from app.container import build_container
    from app.jobs import JobStatus
    from app.settings import BridgeSettings
    from tests.fixtures.repositories import create_git_repository

    repo_path = create_git_repository(tmp_path, "repository")

    settings = BridgeSettings.model_validate(
        {
            "coordinator": {"route_registry_path": tmp_path / "routes.json"},
            "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
            "projects": [{
                "id": "project",
                "name": "Project",
                "repositories": [{
                    "id": "repository",
                    "path": repo_path,
                    "capabilities": {"execute": True},
                    "tasks": [{
                        "id": "task",
                        "name": "Task",
                        "executable": sys.executable,
                        "arguments": ["-c", "print('queryable-output')"],
                        "timeout_seconds": 5,
                    }],
                }],
            }],
        }
    )
    container = build_container(settings)
    container.jobs._store.initialize()
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-1",
        "telegram-bridge-g0",
    )
    repo = container.projects.repositories.get("project", "repository")
    job = await container.jobs.start_task(repo, "task", "req-test-e2e")

    # Register durable waiter for route bridge
    await container.jobs.wake_on_jobs_durable(
        repo,
        (job.job_id,),
        "all_terminal",
        "coordinator",
        {"route_id": "bridge", "generation": 0, "channel_id": "telegram-bridge-g0"},
    )
    assert len(container.jobs._store.terminal_waiters()) == 1

    # Unbind + cancel
    res = await container.route_control.unbind_and_cancel("bridge")
    assert res["state"] == "unbound"
    assert res["cancelled_durable_waiters"] == 1
    assert len(container.jobs._store.terminal_waiters()) == 0
    assert not container.route_registry.is_bound(container.route_registry.resolve("bridge"))

    # Start job worker to execute the task
    await container.jobs.start()
    try:
        for _ in range(300):
            status = container.jobs.status(repo, job.job_id)
            if status.status == JobStatus.SUCCEEDED:
                break
            await asyncio.sleep(0.01)
        assert container.jobs.status(repo, job.job_id).status == JobStatus.SUCCEEDED
        # Verify output is queryable
        assert b"queryable-output" in container.jobs.output(repo, job.job_id).stdout

        # Verify NO coordinator wake was created
        coord_status = await container.coordinator.status("telegram-bridge-g0")
        assert coord_status["state"] == "idle"
    finally:
        await container.jobs.stop()


@pytest.mark.asyncio
async def test_resume_coordinator_waiter_legacy_unpinned_route_payload_is_safe_noop(tmp_path: Path):
    from app.container import build_container
    from app.settings import BridgeSettings
    from tests.fixtures.repositories import create_git_repository

    repo_path = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate(
        {
            "coordinator": {"route_registry_path": tmp_path / "routes.json"},
            "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
            "projects": [{
                "id": "project",
                "name": "Project",
                "repositories": [{
                    "id": "repository",
                    "path": repo_path,
                    "capabilities": {"execute": True},
                    "tasks": [{
                        "id": "task",
                        "name": "Task",
                        "executable": "/bin/echo",
                        "arguments": ["done"],
                    }],
                }],
            }],
        }
    )
    container = build_container(settings)
    container.jobs._store.initialize()
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-1",
        "telegram-bridge-g0",
    )
    repo = container.projects.repositories.get("project", "repository")
    job = await container.jobs.start_task(repo, "task", "req-legacy")

    handler = container.jobs._durable_terminal_handlers["coordinator"]

    # Legacy payload with ONLY route_id (missing generation and channel_id)
    # Must NOT wake current or successor route - must safe no-op!
    await handler(
        {"route_id": "bridge"},
        (job,),
        "all_terminal",
    )
    assert (await container.coordinator.status("telegram-bridge-g0"))["state"] == "idle"


@pytest.mark.asyncio
async def test_unbind_and_cancel_serializes_with_same_route_arm(tmp_path: Path):
    from types import SimpleNamespace

    from app.api.registry import ToolRegistry
    from app.container import build_container
    from app.settings import BridgeSettings
    from app.tools.coordinator import coordinator_tools
    from tests.fixtures.repositories import create_git_repository

    repo_path = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate(
        {
            "coordinator": {"route_registry_path": tmp_path / "routes.json"},
            "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
            "projects": [{
                "id": "project",
                "name": "Project",
                "repositories": [{
                    "id": "repository",
                    "path": repo_path,
                    "capabilities": {"execute": True},
                }],
            }],
        }
    )
    container = build_container(settings)
    container.jobs._store.initialize()
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-1",
        "telegram-bridge-g0",
    )
    tools = ToolRegistry()
    for tool in coordinator_tools(container):
        tools.register(tool)
    continue_tool = tools.get("coordinator_continue")

    # Acquire the route transition guard to simulate unbind_and_cancel in progress
    route_lock = container.route_registry.route_lock("bridge")
    arm_task_started = asyncio.Event()
    arm_error = []

    async def concurrent_continue():
        arm_task_started.set()
        try:
            await continue_tool.handler(
                None,
                SimpleNamespace(arguments={"route_id": "bridge", "message": "wake in gap"}),
                SimpleNamespace(request_id="req-cont-race"),
            )
        except BridgeError as exc:
            arm_error.append(exc)

    async with route_lock:
        # Start concurrent continue
        task = asyncio.create_task(concurrent_continue())
        await arm_task_started.wait()
        # While locked, unbind the route
        container.route_registry.unbind("bridge", expected_generation=0)

    await task
    # Concurrent continue must fail closed because route was unbound across the barrier
    assert len(arm_error) == 1
    assert isinstance(arm_error[0], BridgeError)
    assert arm_error[0].code == ErrorCode.POLICY_VIOLATION
    assert (await container.coordinator.status("telegram-bridge-g0"))["state"] == "idle"


@pytest.mark.asyncio
async def test_unbind_and_cancel_serializes_with_route_waiter_registration(tmp_path: Path):
    from types import SimpleNamespace

    from app.api.registry import ToolRegistry
    from app.container import build_container
    from app.settings import BridgeSettings
    from app.tools.coordinator import coordinator_tools
    from tests.fixtures.repositories import create_git_repository

    repo_path = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate(
        {
            "coordinator": {"route_registry_path": tmp_path / "routes.json"},
            "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
            "projects": [{
                "id": "project",
                "name": "Project",
                "repositories": [{
                    "id": "repository",
                    "path": repo_path,
                    "capabilities": {"execute": True},
                    "tasks": [{
                        "id": "task",
                        "name": "Task",
                        "executable": "/bin/echo",
                        "arguments": ["done"],
                    }],
                }],
            }],
        }
    )
    container = build_container(settings)
    container.jobs._store.initialize()
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-1",
        "telegram-bridge-g0",
    )
    repo = container.projects.repositories.get("project", "repository")
    job = await container.jobs.start_task(repo, "task", "req-reg-race")

    tools = ToolRegistry()
    for tool in coordinator_tools(container):
        tools.register(tool)
    wake_tool = tools.get("coordinator_wake_on_jobs")

    route_lock = container.route_registry.route_lock("bridge")
    reg_task_started = asyncio.Event()
    reg_error = []

    async def concurrent_register():
        reg_task_started.set()
        try:
            await wake_tool.handler(
                None,
                SimpleNamespace(arguments={
                    "project_id": "project",
                    "repository_id": "repository",
                    "job_ids": [job.job_id],
                    "route_id": "bridge",
                }),
                SimpleNamespace(request_id="req-wake-race"),
            )
        except BridgeError as exc:
            reg_error.append(exc)

    async with route_lock:
        task = asyncio.create_task(concurrent_register())
        await reg_task_started.wait()
        # Unbind route while registration is queued behind lock
        container.route_registry.unbind("bridge", expected_generation=0)

    await task
    # Registration must fail closed
    assert len(reg_error) == 1
    assert isinstance(reg_error[0], BridgeError)
    assert reg_error[0].code == ErrorCode.POLICY_VIOLATION
    assert len(container.jobs._store.terminal_waiters()) == 0


@pytest.mark.asyncio
async def test_different_routes_remain_independent(tmp_path: Path):
    from app.container import build_container
    from app.settings import BridgeSettings

    settings = BridgeSettings.model_validate(
        {
            "coordinator": {"route_registry_path": tmp_path / "routes.json"},
            "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
        }
    )
    container = build_container(settings)
    container.jobs._store.initialize()
    container.route_registry.bootstrap(
        "route-a",
        "https://chatgpt.com/g/g-p-infra/c/conv-a",
        "telegram-route-a-g0",
    )
    container.route_registry.bootstrap(
        "route-b",
        "https://chatgpt.com/g/g-p-infra/c/conv-b",
        "telegram-route-b-g0",
    )

    # Lock route-a
    lock_a = container.route_registry.route_lock("route-a")
    async with lock_a:
        # route-b cancel/unbind proceeds without blocking on route-a lock
        result_b = await container.route_control.unbind_and_cancel("route-b")
        assert result_b["state"] == "unbound"
        assert not container.route_registry.is_bound(container.route_registry.resolve("route-b"))
        assert container.route_registry.is_bound(container.route_registry.resolve("route-a"))


@pytest.mark.asyncio
async def test_unbind_and_cancel_serializes_with_terminal_callback(tmp_path: Path):
    from app.container import build_container
    from app.settings import BridgeSettings
    from tests.fixtures.repositories import create_git_repository

    repo_path = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate(
        {
            "coordinator": {"route_registry_path": tmp_path / "routes.json"},
            "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
            "projects": [{
                "id": "project",
                "name": "Project",
                "repositories": [{
                    "id": "repository",
                    "path": repo_path,
                    "capabilities": {"execute": True},
                    "tasks": [{
                        "id": "task",
                        "name": "Task",
                        "executable": "/bin/echo",
                        "arguments": ["done"],
                    }],
                }],
            }],
        }
    )
    container = build_container(settings)
    container.jobs._store.initialize()
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-1",
        "telegram-bridge-g0",
    )
    repo = container.projects.repositories.get("project", "repository")
    job = await container.jobs.start_task(repo, "task", "req-cb-race")

    route_lock = container.route_registry.route_lock("bridge")
    cb_started = asyncio.Event()
    handler = container.jobs._durable_terminal_handlers["coordinator"]

    async def concurrent_callback():
        cb_started.set()
        await handler(
            {"route_id": "bridge", "generation": 0, "channel_id": "telegram-bridge-g0"},
            (job,),
            "all_terminal",
        )

    async with route_lock:
        task = asyncio.create_task(concurrent_callback())
        await cb_started.wait()
        # Unbind route while callback is queued behind route lock
        container.route_registry.unbind("bridge", expected_generation=0)

    await task
    # Terminal callback must safe no-op because route was unbound before it acquired route lock
    assert (await container.coordinator.status("telegram-bridge-g0"))["state"] == "idle"


@pytest.mark.asyncio
async def test_route_scoped_wake_on_already_terminal_jobs_does_not_deadlock(tmp_path: Path):
    from types import SimpleNamespace

    from app.api.registry import ToolRegistry
    from app.container import build_container
    from app.jobs import JobStatus
    from app.settings import BridgeSettings
    from app.tools.coordinator import coordinator_tools
    from tests.fixtures.repositories import create_git_repository

    repo_path = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate(
        {
            "coordinator": {"route_registry_path": tmp_path / "routes.json"},
            "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
            "projects": [{
                "id": "project",
                "name": "Project",
                "repositories": [{
                    "id": "repository",
                    "path": repo_path,
                    "capabilities": {"execute": True},
                    "tasks": [{
                        "id": "task",
                        "name": "Task",
                        "executable": "/bin/echo",
                        "arguments": ["done"],
                    }],
                }],
            }],
        }
    )
    container = build_container(settings)
    container.jobs._store.initialize()
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-1",
        "telegram-bridge-g0",
    )
    repo = container.projects.repositories.get("project", "repository")
    job = await container.jobs.start_task(repo, "task", "req-term")
    # Mark job as already finished (terminal)
    container.jobs._store.start(job.job_id)
    container.jobs._store.finish(job.job_id, JobStatus.SUCCEEDED, exit_code=0)

    tools = ToolRegistry()
    for tool in coordinator_tools(container):
        tools.register(tool)
    wake_tool = tools.get("coordinator_wake_on_jobs")

    # Calling wake_on_jobs on an already-terminal job must not deadlock
    await asyncio.wait_for(
        wake_tool.handler(
            None,
            SimpleNamespace(arguments={
                "project_id": "project",
                "repository_id": "repository",
                "job_ids": [job.job_id],
                "route_id": "bridge",
            }),
            SimpleNamespace(request_id="req-term-wake"),
        ),
        timeout=1.0,
    )
    assert (await container.coordinator.status("telegram-bridge-g0"))["state"] != "idle"


@pytest.mark.asyncio
async def test_pre_task_5_waiter_without_generation_handled_safely_for_status_and_unbind(tmp_path: Path):
    from app.container import build_container
    from app.settings import BridgeSettings
    from tests.fixtures.repositories import create_git_repository

    repo_path = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate(
        {
            "coordinator": {"route_registry_path": tmp_path / "routes.json"},
            "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
            "projects": [{
                "id": "project",
                "name": "Project",
                "repositories": [{
                    "id": "repository",
                    "path": repo_path,
                    "capabilities": {"execute": True},
                    "tasks": [{
                        "id": "task",
                        "name": "Task",
                        "executable": "/bin/echo",
                        "arguments": ["done"],
                    }],
                }],
            }],
        }
    )
    container = build_container(settings)
    container.jobs._store.initialize()
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-1",
        "telegram-bridge-g0",
    )
    repo = container.projects.repositories.get("project", "repository")
    job = await container.jobs.start_task(repo, "task", "req-legacy-status")

    # Manually persist pre-Task-5 legacy waiter with generation=None in payload
    container.jobs.store.save_terminal_waiter(
        waiter_id="legacy-waiter-1",
        project_id="project",
        repository_id="repository",
        job_ids=(job.job_id,),
        policy="all_terminal",
        handler_name="coordinator",
        payload={"route_id": "bridge", "generation": None},
    )

    # safe_status must not crash with TypeError on generation=None
    status = container.route_control.safe_status("bridge")
    assert status["state"] == "bound"
    assert status["pending_durable_waiters"] == 0

    # unbind must not crash with TypeError and must succeed safely since unpinned waiter is not wake-producing
    unbind_res = await container.route_control.unbind("bridge")
    assert unbind_res["state"] == "unbound"

    # Re-bind route to successor generation
    prep = container.route_control.prepare_bind("bridge", allow_project_change=True)
    container.route_control.accept_bind_return(
        prep["operation_id"], "https://chatgpt.com/g/g-p-infra/c/conv-successor"
    )
    container.route_control.commit_bind(prep["operation_id"])
    assert container.route_registry.resolve("bridge")["generation"] == 1

    # Persist another legacy waiter without generation key
    container.jobs.store.save_terminal_waiter(
        waiter_id="legacy-waiter-2",
        project_id="project",
        repository_id="repository",
        job_ids=(job.job_id,),
        policy="all_terminal",
        handler_name="coordinator",
        payload={"route_id": "bridge"},
    )

    # unbind_and_cancel must handle legacy waiter safely without error
    unbind_cancel_res = await container.route_control.unbind_and_cancel("bridge")
    assert unbind_cancel_res["state"] == "unbound"


@pytest.mark.asyncio
async def test_terminal_callback_rejects_source_generation_while_rollover_pending(tmp_path: Path):
    from app.container import build_container
    from app.jobs.models import JobRecord, JobStatus
    from app.settings import BridgeSettings
    container = build_container(BridgeSettings.model_validate({"coordinator": {"route_registry_path": tmp_path / "routes.json"}}))
    container.route_registry.bootstrap("bridge", "https://chatgpt.com/g/g-p-infra/c/conv-current", "telegram-bridge-g0")
    container.route_registry.prepare_rollover("bridge")
    handler = container.jobs._durable_terminal_handlers["coordinator"]
    job = JobRecord(job_id="job_00000000000000000000000000000099", project_id="development-bridge", repository_id="development-bridge", task_id="test", request_id="req-rollover-terminal", status=JobStatus.SUCCEEDED, created_at="2026-09-05T00:00:00+00:00")
    with pytest.raises(BridgeError, match="rollover"):
        await handler({"route_id": "bridge", "generation": 0, "channel_id": "telegram-bridge-g0"}, (job,), "all_terminal")
    assert (await container.coordinator.status("telegram-bridge-g0"))["state"] == "idle"

@pytest.mark.asyncio
async def test_rollover_prepare_rejects_in_flight_route_durable_waiter(tmp_path: Path):
    from types import SimpleNamespace

    from app.container import build_container
    from app.jobs.service import TerminalWaiter
    from app.settings import BridgeSettings
    from app.tools.registry import build_tool_registry

    container = build_container(BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    }))
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-current",
        "telegram-bridge-g0",
    )

    async def callback(_jobs, _reason):
        return None

    container.jobs._firing_terminal_waiters["waiter-rollover-in-flight"] = TerminalWaiter(
        waiter_id="waiter-rollover-in-flight",
        job_ids=("job_00000000000000000000000000000098",),
        policy="all_terminal",
        callback=callback,
        durable=True,
        handler_name="coordinator",
        payload={"route_id": "bridge", "generation": 0, "channel_id": "telegram-bridge-g0"},
    )
    tool = build_tool_registry(container).get("coordinator_route_rollover_prepare")
    with pytest.raises(BridgeError, match="durable waiter"):
        await tool.handler(
            None,
            SimpleNamespace(arguments={"route_id": "bridge"}),
            SimpleNamespace(request_id="req-rollover-in-flight"),
        )
    assert container.route_registry.pending_rollover("bridge") is None


def test_route_control_prepare_missing_route_without_flag_fails(test_setup):
    _registry, _trace_store, service = test_setup
    with pytest.raises(BridgeError) as exc_info:
        service.prepare_bind("missing-route", session_id="session-1")
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT


def test_route_control_bootstrap_flow_end_to_end_commits_generation_0(test_setup):
    registry, trace_store, service = test_setup
    prepared = service.prepare_bind("newroute", session_id="session-1", bootstrap_if_missing=True)
    assert prepared["route_id"] == "newroute"
    assert prepared["state"] == "bind_pending"
    assert prepared["generation"] == 0
    assert prepared["channel_id"] == "telegram-newroute-g0"
    op_id = prepared["operation_id"]
    diag_id = prepared["diagnostic_id"]

    # Pre-commit invariants
    assert registry.resolve("newroute") is None

    # Safe status reports bind_pending
    status = service.safe_status("newroute")
    assert status["route_id"] == "newroute"
    assert status["state"] == "bind_pending"
    assert status["generation"] == 0

    # Accept return target
    return_target = "https://chatgpt.com/g/g-p-infra/c/conv-bootstrap-target"
    accepted = service.accept_bind_return(op_id, return_target)
    assert accepted["state"] == "candidate"
    assert registry.resolve("newroute") is None

    # Commit
    result = service.commit_bind(op_id)
    assert result["route_id"] == "newroute"
    assert result["state"] == "bound"
    assert result["generation"] == 0
    assert result["channel_id"] == "telegram-newroute-g0"
    assert result["changed"] is True

    # Post-commit check
    route = registry.resolve("newroute")
    assert route is not None
    assert route["generation"] == 0
    assert route["conversation_id"] == "conv-bootstrap-target"

    # Status is now bound
    status_after = service.safe_status("newroute")
    assert status_after["state"] == "bound"


def test_route_control_bootstrap_failed_return_leaves_no_route(test_setup):
    registry, trace_store, service = test_setup
    prepared = service.prepare_bind("badroute", session_id="session-1", bootstrap_if_missing=True)
    op_id = prepared["operation_id"]

    with pytest.raises(BridgeError) as exc_info:
        service.accept_bind_return(op_id, "https://not-chatgpt.com/target")
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT
    assert registry.resolve("badroute") is None
    assert registry.pending_current_bind("badroute") is None
