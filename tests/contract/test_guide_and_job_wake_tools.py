import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from app.container import build_container
from app.jobs import JobStatus
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry
from tests.fixtures.repositories import create_git_repository


def test_bridge_guide_is_registry_derived_and_complete():
    registry = build_tool_registry(build_container(BridgeSettings()))
    guide = registry.get("bridge_guide")
    assert "START HERE" in guide.definition.description
    result = asyncio.run(
        guide.handler(
            None,
            SimpleNamespace(arguments={}),
            SimpleNamespace(request_id="guide-request"),
        )
    )
    data = json.loads(result.content[0].text)["data"]
    catalog = {
        item["name"]
        for tools in data["tools_by_category"].values()
        for item in tools
    }
    assert data["tool_count"] == 93
    assert catalog == {tool.name for tool in registry.definitions}
    assert "queued status is normal" in data["durable_jobs"]["rule"]
    assert any("batched_messages" in step for step in data["durable_jobs"]["preferred_event_flow"])
    economy = data["economy_mode"]
    assert "scarce resource" in economy["objective"]
    assert any("Do not poll durable jobs" in rule for rule in economy["rules"])
    assert any("ChatGPT Web/Browser Host" in rule for rule in economy["rules"])
    assert any("Do not repeat discovery" in rule for rule in economy["rules"])
    assert "check -> change -> targeted tests" in economy["rules"][0]
    assert "inspect exact state" in economy["executor_job_shape"]
    delegation = data["executor_delegation"]
    assert "mandatory" in delegation["rule"]
    assert "AGENTS.md" in delegation["rule"]
    assert "ECONOMY MODE" in delegation["prompt_suffix"]
    assert "do not poll durable jobs frequently" in delegation["prompt_suffix"]
    agent_rules = (Path(__file__).parents[2] / "AGENTS.md").read_text(encoding="utf-8")
    assert "## Economy Mode" in agent_rules
    assert "one bounded work cycle" in agent_rules
    assert "Never retry live UI actions during rate-limit/backoff" in agent_rules


def test_coordinator_job_wake_schema_is_bounded_and_mount_explicit():
    registry = build_tool_registry(build_container(BridgeSettings()))
    tool = registry.get("coordinator_wake_on_jobs").definition
    assert tool.input_schema["required"] == [
        "project_id",
        "repository_id",
        "job_ids",
    ]
    assert tool.input_schema["properties"]["job_ids"]["maxItems"] == 64
    assert "coordinator_x_mount" in tool.description
    assert "Transport failures" in tool.description
    assert "not redelivered" in tool.description
    assert "missing model ACK" in tool.description
    assert "durable" in tool.description
    assert "restored across Bridge restart" in tool.description
    assert "batches concurrent terminal" in tool.description


def test_x_wake_payload_never_contains_job_output(tmp_path):
    repository_path = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate(
        {
            "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
            "coordinator": {"route_registry_path": tmp_path / "routes.json"},
            "projects": [{
                "id": "project",
                "name": "Project",
                "repositories": [{
                    "id": "repository",
                    "path": repository_path,
                    "capabilities": {"execute": True},
                    "tasks": [{
                        "id": "task",
                        "name": "Task",
                        "executable": sys.executable,
                        "arguments": ["-c", "print('TOP-SECRET-OUTPUT')"],
                    }],
                }],
            }],
        }
    )
    container = build_container(settings)
    container.coordinator.JOB_WAKE_DEBOUNCE_SECONDS = 0
    container.jobs._store.initialize()

    async def scenario():
        repository = container.projects.repositories.get("project", "repository")
        job = await container.jobs.start_task(repository, "task", "req")
        container.jobs._store.append_output(
            job.job_id, "stdout", b"TOP-SECRET-OUTPUT", 1024
        )
        assert container.jobs._store.start(job.job_id)
        await container.jobs._finish_job(job.job_id, JobStatus.SUCCEEDED)
        registry = build_tool_registry(container)
        await registry.get("coordinator_wake_on_jobs").handler(
            None,
            SimpleNamespace(arguments={
                "project_id": "project",
                "repository_id": "repository",
                "job_ids": [job.job_id],
                "channel_id": "coordinator",
            }),
            SimpleNamespace(request_id="wake-request"),
        )
        status = await container.coordinator.status()
        assert status["state"] == "browser_preflight"
        authorized = await container.coordinator.authorize_browser_preflight(
            "coordinator", status["continuation_id"]
        )
        assert authorized["authorized"] is True
        # Preflight authorization publishes the wake through a scheduled transition.
        # Yield once so claim observes the newly authorized continuation deterministically.
        await asyncio.sleep(0)
        return await container.coordinator.claim()

    claim = asyncio.run(scenario())
    assert claim["claimed"] is True
    assert "TOP-SECRET-OUTPUT" not in claim["message"]
    assert "reason=all_terminal" in claim["message"]


def test_coordinator_ack_schema_is_explicit_and_bounded():
    registry = build_tool_registry(build_container(BridgeSettings()))
    tool = registry.get("coordinator_ack").definition
    assert tool.input_schema["required"] == ["continuation_id"]
    assert tool.input_schema["properties"]["continuation_id"]["pattern"].startswith("^cont_")
    assert "Telegram escalation" in tool.description
    assert "batched_messages" in tool.description


def test_coordinator_exec_and_wake_queues_job_and_durable_waiter(tmp_path):
    repository_path = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate({
        "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
        "projects": [{"id": "project", "name": "Project", "repositories": [{
            "id": "repository", "path": repository_path, "capabilities": {"execute": True}
        }]}],
    })
    container = build_container(settings)
    container.jobs._store.initialize()
    registry = build_tool_registry(container)
    tool = registry.get("coordinator_exec_and_wake")
    assert tool.definition.input_schema["required"] == ["project_id", "repository_id", "executable"]
    result = asyncio.run(tool.handler(None, SimpleNamespace(arguments={
        "project_id": "project", "repository_id": "repository",
        "executable": sys.executable, "arguments": ["-c", "print('ok')"],
        "channel_id": "coordinator", "message": "done",
    }), SimpleNamespace(request_id="atomic-request")))
    data = json.loads(result.content[0].text)["data"]
    assert data["job_id"].startswith("job_")
    assert data["state"] == "waiting" and data["durable"] is True
    waiters = container.jobs._store.terminal_waiters()
    assert len(waiters) == 1 and waiters[0]["job_ids"] == (data["job_id"],)


def test_coordinator_exec_and_wake_cancels_job_if_waiter_registration_fails(tmp_path):
    repository_path = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate({
        "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
        "projects": [{"id": "project", "name": "Project", "repositories": [{
            "id": "repository", "path": repository_path, "capabilities": {"execute": True}
        }]}],
    })
    container = build_container(settings)
    container.jobs._store.initialize()
    container.jobs.MAX_TERMINAL_WAITERS = 0
    cancelled = []
    original_cancel = container.jobs.cancel

    async def capture_cancel(repository, job_id):
        cancelled.append(job_id)
        return await original_cancel(repository, job_id)

    container.jobs.cancel = capture_cancel
    tool = build_tool_registry(container).get("coordinator_exec_and_wake")
    try:
        asyncio.run(tool.handler(None, SimpleNamespace(arguments={
            "project_id": "project", "repository_id": "repository",
            "executable": sys.executable, "arguments": ["-c", "print('orphan')"],
            "channel_id": "coordinator",
        }), SimpleNamespace(request_id="atomic-fail")))
    except Exception:
        pass
    else:
        raise AssertionError("waiter capacity failure was expected")
    assert len(cancelled) == 1
    job = container.jobs._store.get_by_id(cancelled[0])
    assert job is not None and job.status == JobStatus.CANCELLED
