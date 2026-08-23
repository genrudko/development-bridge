from __future__ import annotations

import sqlite3
import sys

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.container import build_container
from app.settings import BridgeSettings
from tests.fixtures.repositories import create_git_repository


def command_container(tmp_path, *, durable: bool = True):
    repository = create_git_repository(tmp_path, "commands")
    raw = {
        "projects": [{
            "id": "engineering",
            "name": "Engineering",
            "repositories": [{
                "id": "commands",
                "path": repository,
                "capabilities": {"execute": True},
            }],
        }],
    }
    if durable:
        raw["jobs"] = {"database_path": tmp_path / "jobs.sqlite3"}
    container = build_container(BridgeSettings.model_validate(raw))
    repo = container.projects.repositories.get("engineering", "commands")
    return container, repo


@pytest.mark.asyncio
async def test_run_command_requires_global_durable_store(tmp_path):
    container, repository = command_container(tmp_path, durable=False)

    with pytest.raises(BridgeError) as caught:
        await container.commands.run(repository, sys.executable, ["-c", "pass"])
    assert caught.value.code is ErrorCode.JOB_EXECUTION_NOT_CONFIGURED


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["queued", "running"])
async def test_run_command_rejects_when_any_durable_job_is_active(tmp_path, status):
    container, repository = command_container(tmp_path)
    store = container.jobs._store
    store.initialize()
    job, _ = store.create(
        project_id="engineering",
        repository_id="commands",
        task_id="blocking",
        request_id="request",
        idempotency_key=None,
    )
    if status == "running":
        with sqlite3.connect(store._path) as connection:
            connection.execute(
                "UPDATE jobs SET status = 'running' WHERE job_id = ?", (job.job_id,)
            )

    with pytest.raises(BridgeError) as caught:
        await container.commands.run(repository, sys.executable, ["-c", "pass"])
    assert caught.value.code is ErrorCode.JOB_BUSY
    assert "queued or running" in caught.value.message


@pytest.mark.asyncio
async def test_run_command_allows_terminal_jobs_and_reports_nonzero(tmp_path):
    container, repository = command_container(tmp_path)
    store = container.jobs._store
    store.initialize()
    job, _ = store.create(
        project_id="engineering",
        repository_id="commands",
        task_id="terminal",
        request_id="request",
        idempotency_key=None,
    )
    with sqlite3.connect(store._path) as connection:
        connection.execute(
            "UPDATE jobs SET status = 'failed' WHERE job_id = ?", (job.job_id,)
        )

    result = await container.commands.run(
        repository,
        sys.executable,
        ["-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(7)"],
    )
    assert result["exit_code"] == 7
    assert result["stdout"] == "out\n"
    assert result["stderr"] == "err\n"
    assert result["timed_out"] is False


@pytest.mark.asyncio
async def test_run_command_timeout_and_output_truncation(tmp_path):
    container, repository = command_container(tmp_path)
    container.jobs._store.initialize()

    timed_out = await container.commands.run(
        repository,
        sys.executable,
        ["-c", "import time; time.sleep(2)"],
        timeout_seconds=0.02,
    )
    assert timed_out["timed_out"] is True
    assert timed_out["exit_code"] != 0

    truncated = await container.commands.run(
        repository,
        sys.executable,
        ["-c", "import sys; print('o' * 2000); print('e' * 2000, file=sys.stderr)"],
        output_limit_bytes=1024,
    )
    assert len(truncated["stdout"].encode()) == 1024
    assert len(truncated["stderr"].encode()) == 1024
    assert truncated["stdout_truncated"] is True
    assert truncated["stderr_truncated"] is True
