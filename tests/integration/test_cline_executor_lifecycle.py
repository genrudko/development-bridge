import asyncio
import json

import httpx2
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.container import build_container
from app.runtime import create_server
from app.settings import BridgeSettings, ClineExecutorSettings
from app.transport import create_streamable_http_app
from tests.fixtures.repositories import create_git_repository

WORKER_RESULT = json.dumps(
    {"status": "SUCCESS", "response": "cline worker completed"}
)


async def terminal(session, scope, job_id):
    for _ in range(200):
        data = json.loads(
            (await session.call_tool("job_status", {**scope, "job_id": job_id})).content[0].text
        )["data"]
        if data["status"] in {"succeeded", "failed", "cancelled"}:
            return data
        await asyncio.sleep(0.01)
    raise AssertionError("job did not finish")


def cline_settings(tmp_path):
    executable = tmp_path / "cline"
    executable.write_text("#!/bin/sh\nprintf '%s\\n' '3.0.61'\n")
    executable.chmod(0o755)
    config = tmp_path / "cline-config"
    providers = config / "data" / "settings" / "providers.json"
    providers.parent.mkdir(parents=True, exist_ok=True)
    # Mirror the real account shape: providers is a dict keyed by provider id.
    providers.write_text(
        json.dumps({
            "version": 1,
            "lastUsedProvider": "cline-pass",
            "providers": {"cline": {"tokenSource": "local"}, "cline-pass": {"tokenSource": "local"}},
        }),
        encoding="utf-8",
    )
    return ClineExecutorSettings(
        enabled=True, executable=executable, config_directory=config
    )


@pytest.mark.asyncio
async def test_cline_mcp_executor_lifecycle(tmp_path):
    root = create_git_repository(tmp_path, "repo")
    fake_worker = tmp_path / "fake_cline_worker"
    fake_worker.write_text(f"#!/bin/sh\nprintf '%s\\n' '{WORKER_RESULT}'\n")
    fake_worker.chmod(0o755)

    settings = BridgeSettings.model_validate({
        "server": {"tool_surface": "compact"},
        "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
        "executors": {"cline": {"enabled": False}},
        "projects": [{"id": "project", "name": "Project", "repositories": [{
            "id": "repo", "path": root, "capabilities": {"execute": True}}]}],
    })
    container = build_container(settings)
    container.executors._cline._settings = cline_settings(tmp_path)
    container.executors._cline._python_executable = str(fake_worker)
    container.executors._cline._worker_path = fake_worker

    app = create_streamable_http_app(create_server(container), settings, container)
    scope = {"project_id": "project", "repository_id": "repo"}
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            async with streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    status = json.loads((await session.call_tool(
                        "bridge_call",
                        {"tool_name": "executor_status", "arguments": scope},
                    )).content[0].text)["data"]
                    cline_status = [
                        ex for ex in status["executors"] if ex["executor"] == "cline"
                    ][0]
                    assert cline_status["available"] is True
                    assert cline_status["authenticated"] is True
                    assert cline_status["version"] == "3.0.61"

                    rejected = json.loads((await session.call_tool(
                        "bridge_call",
                        {"tool_name": "executor_start", "arguments": {
                            **scope, "task": "review", "task_kind": "review",
                            "executor": "cline", "model": "bad slug"}},
                    )).content[0].text)
                    assert rejected.get("isError") is True or "error" in rejected

                    started = json.loads((await session.call_tool(
                        "bridge_call",
                        {"tool_name": "executor_start", "arguments": {
                            **scope, "task": "review", "task_kind": "review",
                            "executor": "cline", "model": "anthropic/claude-sonnet-4"}},
                    )).content[0].text)["data"]
                    final = await terminal(session, scope, started["job_id"])
                    assert final["executor"] == "cline"
                    assert final["executor_model"] == "anthropic/claude-sonnet-4"
                    output = json.loads((await session.call_tool(
                        "job_output", {**scope, "job_id": started["job_id"]}
                    )).content[0].text)["data"]

                    default_started = json.loads((await session.call_tool(
                        "bridge_call",
                        {"tool_name": "executor_start", "arguments": {
                            **scope, "task": "implement", "task_kind": "implementation",
                            "executor": "cline"}},
                    )).content[0].text)["data"]
                    default_final = await terminal(session, scope, default_started["job_id"])
                    assert default_final["executor"] == "cline"
                    assert default_final["executor_model"] == "cline-pass/deepseek-v4-flash"
                    assert output["executor"] == "cline"
