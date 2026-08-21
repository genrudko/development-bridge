from __future__ import annotations

import json

import httpx2
import pytest
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.container import build_container
from app.runtime import create_server
from app.settings import BridgeSettings
from app.transport import create_streamable_http_app
from tests.fixtures.repositories import create_git_repository


class RecordingAuditSink:
    def __init__(self):
        self.events = []

    async def emit(self, event):
        self.events.append(event)


class LifecycleClientSession(ClientSession):
    def __init__(self, *args, lifecycle, **kwargs):
        super().__init__(*args, **kwargs)
        self._lifecycle = lifecycle

    async def initialize(self):
        self._lifecycle.append("initialize")
        result = await super().initialize()
        return result

    async def send_notification(self, notification):
        if isinstance(notification, types.InitializedNotification):
            self._lifecycle.append("initialized")
        return await super().send_notification(notification)


def bridge_settings(first, second):
    return BridgeSettings.model_validate(
        {
            "version": 1,
            "server": {"name": "test-development-bridge"},
            "projects": [
                {
                    "id": "engineering",
                    "name": "Engineering",
                    "repositories": [
                        {
                            "id": "first",
                            "path": first,
                            "capabilities": {"read": True, "git_read": True},
                        },
                        {
                            "id": "second",
                            "path": second,
                            "capabilities": {"read": True, "git_read": True},
                        },
                    ],
                }
            ],
        }
    )


@pytest.mark.asyncio
async def test_full_streamable_http_lifecycle_with_two_repositories(tmp_path):
    first = create_git_repository(tmp_path, "first", branch="main")
    second = create_git_repository(tmp_path, "second", branch="develop")
    audit = RecordingAuditSink()
    container = build_container(bridge_settings(first, second), audit=audit)
    server = create_server(container)
    app = create_streamable_http_app(server, container.settings)
    lifecycle = []

    transport = httpx2.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=transport, base_url="http://127.0.0.1"
        ) as http_client:
            async with streamable_http_client(
                "http://127.0.0.1/mcp", http_client=http_client
            ) as (read_stream, write_stream):
                async with LifecycleClientSession(
                    read_stream, write_stream, lifecycle=lifecycle
                ) as session:
                    initialize_result = await session.initialize()
                    assert initialize_result.server_info.name == "test-development-bridge"

                    lifecycle.append("tools/list")
                    listed = await session.list_tools()
                    names = {tool.name for tool in listed.tools}
                    assert {
                        "bridge_info",
                        "project_list",
                        "project_describe",
                        "repository_status",
                    } <= names

                    lifecycle.append("tools/call")
                    projects_result = await session.call_tool("project_list", {})
                    projects_payload = json.loads(projects_result.content[0].text)
                    assert projects_payload["ok"] is True
                    assert projects_payload["data"]["projects"][0]["repository_count"] == 2

                    first_result = await session.call_tool(
                        "repository_status",
                        {"project_id": "engineering", "repository_id": "first"},
                    )
                    second_result = await session.call_tool(
                        "repository_status",
                        {"project_id": "engineering", "repository_id": "second"},
                    )
                    first_payload = json.loads(first_result.content[0].text)
                    second_payload = json.loads(second_result.content[0].text)
                    assert first_payload["data"]["branch"] == "main"
                    assert second_payload["data"]["branch"] == "develop"

    assert lifecycle == ["initialize", "initialized", "tools/list", "tools/call"]
    assert [event.tool for event in audit.events] == [
        "project_list",
        "repository_status",
        "repository_status",
    ]

