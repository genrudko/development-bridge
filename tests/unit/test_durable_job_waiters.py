from __future__ import annotations

import asyncio
import sys

import pytest

from app.capabilities import CapabilityPolicy
from app.jobs import JobService, JobStatus, JobStore
from app.projects import ProjectRegistry
from app.settings import BridgeSettings
from app.tasks import TaskRegistry
from tests.fixtures.repositories import create_git_repository


class Audit:
    def __init__(self):
        self.events = []

    async def emit(self, event):
        self.events.append(event)


def settings_for(tmp_path):
    repo = create_git_repository(tmp_path, "repository")
    return BridgeSettings.model_validate(
        {
            "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
            "projects": [{
                "id": "project",
                "name": "Project",
                "repositories": [{
                    "id": "repository",
                    "path": repo,
                    "capabilities": {"execute": True},
                    "tasks": [{
                        "id": "task",
                        "name": "Task",
                        "executable": sys.executable,
                        "arguments": ["-c", "print('done')"],
                        "timeout_seconds": 5,
                    }],
                }],
            }],
        }
    )


def service_for(settings, audit=None):
    projects = ProjectRegistry.from_settings(settings)
    service = JobService(
        JobStore(settings.jobs.database_path),
        TaskRegistry.from_settings(settings),
        projects,
        CapabilityPolicy(),
        audit or Audit(),
    )
    return service, projects.repositories.get("project", "repository")


async def wait_until(predicate):
    for _ in range(300):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not reached")


@pytest.mark.asyncio
async def test_durable_waiter_survives_service_recreation(tmp_path):
    settings = settings_for(tmp_path)
    first, repo = service_for(settings)
    first._store.initialize()
    seen = []

    async def handler(payload, records, reason):
        seen.append((payload, records[0].job_id, reason))

    first.register_durable_terminal_handler("test", handler)
    job = await first.start_task(repo, "task", "req-1")
    waiter = await first.wake_on_jobs_durable(
        repo, (job.job_id,), "all_terminal", "test", {"marker": "restart"}
    )
    assert waiter["state"] == "waiting"
    assert waiter["durable"] is True
    assert len(first._store.terminal_waiters()) == 1

    second, repo2 = service_for(settings)
    second.register_durable_terminal_handler("test", handler)
    await second.start()
    try:
        await wait_until(lambda: bool(seen))
        assert seen == [({"marker": "restart"}, job.job_id, "all_terminal")]
        assert second.status(repo2, job.job_id).status is JobStatus.SUCCEEDED
        assert second._store.terminal_waiters() == ()
    finally:
        await second.stop()


@pytest.mark.asyncio
async def test_durable_waiter_fires_if_job_finished_before_recovery(tmp_path):
    settings = settings_for(tmp_path)
    first, repo = service_for(settings)
    first._store.initialize()
    seen = []

    async def handler(payload, records, reason):
        seen.append((payload, records[0].status, reason))

    first.register_durable_terminal_handler("test", handler)
    job = await first.start_task(repo, "task", "req-2")
    await first.wake_on_jobs_durable(
        repo, (job.job_id,), "all_terminal", "test", {"marker": "finished"}
    )
    assert first._store.start(job.job_id)
    first._store.finish(job.job_id, JobStatus.SUCCEEDED, exit_code=0)

    second, _ = service_for(settings)
    second.register_durable_terminal_handler("test", handler)
    await second.start()
    try:
        assert seen == [({"marker": "finished"}, JobStatus.SUCCEEDED, "all_terminal")]
        assert second._store.terminal_waiters() == ()
    finally:
        await second.stop()


@pytest.mark.asyncio
async def test_durable_waiter_observes_interrupted_running_job(tmp_path):
    settings = settings_for(tmp_path)
    first, repo = service_for(settings)
    first._store.initialize()
    seen = []

    async def handler(payload, records, reason):
        seen.append((payload, records[0].status, records[0].failure_reason, reason))

    first.register_durable_terminal_handler("test", handler)
    job = await first.start_task(repo, "task", "req-3")
    await first.wake_on_jobs_durable(
        repo,
        (job.job_id,),
        "failure_or_all_terminal",
        "test",
        {"marker": "interrupted"},
    )
    assert first._store.start(job.job_id)

    second, _ = service_for(settings)
    second.register_durable_terminal_handler("test", handler)
    await second.start()
    try:
        assert seen == [
            ({"marker": "interrupted"}, JobStatus.FAILED, "interrupted_by_restart", "failure")
        ]
        assert second._store.terminal_waiters() == ()
    finally:
        await second.stop()


@pytest.mark.asyncio
async def test_cancel_durable_waiters_removes_waiter_without_cancelling_jobs(tmp_path):
    settings = settings_for(tmp_path)
    service, repo = service_for(settings)
    service._store.initialize()
    seen = []

    async def handler(payload, records, reason):
        seen.append((payload, records[0].job_id, reason))

    service.register_durable_terminal_handler("coordinator", handler)
    job1 = await service.start_task(repo, "task", "req-cancel-1")
    job2 = await service.start_task(repo, "task", "req-cancel-2")

    await service.wake_on_jobs_durable(
        repo,
        (job1.job_id,),
        "all_terminal",
        "coordinator",
        {"route_id": "bridge", "generation": 1, "channel_id": "telegram-bridge-g1"},
    )
    await service.wake_on_jobs_durable(
        repo,
        (job2.job_id,),
        "all_terminal",
        "coordinator",
        {"route_id": "other", "generation": 1, "channel_id": "telegram-other-g1"},
    )

    assert len(service._store.terminal_waiters()) == 2

    # Cancel only route_id="bridge"
    res = await service.cancel_durable_waiters(
        handler_name="coordinator",
        payload_match={"route_id": "bridge", "generation": 1},
    )
    assert res["cancelled_count"] == 1
    assert len(service._store.terminal_waiters()) == 1
    remaining = service._store.terminal_waiters()[0]
    assert remaining["payload"]["route_id"] == "other"

    # Crucial Invariant: Jobs are NOT cancelled!
    assert service.status(repo, job1.job_id).status is JobStatus.QUEUED
    assert service.status(repo, job2.job_id).status is JobStatus.QUEUED

    # Run the worker to finish both jobs
    await service.start()
    try:
        await wait_until(lambda: bool(seen))
        assert len(seen) == 1
        assert seen[0][0]["route_id"] == "other"
        # job1 is SUCCEEDED and queryable
        await wait_until(lambda: service.status(repo, job1.job_id).status is JobStatus.SUCCEEDED)
        assert service.status(repo, job1.job_id).status is JobStatus.SUCCEEDED
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_cancel_durable_waiters_persists_across_restart(tmp_path):
    settings = settings_for(tmp_path)
    first, repo = service_for(settings)
    first._store.initialize()
    seen = []

    async def handler(payload, records, reason):
        seen.append(payload)

    first.register_durable_terminal_handler("coordinator", handler)
    job = await first.start_task(repo, "task", "req-persist-cancel")
    await first.wake_on_jobs_durable(
        repo,
        (job.job_id,),
        "all_terminal",
        "coordinator",
        {"route_id": "bridge", "generation": 1, "channel_id": "telegram-bridge-g1"},
    )
    await first.cancel_durable_waiters(
        handler_name="coordinator",
        payload_match={"route_id": "bridge", "generation": 1},
    )

    second, repo2 = service_for(settings)
    second.register_durable_terminal_handler("coordinator", handler)
    await second.start()
    try:
        await wait_until(lambda: second.status(repo2, job.job_id).status is JobStatus.SUCCEEDED)
        assert seen == []
        assert second._store.terminal_waiters() == ()
    finally:
        await second.stop()


@pytest.mark.asyncio
async def test_cancel_durable_waiters_fails_closed_while_callback_in_flight(tmp_path):
    from app.api.errors import BridgeError, ErrorCode

    settings = settings_for(tmp_path)
    service, repo = service_for(settings)
    service._store.initialize()

    callback_started = asyncio.Event()
    callback_unblock = asyncio.Event()
    callback_finished = asyncio.Event()

    async def in_flight_handler(payload, records, reason):
        callback_started.set()
        await callback_unblock.wait()
        callback_finished.set()

    service.register_durable_terminal_handler("coordinator", in_flight_handler)
    job = await service.start_task(repo, "task", "req-in-flight-cancel")
    await service.wake_on_jobs_durable(
        repo,
        (job.job_id,),
        "all_terminal",
        "coordinator",
        {"route_id": "bridge", "generation": 1, "channel_id": "telegram-bridge-g1"},
    )
    assert len(service._store.terminal_waiters()) == 1

    # Start service worker to execute job and invoke callback
    await service.start()
    try:
        # Wait for callback to begin firing and pause
        await callback_started.wait()

        # While callback is in-flight, cancel_durable_waiters must FAIL CLOSED
        with pytest.raises(BridgeError) as exc_info:
            await service.cancel_durable_waiters(
                handler_name="coordinator",
                payload_match={"route_id": "bridge", "generation": 1},
            )
        assert exc_info.value.code == ErrorCode.POLICY_VIOLATION

        # Persisted waiter must NOT have been deleted from store while in-flight
        assert len(service._store.terminal_waiters()) == 1

        # Unblock callback to let it finish
        callback_unblock.set()
        await callback_finished.wait()

        # After callback completes, persisted waiter is deleted
        await wait_until(lambda: len(service._store.terminal_waiters()) == 0)
        assert len(service._store.terminal_waiters()) == 0
    finally:
        callback_unblock.set()
        await service.stop()
