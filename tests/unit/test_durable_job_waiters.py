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
