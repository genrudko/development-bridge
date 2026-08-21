from __future__ import annotations

import json
import subprocess

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
async def test_git_read_tools_use_explicit_repository_over_http(tmp_path):
    first = create_git_repository(tmp_path, "first")
    second = create_git_repository(tmp_path, "second", branch="develop")
    subprocess.run(["git", "tag", "first-tag"], cwd=first, check=True)
    settings = BridgeSettings.model_validate(
        {
            "server": {"name": "git-read-test"},
            "projects": [
                {
                    "id": "engineering",
                    "name": "Engineering",
                    "repositories": [
                        {"id": "first", "path": first, "capabilities": {"git_read": True}},
                        {"id": "second", "path": second, "capabilities": {"git_read": True}},
                    ],
                }
            ],
        }
    )
    container = build_container(settings)
    app = create_streamable_http_app(create_server(container), settings, container)

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
                    listed = await session.list_tools()
                    assert {"git_log", "git_show", "git_diff", "git_refs"} <= {
                        tool.name for tool in listed.tools
                    }

                    first_log = await session.call_tool(
                        "git_log",
                        {"project_id": "engineering", "repository_id": "first"},
                    )
                    second_log = await session.call_tool(
                        "git_log",
                        {"project_id": "engineering", "repository_id": "second"},
                    )
                    first_payload = json.loads(first_log.content[0].text)
                    second_payload = json.loads(second_log.content[0].text)
                    assert first_payload["ok"] is True
                    assert second_payload["ok"] is True
                    assert first_payload["data"]["commits"][0]["subject"] == "Initial fixture"

                    refs = await session.call_tool(
                        "git_refs",
                        {
                            "project_id": "engineering",
                            "repository_id": "first",
                            "kind": "tags",
                        },
                    )
                    refs_payload = json.loads(refs.content[0].text)
                    assert refs_payload["data"]["refs"][0]["name"] == "refs/tags/first-tag"

                    missing = await session.call_tool(
                        "git_show",
                        {
                            "project_id": "engineering",
                            "repository_id": "first",
                            "revision": "missing",
                        },
                    )
                    missing_payload = json.loads(missing.content[0].text)
                    assert missing_payload["ok"] is False
                    assert missing_payload["error"]["code"] == "GIT_REVISION_NOT_FOUND"
