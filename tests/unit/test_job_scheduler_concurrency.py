from __future__ import annotations

import asyncio
import sys

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.audit import LoggingAuditSink
from app.capabilities import CapabilityPolicy
from app.jobs import JobService, JobStatus, JobStore
from app.projects import ProjectRegistry
from app.settings import BridgeSettings
from app.tasks import TaskRegistry
from tests.fixtures.repositories import create_git_repository


def configured_scheduler(tmp_path, *, max_concurrency=8):
    repositories = []
    for repo_id in ("repo-a", "repo-b", "repo-c"):
        path = create_git_repository(tmp_path, repo_id)
        repositories.append({
            "id": repo_id,
            "path": path,
            "capabilities": {"execute": True},
            "tasks": [{
                "id": "task",
                "name": "Task",
                "executable": sys.executable,
                "arguments": ["-c", "import time; time.sleep(.4); print('done')"],
                "timeout_seconds": 5,
            }],
        })
    settings = BridgeSettings.model_validate({
        "jobs": {
            "database_path": tmp_path / "jobs.sqlite3",
            "max_concurrency": max_concurrency,
        },
        "projects": [{"id": "project", "name": "Project", "repositories": repositories}],
    })
    projects = ProjectRegistry.from_settings(settings)
    jobs = JobService(
        JobStore(settings.jobs.database_path),
        TaskRegistry.from_settings(settings),
        projects,
        CapabilityPolicy(),
        LoggingAuditSink(),
        max_concurrency=settings.jobs.max_concurrency,
    )
    return jobs, tuple(
        projects.repositories.get("project", repo_id)
        for repo_id in ("repo-a", "repo-b", "repo-c")
    )


async def wait_status(jobs, repository, job_id, expected):
    for _ in range(300):
        record = jobs.status(repository, job_id)
        if record.status in expected:
            return record
        await asyncio.sleep(.01)
    raise AssertionError(f"job {job_id} did not reach {expected}")


@pytest.mark.asyncio
async def test_scheduler_runs_different_repositories_in_parallel_but_serializes_same_repo(tmp_path):
    jobs, (repo_a, repo_b, _) = configured_scheduler(tmp_path)
    assert jobs._max_concurrency == 8
    await jobs.start()
    try:
        a1 = await jobs.start_task(repo_a, "task", "a1")
        a2 = await jobs.start_task(repo_a, "task", "a2")
        b1 = await jobs.start_task(repo_b, "task", "b1")
        await wait_status(jobs, repo_a, a1.job_id, {JobStatus.RUNNING})
        await wait_status(jobs, repo_b, b1.job_id, {JobStatus.RUNNING})
        assert jobs.status(repo_a, a2.job_id).status is JobStatus.QUEUED
        await wait_status(jobs, repo_a, a1.job_id, {JobStatus.SUCCEEDED})
        await wait_status(jobs, repo_a, a2.job_id, {JobStatus.SUCCEEDED})
        await wait_status(jobs, repo_b, b1.job_id, {JobStatus.SUCCEEDED})
    finally:
        await jobs.stop()


@pytest.mark.asyncio
async def test_scheduler_respects_global_concurrency_limit(tmp_path):
    jobs, repositories = configured_scheduler(tmp_path, max_concurrency=2)
    await jobs.start()
    try:
        started = [
            await jobs.start_task(repo, "task", f"r{idx}")
            for idx, repo in enumerate(repositories)
        ]
        for _ in range(100):
            states = [
                jobs.status(repo, job.job_id).status
                for repo, job in zip(repositories, started)
            ]
            if states.count(JobStatus.RUNNING) == 2:
                break
            await asyncio.sleep(.01)
        assert states.count(JobStatus.RUNNING) == 2
        assert states.count(JobStatus.QUEUED) == 1
        for repo, job in zip(repositories, started):
            await wait_status(jobs, repo, job.job_id, {JobStatus.SUCCEEDED})
    finally:
        await jobs.stop()


@pytest.mark.asyncio
async def test_repository_idle_gate_does_not_block_other_repositories(tmp_path):
    jobs, (repo_a, repo_b, _) = configured_scheduler(tmp_path)
    await jobs.start()
    try:
        active = await jobs.start_task(repo_a, "task", "active")
        await wait_status(jobs, repo_a, active.job_id, {JobStatus.RUNNING})

        async def operation():
            return "ok"

        assert await jobs.run_when_repository_idle(repo_b, operation) == "ok"
        with pytest.raises(BridgeError) as busy:
            await jobs.run_when_repository_idle(repo_a, operation)
        assert busy.value.code is ErrorCode.JOB_BUSY
    finally:
        await jobs.stop()


def test_default_job_concurrency_is_eight():
    assert BridgeSettings().jobs.max_concurrency == 8
