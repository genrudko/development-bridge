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
async def test_change_plan_is_self_contained_and_idempotent_over_http(tmp_path):
    repository = create_git_repository(tmp_path, "service")
    settings = BridgeSettings.model_validate(
        {
            "server": {"name": "change-test"},
            "projects": [
                {
                    "id": "engineering",
                    "name": "Engineering",
                    "repositories": [
                        {
                            "id": "service",
                            "path": repository,
                            "capabilities": {"write": True},
                        }
                    ],
                }
            ],
        }
    )
    container = build_container(settings)
    app = create_streamable_http_app(create_server(container), settings)

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
                    planned = await session.call_tool(
                        "change_plan",
                        {
                            "project_id": "engineering",
                            "repository_id": "service",
                            "operations": [
                                {
                                    "type": "create",
                                    "path": "created.txt",
                                    "content": "created\n",
                                }
                            ],
                        },
                    )
                    plan_payload = json.loads(planned.content[0].text)
                    assert plan_payload["ok"] is True
                    plan = plan_payload["data"]
                    assert plan["base_revision"].startswith("sha256:")

                    applied = await session.call_tool("change_apply", plan)
                    repeated = await session.call_tool("change_apply", plan)
                    applied_payload = json.loads(applied.content[0].text)
                    repeated_payload = json.loads(repeated.content[0].text)

                    assert applied_payload["data"]["status"] == "applied"
                    assert repeated_payload["data"]["status"] == "already_applied"
                    assert repository.joinpath("created.txt").read_text() == "created\n"
