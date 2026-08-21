from __future__ import annotations

import asyncio
import sys

import pytest

from app.audit import AuditOutcome
from app.capabilities import CapabilityPolicy
from app.jobs import JobService, JobStatus, JobStore
from app.projects import ProjectRegistry
from app.settings import BridgeSettings
from app.tasks import TaskRegistry
from tests.fixtures.repositories import create_git_repository


class RecordingAuditSink:
    def __init__(self):
        self.events = []

    async def emit(self, event):
        self.events.append(event)


def configured(tmp_path, script, *, output_limit=1024, timeout=5):
    repository = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate(
        {
            "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
            "projects": [
                {
                    "id": "project",
                    "name": "Project",
                    "repositories": [
                        {
                            "id": "repository",
                            "path": repository,
                            "capabilities": {"execute": True},
                            "tasks": [
                                {
                                    "id": "task",
                                    "name": "Task",
                                    "executable": sys.executable,
                                    "arguments": ["-c", script],
                                    "timeout_seconds": timeout,
                                    "output_limit_bytes": output_limit,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )
    projects = ProjectRegistry.from_settings(settings)
    tasks = TaskRegistry.from_settings(settings)
    audit = RecordingAuditSink()
    jobs = JobService(
        JobStore(settings.jobs.database_path),
        tasks,
        projects,
        CapabilityPolicy(),
        audit,
    )
    return jobs, projects.repositories.get("project", "repository"), audit


async def wait_for_status(jobs, repository, job_id, statuses):
    for _ in range(300):
        job = jobs.status(repository, job_id)
        if job.status in statuses:
            return job
        await asyncio.sleep(0.01)
    raise AssertionError(f"job did not reach {statuses}")


@pytest.mark.asyncio
async def test_live_output_is_available_while_job_runs(tmp_path):
    script = (
        "import sys,time; print('early', flush=True); time.sleep(.3); "
        "print('late', flush=True); print('error', file=sys.stderr, flush=True)"
    )
    jobs, repository, audit = configured(tmp_path, script)
    await jobs.start()
    try:
        started = await jobs.start_task(repository, "task", "req_1")
        await wait_for_status(jobs, repository, started.job_id, {JobStatus.RUNNING})
        for _ in range(100):
            live = jobs.output(repository, started.job_id)
            if b"early" in live.stdout:
                break
            await asyncio.sleep(0.01)
        assert b"early" in live.stdout
        assert live.status is JobStatus.RUNNING

        finished = await wait_for_status(
            jobs, repository, started.job_id, {JobStatus.SUCCEEDED}
        )
        assert finished.stdout == b"early\nlate\n"
        assert finished.stderr == b"error\n"
        assert [event.event for event in audit.events] == ["start", "finish"]
        assert all(event.outcome is AuditOutcome.SUCCESS for event in audit.events)
    finally:
        await jobs.stop()


@pytest.mark.asyncio
async def test_output_is_bounded_and_reports_truncation(tmp_path):
    jobs, repository, _ = configured(
        tmp_path, "import sys; sys.stdout.write('x' * 5000)", output_limit=1024
    )
    await jobs.start()
    try:
        started = await jobs.start_task(repository, "task", "req_2")
        finished = await wait_for_status(
            jobs, repository, started.job_id, {JobStatus.SUCCEEDED}
        )
        assert len(finished.stdout) == 1024
        assert finished.stdout_truncated is True
    finally:
        await jobs.stop()


@pytest.mark.asyncio
async def test_running_job_can_be_cancelled(tmp_path):
    jobs, repository, audit = configured(tmp_path, "import time; time.sleep(10)")
    await jobs.start()
    try:
        started = await jobs.start_task(repository, "task", "req_3")
        await wait_for_status(jobs, repository, started.job_id, {JobStatus.RUNNING})

        cancelled = await jobs.cancel(repository, started.job_id)

        assert cancelled.status is JobStatus.CANCELLED
        assert audit.events[-1].event == "cancel"
    finally:
        await jobs.stop()


@pytest.mark.asyncio
async def test_failed_job_emits_failure_audit(tmp_path):
    jobs, repository, audit = configured(tmp_path, "raise SystemExit(3)")
    await jobs.start()
    try:
        started = await jobs.start_task(repository, "task", "req_failed")
        failed = await wait_for_status(
            jobs, repository, started.job_id, {JobStatus.FAILED}
        )
        assert failed.exit_code == 3
        assert failed.failure_reason == "nonzero_exit"
        assert audit.events[-1].event == "fail"
        assert audit.events[-1].outcome is AuditOutcome.ERROR
    finally:
        await jobs.stop()


@pytest.mark.asyncio
async def test_idempotent_start_returns_same_job(tmp_path):
    jobs, repository, _ = configured(tmp_path, "print('done')")
    await jobs.start()
    try:
        first = await jobs.start_task(
            repository, "task", "req_4", idempotency_key="same"
        )
        second = await jobs.start_task(
            repository, "task", "req_5", idempotency_key="same"
        )
        assert first.job_id == second.job_id
    finally:
        await wait_for_status(jobs, repository, first.job_id, {JobStatus.SUCCEEDED})
        await jobs.stop()
