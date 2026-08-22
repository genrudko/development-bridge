from __future__ import annotations

import base64
import json
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx2
import pytest
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.api.capability_exports import CapabilityExportRegistry
from app.container import build_container
from app.github import GitHubActionsArtifactExportService, GitHubArtifactSnapshot
from app.runtime import create_server
from app.settings import BridgeSettings
from app.transport import create_streamable_http_app
from tests.fixtures.github_transport import FakeGitHubTransport
from tests.fixtures.repositories import create_git_repository


@pytest.mark.asyncio
async def test_github_actions_artifact_native_export_and_capability_route(
    tmp_path, monkeypatch
):
    repository = create_git_repository(tmp_path, "github-artifact")
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/acme/widgets.git"],
        cwd=repository,
        check=True,
    )
    archive = b"PK\x03\x04byte-exact-actions-archive"
    fake = FakeGitHubTransport()
    metadata_path = "/repos/acme/widgets/actions/artifacts/8"
    metadata = {
        "id": 8,
        "name": "build/output",
        "size_in_bytes": len(archive),
        "expired": False,
        "archive_download_url": "https://signed.example.invalid/secret",
    }
    fake.add("GET", metadata_path, metadata)
    fake.add("GET", metadata_path, metadata)
    fake.downloads[metadata_path + "/zip"] = archive
    settings = BridgeSettings.model_validate(
        {
            "server": {"public_base_url": "https://bridge.example"},
            "github": {"artifact_directory": tmp_path / "github-artifacts"},
            "projects": [{
                "id": "project",
                "name": "Project",
                "repositories": [{
                    "id": "repo",
                    "path": repository,
                    "capabilities": {"git_read": True, "git_write": True},
                }],
            }],
        }
    )
    container = build_container(settings, github_transport=fake)
    clock = {"value": 100.0}
    exports = GitHubActionsArtifactExportService(
        container.github,
        CapabilityExportRegistry[GitHubArtifactSnapshot](
            600,
            monotonic=lambda: clock["value"],
            utcnow=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        ),
        settings.github.artifact_directory,
        "https://bridge.example",
        settings.server.endpoint,
        settings.github.artifact_max_bytes,
    )
    container = replace(container, github_artifact_exports=exports)
    app = create_streamable_http_app(create_server(container), settings, container)

    transport = httpx2.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=transport, base_url="http://127.0.0.1"
        ) as client:
            async with streamable_http_client(
                "http://127.0.0.1/mcp", http_client=client
            ) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "github_actions_artifact_export",
                        {"project_id": "project", "repository_id": "repo", "artifact_id": 8},
                    )
                    data = json.loads(result.content[0].text)["data"]
                    assert isinstance(result.content[1], types.ResourceLink)
                    assert result.content[1].uri == data["export_url"]
                    assert result.content[1].name == "build_output.zip"
                    assert result.content[1].mime_type == "application/zip"
                    assert result.content[1].size == len(archive)
                    assert isinstance(result.content[2], types.EmbeddedResource)
                    assert base64.b64decode(result.content[2].resource.blob) == archive
                    serialized = json.dumps(data)
                    assert str(tmp_path) not in serialized
                    assert "signed.example" not in serialized
                    assert "token" not in serialized.lower()

                    path = urlparse(data["export_url"]).path
                    get = await client.get(path)
                    head = await client.head(path)
                    assert get.status_code == head.status_code == 200
                    assert get.content == archive and head.content == b""
                    assert get.headers["cache-control"] == "private, no-store"
                    assert get.headers["etag"] == f'"{data["sha256"]}"'
                    assert (await client.get(path + "-invalid")).status_code == 404

                    monkeypatch.setattr(
                        "app.tools.github.GITHUB_ARTIFACT_INLINE_LIMIT", 1
                    )
                    link_only = await session.call_tool(
                        "github_actions_artifact_export",
                        {"project_id": "project", "repository_id": "repo", "artifact_id": 8},
                    )
                    assert len(link_only.content) == 2
                    assert isinstance(link_only.content[1], types.ResourceLink)

                    clock["value"] = 701.0
                    assert (await client.get(path)).status_code == 404

    fresh = build_container(settings, github_transport=fake)
    fresh_app = create_streamable_http_app(create_server(fresh), settings, fresh)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=fresh_app), base_url="http://127.0.0.1"
    ) as client:
        assert (await client.get(path)).status_code == 404
    assert len(fake.downloads) == 1
