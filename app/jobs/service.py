from __future__ import annotations

import asyncio
import os
import signal
import time
from pathlib import Path

from app.api.errors import BridgeError, ErrorCode
from app.audit import AuditEvent, AuditOutcome, AuditSink
from app.capabilities import Capability, CapabilityPolicy
from app.projects import ProjectRegistry, Repository
from app.tasks import TaskProfile, TaskRegistry

from .artifacts import ArtifactStorage
from .models import JobArtifact, JobRecord, JobStatus
from .store import JobStore


class JobService:
    CANCEL_GRACE_SECONDS = 2

    def __init__(
        self,
        store: JobStore | None,
        tasks: TaskRegistry,
        projects: ProjectRegistry,
        policy: CapabilityPolicy,
        audit: AuditSink,
        artifacts: ArtifactStorage | None = None,
    ) -> None:
        self._store = store
        self._tasks = tasks
        self._projects = projects
        self._policy = policy
        self._audit = audit
        self._artifacts = artifacts
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker: asyncio.Task | None = None
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._cancel_requested: set[str] = set()
        self._stopping = False

    async def start(self) -> None:
        if self._store is None or self._worker is not None:
            return
        interrupted = self._store.initialize()
        for job in interrupted:
            await self._emit(job, "fail", AuditOutcome.ERROR, "interrupted_by_restart")
        for job in self._store.queued():
            self._queue.put_nowait(job.job_id)
        self._stopping = False
        self._worker = asyncio.create_task(self._run_worker())

    async def stop(self) -> None:
        if self._worker is None:
            return
        self._stopping = True
        for job_id in tuple(self._processes):
            self._cancel_requested.add(job_id)
            await self._terminate(self._processes[job_id])
        self._queue.put_nowait("")
        await self._queue.join()
        await self._worker
        self._worker = None

    def list_tasks(self, repository: Repository) -> tuple[TaskProfile, ...]:
        self._require_execute(repository)
        return self._tasks.list(repository.project_id, repository.id)

    async def start_task(
        self,
        repository: Repository,
        task_id: str,
        request_id: str,
        *,
        idempotency_key: str | None = None,
    ) -> JobRecord:
        self._require_execute(repository)
        self._tasks.get(repository.project_id, repository.id, task_id)
        if idempotency_key is not None and not 1 <= len(idempotency_key) <= 128:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "idempotency_key is outside the allowed length",
            )
        store = self._require_store()
        job, created = store.create(
            project_id=repository.project_id,
            repository_id=repository.id,
            task_id=task_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
        if created:
            self._queue.put_nowait(job.job_id)
        return job

    def status(self, repository: Repository, job_id: str) -> JobRecord:
        self._require_execute(repository)
        return self._require_store().get(repository.project_id, repository.id, job_id)

    def output(self, repository: Repository, job_id: str) -> JobRecord:
        return self.status(repository, job_id)

    def list_artifacts(
        self, repository: Repository, job_id: str
    ) -> tuple[JobArtifact, ...]:
        job = self.status(repository, job_id)
        stored = self._require_store().artifacts(job_id)
        if stored:
            return stored
        profile = self._tasks.get(job.project_id, job.repository_id, job.task_id)
        return tuple(
            JobArtifact(
                job.job_id,
                declaration.id,
                declaration.path,
                declaration.media_type,
                declaration.required,
                False,
            )
            for declaration in profile.artifacts
        )

    def artifact_file(
        self, repository: Repository, job_id: str, artifact_id: str
    ) -> tuple[JobArtifact, Path]:
        job = self.status(repository, job_id)
        if job.status not in {
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }:
            raise BridgeError(ErrorCode.ARTIFACT_NOT_FOUND, "Artifact is not available")
        artifact = next(
            (
                candidate
                for candidate in self._require_store().artifacts(job_id)
                if candidate.artifact_id == artifact_id and candidate.available
            ),
            None,
        )
        if artifact is None or self._artifacts is None:
            raise BridgeError(ErrorCode.ARTIFACT_NOT_FOUND, "Artifact is not available")
        try:
            path = self._artifacts.path_for(artifact)
        except FileNotFoundError as exc:
            raise BridgeError(
                ErrorCode.ARTIFACT_NOT_FOUND, "Artifact is not available"
            ) from exc
        return artifact, path

    async def cancel(self, repository: Repository, job_id: str) -> JobRecord:
        job = self.status(repository, job_id)
        store = self._require_store()
        if job.status is JobStatus.CANCELLED:
            return job
        if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED}:
            raise BridgeError(
                ErrorCode.JOB_NOT_CANCELLABLE,
                "Completed job cannot be cancelled",
                details={"job_id": job_id, "status": job.status.value},
            )
        if job.status is JobStatus.QUEUED:
            if store.cancel_queued(job_id):
                cancelled = store.get(repository.project_id, repository.id, job_id)
                await self._emit(cancelled, "cancel", AuditOutcome.SUCCESS)
                return cancelled
            job = store.get(repository.project_id, repository.id, job_id)
            if job.status is JobStatus.CANCELLED:
                return job
            if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED}:
                raise BridgeError(
                    ErrorCode.JOB_NOT_CANCELLABLE,
                    "Completed job cannot be cancelled",
                    details={"job_id": job_id, "status": job.status.value},
                )
        self._cancel_requested.add(job_id)
        process = self._processes.get(job_id)
        if process is not None and process.returncode is None:
            await self._terminate(process)
        for _ in range(200):
            current = store.get(repository.project_id, repository.id, job_id)
            if current.status is not JobStatus.RUNNING:
                return current
            await asyncio.sleep(0.01)
        return store.get(repository.project_id, repository.id, job_id)

    async def _run_worker(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                if not self._stopping and job_id:
                    try:
                        await self._execute(job_id)
                    except Exception:
                        store = self._require_store()
                        store.fail_active(job_id, "internal_worker_error")
                        failed = store.get_by_id(job_id)
                        if failed is not None:
                            await self._emit(
                                failed,
                                "fail",
                                AuditOutcome.ERROR,
                                "internal_worker_error",
                            )
            finally:
                self._queue.task_done()
            if self._stopping and self._queue.empty():
                return

    async def _execute(self, job_id: str) -> None:
        store = self._require_store()
        job = store.get_by_id(job_id)
        if job is None or job.status is not JobStatus.QUEUED or not store.start(job_id):
            return
        job = store.get(job.project_id, job.repository_id, job_id)
        if self._stopping:
            store.finish(job_id, JobStatus.CANCELLED, failure_reason="shutdown")
            final = store.get(job.project_id, job.repository_id, job_id)
            await self._emit(final, "cancel", AuditOutcome.SUCCESS)
            return
        try:
            profile = self._tasks.get(job.project_id, job.repository_id, job.task_id)
            repository = self._projects.repositories.get(
                job.project_id, job.repository_id
            )
        except BridgeError:
            store.finish(
                job_id, JobStatus.FAILED, failure_reason="task_profile_unavailable"
            )
            final = store.get_by_id(job_id)
            assert final is not None
            await self._emit(
                final,
                "fail",
                AuditOutcome.ERROR,
                "task_profile_unavailable",
            )
            return
        started = time.perf_counter()
        try:
            process = await asyncio.create_subprocess_exec(
                profile.executable,
                *profile.arguments,
                cwd=repository.root,
                env=self._task_environment(),
                start_new_session=True,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError:
            store.finish(job_id, JobStatus.FAILED, failure_reason="process_start_failed")
            await self._emit(job, "fail", AuditOutcome.ERROR, "process_start_failed")
            return
        self._processes[job_id] = process
        if job_id in self._cancel_requested:
            os.killpg(process.pid, signal.SIGTERM)
        await self._emit(job, "start", AuditOutcome.SUCCESS)
        stdout_reader = asyncio.create_task(
            self._drain(job_id, "stdout", process.stdout, profile.output_limit_bytes)
        )
        stderr_reader = asyncio.create_task(
            self._drain(job_id, "stderr", process.stderr, profile.output_limit_bytes)
        )
        failure_reason = None
        try:
            await asyncio.wait_for(process.wait(), timeout=profile.timeout_seconds)
        except TimeoutError:
            failure_reason = "timeout"
            await self._terminate(process)
        finally:
            await asyncio.gather(stdout_reader, stderr_reader)
            self._processes.pop(job_id, None)

        artifact_failure = None
        if profile.artifacts:
            if self._artifacts is None:
                artifact_failure = "storage_unavailable"
                captured = tuple(
                    JobArtifact(
                        job.job_id,
                        declaration.id,
                        declaration.path,
                        declaration.media_type,
                        declaration.required,
                        False,
                        error="storage_unavailable",
                    )
                    for declaration in profile.artifacts
                )
            else:
                captured = await asyncio.to_thread(
                    self._artifacts.capture, job, profile, repository
                )
            store.save_artifacts(job_id, captured)
            required_failure = next(
                (
                    artifact.error or "unavailable"
                    for artifact in captured
                    if artifact.required and not artifact.available
                ),
                None,
            )
            if required_failure is not None:
                artifact_failure = f"required_artifact_{required_failure}"

        if job_id in self._cancel_requested:
            self._cancel_requested.discard(job_id)
            store.finish(job_id, JobStatus.CANCELLED, exit_code=process.returncode)
            final = store.get(job.project_id, job.repository_id, job_id)
            await self._emit(final, "cancel", AuditOutcome.SUCCESS)
        elif failure_reason is not None or process.returncode != 0 or artifact_failure:
            reason = failure_reason or (
                "nonzero_exit" if process.returncode != 0 else artifact_failure
            )
            store.finish(
                job_id,
                JobStatus.FAILED,
                exit_code=process.returncode,
                failure_reason=reason,
            )
            final = store.get(job.project_id, job.repository_id, job_id)
            await self._emit(final, "fail", AuditOutcome.ERROR, reason, started)
        else:
            store.finish(job_id, JobStatus.SUCCEEDED, exit_code=process.returncode)
            final = store.get(job.project_id, job.repository_id, job_id)
            await self._emit(final, "finish", AuditOutcome.SUCCESS, started=started)

    async def _drain(self, job_id, stream_name, stream, limit) -> None:
        while chunk := await stream.read(64 * 1024):
            self._require_store().append_output(job_id, stream_name, chunk, limit)

    async def _terminate(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        os.killpg(process.pid, signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), timeout=self.CANCEL_GRACE_SECONDS)
        except TimeoutError:
            os.killpg(process.pid, signal.SIGKILL)
            await process.wait()

    async def _emit(
        self,
        job: JobRecord,
        event: str,
        outcome: AuditOutcome,
        error_code: str | None = None,
        started: float | None = None,
    ) -> None:
        await self._audit.emit(
            AuditEvent(
                request_id=job.request_id,
                tool="job_lifecycle",
                outcome=outcome,
                duration_ms=(
                    0
                    if started is None
                    else max(0, int((time.perf_counter() - started) * 1000))
                ),
                project_id=job.project_id,
                repository_id=job.repository_id,
                error_code=error_code,
                event=event,
                job_id=job.job_id,
                task_id=job.task_id,
            )
        )

    @staticmethod
    def _task_environment() -> dict[str, str]:
        return {
            key: value
            for key in ("PATH", "LANG", "LC_ALL")
            if (value := os.environ.get(key)) is not None
        }

    def _require_execute(self, repository: Repository) -> None:
        self._policy.require(
            repository.capabilities,
            Capability.EXECUTE,
            project_id=repository.project_id,
            repository_id=repository.id,
        )

    def _require_store(self) -> JobStore:
        if self._store is None:
            raise BridgeError(ErrorCode.TASK_NOT_FOUND, "No task profiles are configured")
        return self._store
