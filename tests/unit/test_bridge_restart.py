from __future__ import annotations

import asyncio
import os
import sqlite3

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.bridge_restart import BridgeRestartService
from app.bridge_restart.service import RESTART_COMMAND
from tests.unit.test_commands import command_container


@pytest.mark.asyncio
async def test_idle_restart_schedules_delayed_fixed_command(tmp_path):
    assert RESTART_COMMAND == (
        "/usr/bin/systemd-run",
        "--user",
        "--collect",
        "--unit=development-bridge-self-restart",
        "/usr/bin/sudo",
        "-n",
        "/usr/bin/systemctl",
        "--no-block",
        "restart",
        "development-bridge.service",
    )
    container, _ = command_container(tmp_path)
    container.jobs._store.initialize()
    calls = []
    delay_released = asyncio.Event()

    async def sleep(delay):
        calls.append(("sleep", delay))
        await delay_released.wait()

    async def spawn(*argv, **kwargs):
        calls.append(("spawn", argv, kwargs))
        return object()

    service = BridgeRestartService(container.jobs, sleep=sleep, spawn=spawn)
    result = await service.schedule()

    assert result == {
        "restart_scheduled": True,
        "service": "development-bridge.service",
        "delay_seconds": 1.0,
    }
    await asyncio.sleep(0)
    assert calls == [("sleep", 1.0)]
    assert len(service._tasks) == 1

    delay_released.set()
    await next(iter(service._tasks))
    assert calls[1][0:2] == ("spawn", RESTART_COMMAND)
    runtime_dir = f"/run/user/{os.getuid()}"
    assert calls[1][2] == {
        "stdin": asyncio.subprocess.DEVNULL,
        "stdout": asyncio.subprocess.DEVNULL,
        "stderr": asyncio.subprocess.DEVNULL,
        "env": {
            "XDG_RUNTIME_DIR": runtime_dir,
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path={runtime_dir}/bus",
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["queued", "running"])
async def test_restart_rejects_active_durable_jobs(tmp_path, status):
    container, _ = command_container(tmp_path)
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
    spawned = False

    async def spawn(*args, **kwargs):
        nonlocal spawned
        spawned = True

    service = BridgeRestartService(container.jobs, spawn=spawn)
    with pytest.raises(BridgeError) as caught:
        await service.schedule()

    assert caught.value.code is ErrorCode.JOB_BUSY
    assert spawned is False
    assert service._tasks == set()


@pytest.mark.asyncio
async def test_restart_task_creation_failure_is_structured(tmp_path):
    container, _ = command_container(tmp_path)
    container.jobs._store.initialize()

    def fail_create_task(coroutine):
        raise RuntimeError("event loop unavailable")

    service = BridgeRestartService(container.jobs, create_task=fail_create_task)
    with pytest.raises(BridgeError) as caught:
        await service.schedule()

    assert caught.value.code is ErrorCode.INTERNAL_ERROR
    assert caught.value.message == "Bridge restart could not be scheduled"


@pytest.mark.asyncio
async def test_detached_spawn_failure_is_logged(tmp_path, caplog):
    container, _ = command_container(tmp_path)
    container.jobs._store.initialize()

    async def spawn(*args, **kwargs):
        raise OSError("sudo unavailable")

    service = BridgeRestartService(
        container.jobs,
        delay_seconds=0,
        spawn=spawn,
    )
    await service.schedule()
    task = next(iter(service._tasks))
    with pytest.raises(OSError, match="sudo unavailable"):
        await task
    await asyncio.sleep(0)

    assert "Detached bridge restart process could not be spawned" in caplog.text


@pytest.mark.asyncio
async def test_restart_checkpoint_runs_before_restart_is_scheduled(tmp_path):
    container, _ = command_container(tmp_path)
    container.jobs._store.initialize()
    events = []
    release = asyncio.Event()

    async def checkpoint():
        events.append("checkpoint")

    async def sleep(delay):
        events.append("sleep")
        await release.wait()

    async def spawn(*args, **kwargs):
        events.append("spawn")
        return object()

    service = BridgeRestartService(container.jobs, sleep=sleep, spawn=spawn)
    result = await service.schedule(checkpoint=checkpoint)
    await asyncio.sleep(0)
    assert result["restart_scheduled"] is True
    assert events == ["checkpoint", "sleep"]
    release.set()
    await next(iter(service._tasks))
    assert events == ["checkpoint", "sleep", "spawn"]
