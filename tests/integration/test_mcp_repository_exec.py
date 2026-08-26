from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx2
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.container import build_container
from app.runtime import create_server
from app.settings import BridgeSettings
from app.transport import create_streamable_http_app
from tests.fixtures.repositories import create_git_repository


async def wait_for(session, scope, job_id):
    for _ in range(300):
        result = await session.call_tool("job_status", {**scope, "job_id": job_id})
        data = json.loads(result.content[0].text)["data"]
        if data["status"] in {"succeeded", "failed", "cancelled"}:
            return data
        await asyncio.sleep(0.01)
    raise AssertionError("job did not finish")


@pytest.mark.asyncio
async def test_repository_exec_uses_durable_job_lifecycle_and_literal_argv(tmp_path):
    repository = create_git_repository(tmp_path, "exec-service")
    settings = BridgeSettings.model_validate({
        "server": {"public_base_url": "https://bridge.example"},
        "jobs": {
            "database_path": tmp_path / "jobs.sqlite3",
            "artifact_directory": tmp_path / "artifacts",
        },
        "projects": [{"id": "project", "name": "Project", "repositories": [{
            "id": "repo", "path": repository,
            "capabilities": {"execute": True},
        }]}],
    })
    container = build_container(settings)
    app = create_streamable_http_app(create_server(container), settings, container)
    scope = {"project_id": "project", "repository_id": "repo"}
    script = (
        "import os,sys; from pathlib import Path; "
        "print(os.getcwd()); print('|'.join(sys.argv[1:])); "
        "Path('result.txt').write_text('immutable')"
    )
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            async with streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    args = {
                        **scope, "executable": sys.executable,
                        "arguments": ["-c", script, ";", "&&", "|", "$(touch pwned)"],
                        "idempotency_key": "same",
                        "artifacts": [{
                            "id": "result", "path": "result.txt",
                            "media_type": "text/plain", "required": True,
                            "max_bytes": 1024,
                        }],
                    }
                    started = json.loads((await session.call_tool("repository_exec", args)).content[0].text)["data"]
                    repeated = json.loads((await session.call_tool("repository_exec", args)).content[0].text)["data"]
                    assert repeated["job_id"] == started["job_id"]
                    conflict_args = {**args, "arguments": ["-c", "print('different')"]}
                    conflict = json.loads((await session.call_tool("repository_exec", conflict_args)).content[0].text)
                    assert conflict["error"]["code"] == "IDEMPOTENCY_CONFLICT"
                    final = await wait_for(session, scope, started["job_id"])
                    assert final["status"] == "succeeded"
                    output = json.loads((await session.call_tool("job_output", {**scope, "job_id": started["job_id"]})).content[0].text)["data"]
                    assert output["stdout"].splitlines()[0] == str(repository)
                    assert ";|&&|||$(touch pwned)" in output["stdout"]
                    assert not (repository / "pwned").exists()
                    listed = json.loads((await session.call_tool("job_artifact_list", {**scope, "job_id": started["job_id"]})).content[0].text)["data"]
                    assert listed["artifacts"][0]["available"] is True
                    exported = await session.call_tool("job_artifact_export", {**scope, "job_id": started["job_id"], "artifact_id": "result"})
                    assert len(exported.content) == 3

                    large_stdin = "payload-" * 2048
                    stdin_args = {**scope, "executable": sys.executable, "arguments": ["-c", "import hashlib,sys; data=sys.stdin.read(); print(len(data)); print(hashlib.sha256(data.encode()).hexdigest())"], "stdin": large_stdin, "idempotency_key": "stdin-large"}
                    stdin_job = json.loads((await session.call_tool("repository_exec", stdin_args)).content[0].text)["data"]["job_id"]
                    assert (await wait_for(session, scope, stdin_job))["status"] == "succeeded"
                    stdin_output = json.loads((await session.call_tool("job_output", {**scope, "job_id": stdin_job})).content[0].text)["data"]["stdout"].splitlines()
                    import hashlib
                    assert stdin_output == [str(len(large_stdin)), hashlib.sha256(large_stdin.encode()).hexdigest()]
                    stdin_conflict = json.loads((await session.call_tool("repository_exec", {**stdin_args, "stdin": large_stdin + "x"})).content[0].text)
                    assert stdin_conflict["error"]["code"] == "IDEMPOTENCY_CONFLICT"

                    failed_job = json.loads((await session.call_tool("repository_exec", {**scope, "executable": sys.executable, "arguments": ["-c", "import sys; print('out'); print('err',file=sys.stderr); sys.exit(3)"]})).content[0].text)["data"]["job_id"]
                    failed = await wait_for(session, scope, failed_job)
                    assert failed["status"] == "failed" and failed["exit_code"] == 3
                    failed_output = json.loads((await session.call_tool("job_output", {**scope, "job_id": failed_job})).content[0].text)["data"]
                    assert failed_output["stdout"] == "out\n" and failed_output["stderr"] == "err\n"

                    timeout_job = json.loads((await session.call_tool("repository_exec", {**scope, "executable": sys.executable, "arguments": ["-c", "import time; time.sleep(5)"], "timeout_seconds": 0.05})).content[0].text)["data"]["job_id"]
                    assert (await wait_for(session, scope, timeout_job))["failure_reason"] == "timeout"

                    cancel_job = json.loads((await session.call_tool("repository_exec", {**scope, "executable": sys.executable, "arguments": ["-c", "import time; time.sleep(5)"]})).content[0].text)["data"]["job_id"]
                    for _ in range(100):
                        state = json.loads((await session.call_tool("job_status", {**scope, "job_id": cancel_job})).content[0].text)["data"]["status"]
                        if state == "running": break
                        await asyncio.sleep(0.01)
                    cancelled = json.loads((await session.call_tool("job_cancel", {**scope, "job_id": cancel_job})).content[0].text)["data"]
                    assert cancelled["status"] == "cancelled"


@pytest.mark.asyncio
async def test_repository_exec_capability_and_queued_restart(tmp_path):
    allowed = create_git_repository(tmp_path, "allowed")
    denied = create_git_repository(tmp_path, "denied")
    settings = BridgeSettings.model_validate({
        "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
        "projects": [{"id": "project", "name": "Project", "repositories": [
            {"id": "allowed", "path": allowed, "capabilities": {"execute": True}},
            {"id": "denied", "path": denied, "capabilities": {"execute": False}},
        ]}],
    })
    first = build_container(settings)
    first.jobs._store.initialize()
    job = await first.jobs.start_execution(
        first.projects.repositories.get("project", "allowed"),
        sys.executable, ["-c", "print('after restart')"], "request",
    )
    with pytest.raises(Exception) as denied_error:
        await first.jobs.start_execution(
            first.projects.repositories.get("project", "denied"), sys.executable, [], "request"
        )
    assert denied_error.value.code.value == "PERMISSION_DENIED"

    rebuilt = build_container(settings)
    await rebuilt.jobs.start()
    try:
        for _ in range(200):
            restored = rebuilt.jobs.status(rebuilt.projects.repositories.get("project", "allowed"), job.job_id)
            if restored.status.value in {"succeeded", "failed", "cancelled", "timed_out"}:
                break
            await asyncio.sleep(0.01)
        assert restored.status.value == "succeeded"
        assert restored.stdout == b"after restart\n"
    finally:
        await rebuilt.jobs.stop()
