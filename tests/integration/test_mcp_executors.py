import asyncio
import json

import httpx2
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.container import build_container
from app.executors.antigravity import ProcessResult
from app.runtime import create_server
from app.settings import BridgeSettings
from app.transport import create_streamable_http_app
from tests.fixtures.repositories import create_git_repository


class FakeRunner:
    def __init__(self): self.calls = 0
    async def run(self, argv, **kwargs):
        self.calls += 1
        if argv[-1] == "--version":
            return ProcessResult(0, b"agy 1\n", b"", False, False, False)
        return ProcessResult(0, b'{"status":"SUCCESS","response":"BRIDGE_PROBE_OK"}',
            b"credential=never-return-this", False, False, False)


async def terminal(session, scope, job_id):
    for _ in range(200):
        data = json.loads((await session.call_tool("job_status", {**scope, "job_id": job_id})).content[0].text)["data"]
        if data["status"] in {"succeeded", "failed", "cancelled"}: return data
        await asyncio.sleep(.01)
    raise AssertionError("job did not finish")


@pytest.mark.asyncio
async def test_executor_tools_are_normalized_durable_and_hidden_capable(tmp_path):
    root = create_git_repository(tmp_path, "repo")
    agy = tmp_path / "agy"
    agy.write_text("#!/bin/sh\nprintf '%s\\n' '{\"status\":\"SUCCESS\",\"response\":\"done\"}'\n")
    agy.chmod(0o755)
    settings = BridgeSettings.model_validate({
        "server": {"tool_surface": "compact"},
        "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
        "executors": {
            "antigravity": {
                "enabled": True,
                "executable": agy,
                "quota_cache_path": tmp_path / "antigravity-quota.json",
            }
        },
        "projects": [{"id": "project", "name": "Project", "repositories": [{
            "id": "repo", "path": root, "capabilities": {"execute": True}}]}],
    })
    container = build_container(settings)
    container.executors._antigravity._runner = FakeRunner()
    app = create_streamable_http_app(create_server(container), settings, container)
    scope = {"project_id": "project", "repository_id": "repo"}
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            async with streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    visible = {tool.name for tool in (await session.list_tools()).tools}
                    assert "executor_status" not in visible and "executor_start" not in visible
                    search = json.loads((await session.call_tool("bridge_search", {"query": "executor"})).content[0].text)
                    assert "executor_status" in str(search)
                    schema = json.loads((await session.call_tool("bridge_schema", {"tool_name": "executor_status"})).content[0].text)
                    assert "executor_status" in str(schema)
                    status = json.loads((await session.call_tool("bridge_call", {"tool_name": "executor_status", "arguments": scope})).content[0].text)
                    assert "credential" not in str(status) and status["data"]["executors"][1]["quota_state"] == "unknown"
                    started = json.loads((await session.call_tool("bridge_call", {"tool_name": "executor_start", "arguments": {
                        **scope, "task": "review", "task_kind": "review", "executor": "antigravity"}})).content[0].text)["data"]
                    final = await terminal(session, scope, started["job_id"])
                    output = json.loads((await session.call_tool("job_output", {**scope, "job_id": started["job_id"]})).content[0].text)["data"]
                    assert final["executor"] == "antigravity" and output["executor"] == "antigravity"
                    started_codex = json.loads((await session.call_tool("bridge_call", {"tool_name": "executor_start", "arguments": {
                        **scope, "task": "review", "task_kind": "review", "executor": "codex"}})).content[0].text)["data"]
                    assert started_codex["executor"] == "codex" and started_codex["executor_quota_state"] == "unknown"
