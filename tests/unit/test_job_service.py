from __future__ import annotations

import asyncio
import sys

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.audit import AuditOutcome
from app.capabilities import CapabilityPolicy
from app.jobs import ArtifactStorage, JobService, JobStatus, JobStore
from app.projects import ProjectRegistry
from app.settings import BridgeSettings
from app.tasks import TaskRegistry
from tests.fixtures.repositories import create_git_repository


class RecordingAuditSink:
    def __init__(self):
        self.events = []

    async def emit(self, event):
        self.events.append(event)


def configured(tmp_path, script, *, output_limit=1024, timeout=5, artifacts=()):
    repository = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate(
        {
            "jobs": {
                "database_path": tmp_path / "jobs.sqlite3",
                **(
                    {"artifact_directory": tmp_path / "artifacts"}
                    if artifacts
                    else {}
                ),
            },
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
                                    "artifacts": artifacts,
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
        ArtifactStorage(settings.jobs.artifact_directory) if artifacts else None,
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
async def test_terminal_waiters_are_event_driven_race_safe_and_one_shot(tmp_path):
    jobs, repository, _ = configured(tmp_path, "print('secret-output')")
    jobs._store.initialize()
    first = await jobs.start_task(repository, "task", "req_1")
    second = await jobs.start_task(repository, "task", "req_2")
    wakes = []

    async def wake(records, reason):
        wakes.append(([record.job_id for record in records], reason))

    waiting = await jobs.wake_on_jobs(
        repository, (first.job_id, second.job_id), "all_terminal", wake
    )
    assert waiting["state"] == "waiting"
    assert jobs._store.start(first.job_id)
    await jobs._finish_job(first.job_id, JobStatus.SUCCEEDED)
    assert wakes == []
    assert jobs._store.start(second.job_id)
    await jobs._finish_job(second.job_id, JobStatus.SUCCEEDED)
    assert wakes == [([first.job_id, second.job_id], "all_terminal")]
    await jobs._finish_job(second.job_id, JobStatus.SUCCEEDED)
    assert len(wakes) == 1

    immediate = await jobs.wake_on_jobs(
        repository, (first.job_id,), "all_terminal", wake
    )
    assert immediate["state"] == "fired"
    assert wakes[-1] == ([first.job_id], "all_terminal")

    third = await jobs.start_task(repository, "task", "req_3")
    fourth = await jobs.start_task(repository, "task", "req_4")
    await jobs.wake_on_jobs(
        repository,
        (third.job_id, fourth.job_id),
        "failure_or_all_terminal",
        wake,
    )
    assert jobs._store.start(third.job_id)
    await jobs._finish_job(third.job_id, JobStatus.FAILED)
    assert wakes[-1] == ([third.job_id, fourth.job_id], "failure")

    with pytest.raises(BridgeError) as unknown:
        await jobs.wake_on_jobs(
            repository, ("job_" + "0" * 32,), "all_terminal", wake
        )
    assert unknown.value.code is ErrorCode.JOB_NOT_FOUND

    foreign, _ = jobs._store.create(
        project_id="other-project",
        repository_id="other-repository",
        task_id="task",
        request_id="foreign",
        idempotency_key=None,
    )
    with pytest.raises(BridgeError) as scoped:
        await jobs.wake_on_jobs(repository, (foreign.job_id,), "all_terminal", wake)
    assert scoped.value.code is ErrorCode.JOB_NOT_FOUND


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


@pytest.mark.asyncio
async def test_repository_busy_tracks_active_execution(tmp_path):
    jobs, repository, _ = configured(tmp_path, "print('done')")
    jobs._store.initialize()
    assert jobs.repository_busy(repository) is False
    started = await jobs.start_execution(repository, sys.executable, ["-c", "print('done')"],
        "req", executor="antigravity", executor_model="gemini", executor_quota_state="unknown",
        environment_keys=("HOME",))
    assert jobs.repository_busy(repository) is True
    assert jobs._store.start(started.job_id)
    jobs._store.finish(started.job_id, JobStatus.SUCCEEDED, exit_code=0)
    assert jobs.repository_busy(repository) is False


@pytest.mark.asyncio
async def test_executor_idle_admission_is_atomic_and_idempotent(tmp_path):
    jobs, repository, _ = configured(tmp_path, "print('done')")
    jobs._store.initialize()
    kwargs = dict(idempotency_key="same", executor="antigravity",
        executor_quota_state="unknown", require_repository_idle=True)
    first = await jobs.start_execution(repository, sys.executable, ["-c", "print('one')"], "one", **kwargs)
    repeated = await jobs.start_execution(repository, sys.executable, ["-c", "print('one')"], "two", **kwargs)
    assert repeated.job_id == first.job_id
    with pytest.raises(BridgeError) as busy:
        await jobs.start_execution(repository, sys.executable, ["-c", "print('two')"], "three",
            executor="antigravity", executor_quota_state="unknown", require_repository_idle=True)
    assert busy.value.code is ErrorCode.JOB_BUSY


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("required", "expected_status"),
    [(True, JobStatus.FAILED), (False, JobStatus.SUCCEEDED)],
)
async def test_missing_artifact_only_fails_job_when_required(
    tmp_path, required, expected_status
):
    jobs, repository, _ = configured(
        tmp_path,
        "pass",
        artifacts=(
            {
                "id": "report",
                "path": "missing.txt",
                "media_type": "text/plain",
                "required": required,
            },
        ),
    )
    await jobs.start()
    try:
        started = await jobs.start_task(repository, "task", "req_artifact")
        finished = await wait_for_status(
            jobs, repository, started.job_id, {JobStatus.SUCCEEDED, JobStatus.FAILED}
        )
        artifacts = jobs.list_artifacts(repository, started.job_id)

        assert finished.status is expected_status
        assert artifacts[0].available is False
        if required:
            assert finished.failure_reason == "required_artifact_missing"
    finally:
        await jobs.stop()
