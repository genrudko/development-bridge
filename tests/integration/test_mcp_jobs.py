from __future__ import annotations

import asyncio
import json
import sys

import httpx2
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.container import build_container
from app.runtime import create_server
from app.settings import BridgeSettings
from app.transport import create_streamable_http_app
from tests.fixtures.repositories import create_git_repository


@pytest.mark.asyncio
async def test_job_api_exposes_live_output_and_queued_cancellation(tmp_path):
    repository = create_git_repository(tmp_path, "service")
    script = "import time; print('early', flush=True); time.sleep(.4); print('late')"
    settings = BridgeSettings.model_validate(
        {
            "server": {"name": "job-test"},
            "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
            "projects": [
                {
                    "id": "engineering",
                    "name": "Engineering",
                    "repositories": [
                        {
                            "id": "service",
                            "path": repository,
                            "capabilities": {"execute": True},
                            "tasks": [
                                {
                                    "id": "test",
                                    "name": "Test",
                                    "executable": sys.executable,
                                    "arguments": ["-c", script],
                                    "timeout_seconds": 5,
                                    "output_limit_bytes": 4096,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )
    container = build_container(settings)
    app = create_streamable_http_app(create_server(container), settings)
    scope = {"project_id": "engineering", "repository_id": "service"}

    transport = httpx2.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=transport, base_url="http://127.0.0.1"
        ) as http_client:
            async with streamable_http_client(
                "http://127.0.0.1/mcp", http_client=http_client
            ) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    listed = await session.call_tool("task_list", scope)
                    listed_payload = json.loads(listed.content[0].text)
                    assert listed_payload["data"]["tasks"][0]["task_id"] == "test"
                    assert "executable" not in listed_payload["data"]["tasks"][0]

                    first = await session.call_tool(
                        "task_start", {**scope, "task_id": "test"}
                    )
                    second = await session.call_tool(
                        "task_start", {**scope, "task_id": "test"}
                    )
                    first_job = json.loads(first.content[0].text)["data"]["job_id"]
                    second_job = json.loads(second.content[0].text)["data"]["job_id"]

                    queued_output = await session.call_tool(
                        "job_output", {**scope, "job_id": second_job}
                    )
                    assert json.loads(queued_output.content[0].text)["data"]["stdout"] == ""
                    cancelled = await session.call_tool(
                        "job_cancel", {**scope, "job_id": second_job}
                    )
                    assert json.loads(cancelled.content[0].text)["data"]["status"] == "cancelled"

                    live_text = ""
                    for _ in range(100):
                        live = await session.call_tool(
                            "job_output", {**scope, "job_id": first_job}
                        )
                        live_text = json.loads(live.content[0].text)["data"]["stdout"]
                        if "early" in live_text:
                            break
                        await asyncio.sleep(0.01)
                    assert "early" in live_text

                    for _ in range(100):
                        status = await session.call_tool(
                            "job_status", {**scope, "job_id": first_job}
                        )
                        status_payload = json.loads(status.content[0].text)["data"]
                        if status_payload["status"] == "succeeded":
                            break
                        await asyncio.sleep(0.01)
                    assert status_payload["status"] == "succeeded"

                    final_output = await session.call_tool(
                        "job_output", {**scope, "job_id": first_job}
                    )
                    output_payload = json.loads(final_output.content[0].text)["data"]
                    assert output_payload["stdout"] == "early\nlate\n"
                    assert output_payload["stdout_truncated"] is False
