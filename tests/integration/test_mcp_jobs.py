from __future__ import annotations

import asyncio
import base64
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


SMALL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


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
    app = create_streamable_http_app(create_server(container), settings, container)
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


@pytest.mark.asyncio
async def test_job_artifacts_are_listed_and_downloaded_as_snapshots(tmp_path):
    repository = create_git_repository(tmp_path, "artifact-service")
    script = "from pathlib import Path; Path('report.txt').write_text('captured')"
    settings = BridgeSettings.model_validate(
        {
            "server": {"name": "artifact-test"},
            "jobs": {
                "database_path": tmp_path / "jobs.sqlite3",
                "artifact_directory": tmp_path / "artifacts",
            },
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
                                    "id": "report",
                                    "name": "Report",
                                    "executable": sys.executable,
                                    "arguments": ["-c", script],
                                    "artifacts": [
                                        {
                                            "id": "report",
                                            "path": "report.txt",
                                            "media_type": "text/plain",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )
    container = build_container(settings)
    app = create_streamable_http_app(create_server(container), settings, container)
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
                    started = await session.call_tool(
                        "task_start", {**scope, "task_id": "report"}
                    )
                    job_id = json.loads(started.content[0].text)["data"]["job_id"]
                    for _ in range(100):
                        status = await session.call_tool(
                            "job_status", {**scope, "job_id": job_id}
                        )
                        if json.loads(status.content[0].text)["data"]["status"] == "succeeded":
                            break
                        await asyncio.sleep(0.01)

                    listed = await session.call_tool(
                        "job_artifact_list", {**scope, "job_id": job_id}
                    )
                    artifact = json.loads(listed.content[0].text)["data"]["artifacts"][0]

            (repository / "report.txt").write_text("changed", encoding="utf-8")
            response = await http_client.get(artifact["download_path"])

    assert artifact["available"] is True
    assert artifact["size_bytes"] == 8
    assert artifact["sha256"].startswith("sha256:")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["etag"] == f'"{artifact["sha256"]}"'
    assert response.content == b"captured"


@pytest.mark.asyncio
async def test_job_artifact_view_returns_snapshot_as_mcp_image(tmp_path):
    repository = create_git_repository(tmp_path, "visual-artifact-service")
    encoded_png = base64.b64encode(SMALL_PNG).decode()
    script = (
        "import base64; from pathlib import Path; "
        f"Path('screenshot.png').write_bytes(base64.b64decode('{encoded_png}'))"
    )
    settings = BridgeSettings.model_validate(
        {
            "server": {"name": "visual-artifact-test"},
            "jobs": {
                "database_path": tmp_path / "jobs.sqlite3",
                "artifact_directory": tmp_path / "artifacts",
            },
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
                                    "id": "screenshot",
                                    "name": "Screenshot",
                                    "executable": sys.executable,
                                    "arguments": ["-c", script],
                                    "artifacts": [
                                        {
                                            "id": "screenshot",
                                            "path": "screenshot.png",
                                            "media_type": "image/png",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )
    container = build_container(settings)
    app = create_streamable_http_app(create_server(container), settings, container)
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
                    started = await session.call_tool(
                        "task_start", {**scope, "task_id": "screenshot"}
                    )
                    job_id = json.loads(started.content[0].text)["data"]["job_id"]
                    for _ in range(100):
                        status = await session.call_tool(
                            "job_status", {**scope, "job_id": job_id}
                        )
                        if json.loads(status.content[0].text)["data"]["status"] == "succeeded":
                            break
                        await asyncio.sleep(0.01)

                    viewed = await session.call_tool(
                        "job_artifact_view",
                        {**scope, "job_id": job_id, "artifact_id": "screenshot"},
                    )

    envelope = json.loads(viewed.content[0].text)
    assert envelope["data"]["job_id"] == job_id
    assert envelope["data"]["artifact"]["artifact_id"] == "screenshot"
    assert viewed.content[1].type == "image"
    assert viewed.content[1].mime_type == "image/png"
    assert base64.b64decode(viewed.content[1].data) == SMALL_PNG
