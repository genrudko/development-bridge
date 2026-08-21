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
async def test_git_write_cycle_over_http(tmp_path):
    root = create_git_repository(tmp_path, "service")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", remote], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    (root / "stage-six.txt").write_text("ready\n", encoding="utf-8")
    settings = BridgeSettings.model_validate(
        {
            "server": {"name": "git-write-test"},
            "projects": [
                {
                    "id": "engineering",
                    "name": "Engineering",
                    "repositories": [
                        {
                            "id": "service",
                            "path": root,
                            "capabilities": {"git_read": True, "git_write": True},
                        }
                    ],
                }
            ],
        }
    )
    container = build_container(settings)
    app = create_streamable_http_app(create_server(container), settings, container)

    transport = httpx2.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            async with streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    assert {"git_stage", "git_commit", "git_push_plan", "git_push"} <= {
                        tool.name for tool in listed.tools
                    }
                    staged = json.loads((await session.call_tool("git_stage", {
                        "project_id": "engineering",
                        "repository_id": "service",
                        "paths": ["stage-six.txt"],
                    })).content[0].text)["data"]
                    committed = json.loads((await session.call_tool("git_commit", {
                        "project_id": "engineering",
                        "repository_id": "service",
                        "message": "Add Stage 6 fixture",
                        "idempotency_key": "integration-commit",
                        "expected_head": staged["head"],
                        "expected_index_revision": staged["index_revision"],
                    })).content[0].text)["data"]
                    assert committed["status"] == "committed"

                    plan = json.loads((await session.call_tool("git_push_plan", {
                        "project_id": "engineering",
                        "repository_id": "service",
                        "remote": "origin",
                        "remote_branch": "main",
                    })).content[0].text)["data"]
                    assert plan["action"] == "create"
                    pushed = json.loads((await session.call_tool("git_push", {
                        "project_id": "engineering",
                        "repository_id": "service",
                        "plan_id": plan["plan_id"],
                        "local_branch": plan["local_branch"],
                        "local_head": plan["local_head"],
                        "remote": plan["remote"],
                        "remote_branch": plan["remote_branch"],
                        "remote_head": plan["remote_head"],
                        "set_upstream": True,
                        "idempotency_key": "integration-push",
                    })).content[0].text)["data"]
                    assert pushed["status"] == "pushed"

    remote_head = subprocess.run(
        ["git", "--git-dir", remote, "rev-parse", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert remote_head == committed["head"]
