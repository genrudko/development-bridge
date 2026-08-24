import asyncio
import json
import sys
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
    assert data["tool_count"] == 80
    assert catalog == {tool.name for tool in registry.definitions}
    assert "queued status is normal" in data["durable_jobs"]["rule"]
    assert any("batched_messages" in step for step in data["durable_jobs"]["preferred_event_flow"])


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
            }),
            SimpleNamespace(request_id="wake-request"),
        )
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
