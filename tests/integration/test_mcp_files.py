from __future__ import annotations

import json

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
async def test_file_tools_use_the_explicit_repository_over_http(tmp_path):
    first = create_git_repository(tmp_path, "first")
    second = create_git_repository(tmp_path, "second")
    (first / "value.txt").write_text("first needle\n", encoding="utf-8")
    (second / "value.txt").write_text("second needle\n", encoding="utf-8")
    settings = BridgeSettings.model_validate(
        {
            "server": {"name": "file-test"},
            "projects": [
                {
                    "id": "engineering",
                    "name": "Engineering",
                    "repositories": [
                        {"id": "first", "path": first, "capabilities": {"read": True}},
                        {"id": "second", "path": second, "capabilities": {"read": True}},
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
                    assert {"file_list", "file_read", "file_search"} <= {
                        tool.name for tool in listed.tools
                    }

                    first_result = await session.call_tool(
                        "file_read",
                        {
                            "project_id": "engineering",
                            "repository_id": "first",
                            "path": "value.txt",
                        },
                    )
                    second_result = await session.call_tool(
                        "file_read",
                        {
                            "project_id": "engineering",
                            "repository_id": "second",
                            "path": "value.txt",
                        },
                    )
                    first_payload = json.loads(first_result.content[0].text)
                    second_payload = json.loads(second_result.content[0].text)
                    assert first_payload["data"]["content"] == "first needle\n"
                    assert second_payload["data"]["content"] == "second needle\n"

                    rejected = await session.call_tool(
                        "file_read",
                        {
                            "project_id": "engineering",
                            "repository_id": "first",
                            "path": "../second/value.txt",
                        },
                    )
                    rejected_payload = json.loads(rejected.content[0].text)
                    assert rejected_payload["ok"] is False
                    assert rejected_payload["error"]["code"] == "POLICY_VIOLATION"
