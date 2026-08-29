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
from tests.fixtures.managed_clone import FakeManagedCloneRunner


def payload(result):
    return json.loads(result.content[0].text)


@pytest.mark.asyncio
async def test_clone_is_immediately_available_to_read_apis_and_remains_read_only(tmp_path):
    settings = BridgeSettings.model_validate({
        "managed_repositories": {"root": tmp_path / "managed"},
        "projects": [{"id": "project", "name": "Project"}],
    })
    container = build_container(
        settings, managed_clone_runner=FakeManagedCloneRunner()
    )
    app = create_streamable_http_app(create_server(container), settings, container)
    scope = {"project_id": "project", "repository_id": "upstream"}

    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            async with streamable_http_client(
                "http://127.0.0.1/mcp", http_client=client
            ) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    cloned = payload(await session.call_tool("repository_clone", {
                        **scope,
                        "url": "https://github.com/example/reference.git",
                        "depth": 7,
                    }))
                    assert cloned["data"]["status"] == "cloned"
                    assert "path" not in cloned["data"]

                    described = payload(await session.call_tool(
                        "project_describe", {"project_id": "project"}
                    ))["data"]
                    assert described["repositories"][0]["id"] == "upstream"
                    assert described["repositories"][0]["capabilities"] == {
                        "read": True, "write": False, "git_read": True,
                        "git_write": False, "github_contribute": True,
                        "execute": False,
                    }
                    listed = payload(await session.call_tool("project_list", {}))["data"]
                    assert listed["projects"][0]["repository_count"] == 1
                    assert payload(await session.call_tool(
                        "repository_status", scope
                    ))["ok"] is True
                    assert payload(await session.call_tool(
                        "file_read", {**scope, "path": "README.md"}
                    ))["data"]["content"] == "# repository\n"
                    assert payload(await session.call_tool(
                        "file_search", {**scope, "query": "repository"}
                    ))["data"]["matches"]
                    log = payload(await session.call_tool("git_log", scope))["data"]
                    assert log["commits"][0]["subject"] == "Initial fixture"
                    shown = payload(await session.call_tool(
                        "git_show", {**scope, "revision": "HEAD"}
                    ))["data"]
                    assert shown["commit"]["subject"] == "Initial fixture"
                    assert payload(await session.call_tool("git_fetch", scope))["ok"] is True

                    denied_calls = (
                        ("git_stage", {**scope, "paths": ["README.md"]}),
                        ("git_commit", {
                            **scope, "message": "Denied", "idempotency_key": "denied",
                        }),
                        ("change_plan", {
                            **scope,
                            "operations": [{
                                "type": "create", "path": "denied", "content": "x",
                            }],
                        }),
                        ("change_apply", {
                            **scope, "plan_id": "denied",
                            "base_revision": "sha256:" + "0" * 64,
                            "operations": [{
                                "type": "create", "path": "denied", "content": "x",
                            }],
                        }),
                        ("task_start", {**scope, "task_id": "denied"}),
                    )
                    for tool, arguments in denied_calls:
                        denied = payload(await session.call_tool(tool, arguments))
                        assert denied["error"]["code"] == "PERMISSION_DENIED"
