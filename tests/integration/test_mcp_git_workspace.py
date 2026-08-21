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


def git(root, *arguments):
    return subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.mark.asyncio
async def test_full_git_workspace_cycle_over_http(tmp_path):
    root = create_git_repository(tmp_path, "service")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", remote], check=True, capture_output=True)
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "--set-upstream", "origin", "main")
    settings = BridgeSettings.model_validate({
        "projects": [{
            "id": "engineering",
            "name": "Engineering",
            "repositories": [{
                "id": "service",
                "path": root,
                "capabilities": {"git_write": True},
            }],
        }],
    })
    app = create_streamable_http_app(create_server(build_container(settings)), settings)
    transport = httpx2.ASGITransport(app=app)

    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            async with streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    scope = {"project_id": "engineering", "repository_id": "service"}
                    created = json.loads((await session.call_tool(
                        "git_branch_create", {**scope, "branch": "feature/dogfood"}
                    )).content[0].text)["data"]
                    assert created["current_branch"] == "main"
                    switched = json.loads((await session.call_tool(
                        "git_branch_switch", {**scope, "branch": "feature/dogfood"}
                    )).content[0].text)["data"]
                    assert switched["branch"] == "feature/dogfood"
                    await session.call_tool("git_branch_switch", {**scope, "branch": "main"})

                    publisher = tmp_path / "publisher"
                    subprocess.run(["git", "clone", remote, publisher], check=True, capture_output=True)
                    git(publisher, "config", "user.name", "Publisher")
                    git(publisher, "config", "user.email", "publisher@example.invalid")
                    git(publisher, "switch", "main")
                    (publisher / "remote.txt").write_text("remote\n", encoding="utf-8")
                    git(publisher, "add", "remote.txt")
                    git(publisher, "commit", "-m", "Remote update")
                    remote_head = git(publisher, "rev-parse", "HEAD")
                    git(publisher, "push", "origin", "main")

                    fetched = json.loads((await session.call_tool(
                        "git_fetch", scope
                    )).content[0].text)["data"]
                    assert fetched["updated_refs"][0]["target"] == remote_head
                    advanced = json.loads((await session.call_tool(
                        "git_fast_forward", scope
                    )).content[0].text)["data"]
                    assert advanced["head"] == remote_head
                    assert advanced["commits_applied"] == 1
