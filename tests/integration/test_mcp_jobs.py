from __future__ import annotations

import asyncio
import base64
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx2
import pytest
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.container import build_container
from app.api.capability_exports import CapabilityExportRegistry
from app.auth import create_owner_verifier
from app.jobs import JobArtifactExportService, JobArtifactExportSubject
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
async def test_job_artifacts_are_listed_exported_and_downloaded_as_snapshots(
    tmp_path, monkeypatch
):
    repository = create_git_repository(tmp_path, "artifact-service")
    script = "from pathlib import Path; Path('report.txt').write_text('captured')"
    settings = BridgeSettings.model_validate(
        {
            "server": {
                "name": "artifact-test",
                "public_base_url": "https://bridge.example",
            },
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
    export_clock = {"value": 100.0}
    container = replace(
        container,
        job_artifact_exports=JobArtifactExportService(
            container.jobs,
            container.projects,
            CapabilityExportRegistry[JobArtifactExportSubject](
                600,
                monotonic=lambda: export_clock["value"],
                utcnow=lambda: datetime(2026, 1, 1, tzinfo=UTC),
            ),
            "https://bridge.example",
            settings.server.endpoint,
        ),
    )
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

                    original_artifact_file = container.jobs.artifact_file
                    authority_calls = []

                    def counted_artifact_file(repository, selected_job, artifact_id):
                        authority_calls.append((selected_job, artifact_id))
                        return original_artifact_file(
                            repository, selected_job, artifact_id
                        )

                    monkeypatch.setattr(
                        container.jobs, "artifact_file", counted_artifact_file
                    )
                    snapshots_before = tuple(
                        path for path in (tmp_path / "artifacts").rglob("*")
                        if path.is_file()
                    )
                    exported = await session.call_tool(
                        "job_artifact_export",
                        {**scope, "job_id": job_id, "artifact_id": "report"},
                    )
                    exported_data = json.loads(exported.content[0].text)["data"]
                    assert authority_calls == [(job_id, "report")]
                    assert isinstance(exported.content[1], types.ResourceLink)
                    assert exported.content[1].uri == exported_data["export_url"]
                    assert exported.content[1].name == exported.content[1].title == "report.txt"
                    assert exported.content[1].mime_type == "text/plain"
                    assert exported.content[1].size == 8
                    assert isinstance(exported.content[2], types.EmbeddedResource)
                    assert isinstance(
                        exported.content[2].resource, types.BlobResourceContents
                    )
                    assert exported.content[2].resource.uri == exported_data["export_url"]
                    assert base64.b64decode(exported.content[2].resource.blob) == b"captured"
                    assert exported_data["artifact"]["artifact_id"] == "report"
                    assert exported_data["file_name"] == "report.txt"
                    assert exported_data["media_type"] == "text/plain"
                    assert exported_data["size_bytes"] == 8
                    assert exported_data["sha256"] == artifact["sha256"]
                    assert str(tmp_path) not in json.dumps(exported_data)
                    assert tuple(
                        path for path in (tmp_path / "artifacts").rglob("*")
                        if path.is_file()
                    ) == snapshots_before

                    monkeypatch.setattr("app.tools.jobs.JOB_ARTIFACT_INLINE_LIMIT", 1)
                    oversized = await session.call_tool(
                        "job_artifact_export",
                        {**scope, "job_id": job_id, "artifact_id": "report"},
                    )
                    assert len(oversized.content) == 2
                    assert isinstance(oversized.content[1], types.ResourceLink)
                    export_path = urlparse(exported_data["export_url"]).path

            (repository / "report.txt").write_text("changed", encoding="utf-8")
            response = await http_client.get(artifact["download_path"])
            exported_get = await http_client.get(export_path)
            exported_head = await http_client.head(export_path)
            invalid = await http_client.get("/mcp/job-artifacts/exports/invalid")

    assert artifact["available"] is True
    assert artifact["size_bytes"] == 8
    assert artifact["sha256"].startswith("sha256:")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["etag"] == f'"{artifact["sha256"]}"'
    assert response.content == b"captured"
    assert exported_get.status_code == exported_head.status_code == 200
    assert exported_get.content == b"captured"
    assert int(exported_head.headers["content-length"]) == 8
    assert exported_get.headers["cache-control"] == "private, no-store"
    assert exported_get.headers["etag"] == f'"{artifact["sha256"]}"'
    assert "report.txt" in exported_get.headers["content-disposition"]
    assert invalid.status_code == 404

    oauth_data = settings.model_dump(mode="python")
    oauth_data["oauth"] = {
        "enabled": True,
        "issuer_url": "http://127.0.0.1",
        "resource_url": "http://127.0.0.1/mcp",
        "database_path": tmp_path / "oauth.sqlite3",
        "owner_verifier": create_owner_verifier("owner-password"),
    }
    oauth_settings = BridgeSettings.model_validate(oauth_data)
    restarted = build_container(oauth_settings)
    restarted_repository = restarted.projects.repositories.get(
        "engineering", "service"
    )
    restarted_data, _, _ = restarted.job_artifact_exports.export(
        restarted_repository, job_id, "report"
    )
    restarted_app = create_streamable_http_app(
        create_server(restarted), oauth_settings, restarted
    )
    assert container.job_artifact_exports.resolve(
        urlparse(exported_data["export_url"]).path.rsplit("/", 1)[-1]
    ) is not None
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=restarted_app),
        base_url="http://127.0.0.1",
    ) as restarted_client:
        old_token = await restarted_client.get(export_path)
        bearer_free = await restarted_client.get(
            urlparse(restarted_data["export_url"]).path
        )
        oauth_protected = await restarted_client.get(artifact["download_path"])
    assert old_token.status_code == 404
    assert bearer_free.status_code == 200
    assert bearer_free.content == b"captured"
    assert oauth_protected.status_code == 401

    export_clock["value"] = 701.0
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as expired_client:
        expired = await expired_client.get(export_path)
    assert expired.status_code == 404


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
