from __future__ import annotations

import asyncio
import hashlib
import json
import os
import signal
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from secrets import token_urlsafe

from app.api.errors import BridgeError, ErrorCode
from app.audit import AuditEvent, AuditOutcome, AuditSink
from app.capabilities import Capability, CapabilityPolicy
from app.projects import ProjectRegistry, Repository
from app.settings import ArtifactSettings
from app.tasks import TaskProfile, TaskRegistry

from .artifacts import ArtifactStorage
from .models import JobArtifact, JobRecord, JobStatus
from .store import JobStore

TerminalCallback = Callable[[tuple[JobRecord, ...], str], Awaitable[None]]


@dataclass(slots=True)
class TerminalWaiter:
    job_ids: tuple[str, ...]
    policy: str
    callback: TerminalCallback


class JobService:
    CANCEL_GRACE_SECONDS = 2
    MAX_TERMINAL_WAITERS = 256

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
        self._admission_lock = asyncio.Lock()
        self._terminal_lock = asyncio.Lock()
        self._terminal_waiters: dict[str, TerminalWaiter] = {}

    async def wake_on_jobs(
        self,
        repository: Repository,
        job_ids: tuple[str, ...],
        policy: str,
        callback: TerminalCallback,
    ) -> dict:
        """Register a race-free, one-shot callback for terminal job transitions."""
        self._require_execute(repository)
        store = self._require_store()
        if not 1 <= len(job_ids) <= 64 or len(set(job_ids)) != len(job_ids):
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "job_ids must contain 1 to 64 unique job IDs",
            )
        if policy not in {"all_terminal", "failure_or_all_terminal"}:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "policy is invalid")
        waiter_id = token_urlsafe(18)
        fire: tuple[tuple[JobRecord, ...], str] | None = None
        async with self._terminal_lock:
            jobs = tuple(
                store.get(repository.project_id, repository.id, job_id)
                for job_id in job_ids
            )
            reason = self._waiter_reason(jobs, policy)
            if reason is None:
                if len(self._terminal_waiters) >= self.MAX_TERMINAL_WAITERS:
                    raise BridgeError(
                        ErrorCode.POLICY_VIOLATION,
                        "Job wake waiter capacity is full",
                        retryable=True,
                    )
                self._terminal_waiters[waiter_id] = TerminalWaiter(
                    job_ids, policy, callback
                )
            else:
                fire = (jobs, reason)
        if fire is not None:
            await callback(*fire)
        return {
            "waiter_id": waiter_id,
            "job_ids": list(job_ids),
            "policy": policy,
            "state": "fired" if fire is not None else "waiting",
        }

    async def _finish_job(
        self,
        job_id: str,
        status: JobStatus,
        *,
        exit_code: int | None = None,
        failure_reason: str | None = None,
    ) -> None:
        async with self._terminal_lock:
            store = self._require_store()
            store.finish(
                job_id, status, exit_code=exit_code, failure_reason=failure_reason
            )
            ready = self._collect_terminal_callbacks(store)
        await self._invoke_terminal_callbacks(ready)

    async def _cancel_queued(self, job_id: str) -> bool:
        async with self._terminal_lock:
            store = self._require_store()
            changed = store.cancel_queued(job_id)
            ready = self._collect_terminal_callbacks(store) if changed else []
        await self._invoke_terminal_callbacks(ready)
        return changed

    async def _fail_active(self, job_id: str, reason: str) -> None:
        async with self._terminal_lock:
            store = self._require_store()
            store.fail_active(job_id, reason)
            ready = self._collect_terminal_callbacks(store)
        await self._invoke_terminal_callbacks(ready)

    def _collect_terminal_callbacks(
        self, store: JobStore
    ) -> list[tuple[TerminalCallback, tuple[JobRecord, ...], str]]:
        ready: list[tuple[TerminalCallback, tuple[JobRecord, ...], str]] = []
        for waiter_id, waiter in tuple(self._terminal_waiters.items()):
            jobs = tuple(store.get_by_id(job_id) for job_id in waiter.job_ids)
            if any(job is None for job in jobs):
                continue
            records = tuple(job for job in jobs if job is not None)
            reason = self._waiter_reason(records, waiter.policy)
            if reason is not None:
                del self._terminal_waiters[waiter_id]
                ready.append((waiter.callback, records, reason))
        return ready

    @staticmethod
    async def _invoke_terminal_callbacks(
        ready: list[tuple[TerminalCallback, tuple[JobRecord, ...], str]],
    ) -> None:
        # Removal happens before invocation, so duplicate transitions cannot re-fire.
        for callback, jobs, reason in ready:
            await callback(jobs, reason)

    @staticmethod
    def _waiter_reason(jobs: tuple[JobRecord, ...], policy: str) -> str | None:
        terminal = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
        if policy == "failure_or_all_terminal" and any(
            job.status in {JobStatus.FAILED, JobStatus.CANCELLED} for job in jobs
        ):
            return "failure"
        if all(job.status in terminal for job in jobs):
            return "all_terminal"
        return None

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
        async with self._admission_lock:
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

    async def start_execution(
        self,
        repository: Repository,
        executable: str,
        arguments: list[str] | tuple[str, ...],
        request_id: str,
        *,
        timeout_seconds: float = 300,
        output_limit_bytes: int = 262_144,
        artifacts: list[dict] | tuple[dict, ...] = (),
        idempotency_key: str | None = None,
    ) -> JobRecord:
        self._require_execute(repository)
        if not isinstance(executable, str) or not 1 <= len(executable) <= 4096 or "\0" in executable:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "executable is invalid")
        if not isinstance(arguments, (list, tuple)) or len(arguments) > 256 or any(
            not isinstance(value, str) or len(value) > 4096 or "\0" in value
            for value in arguments
        ):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "arguments are invalid")
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or not 0 < timeout_seconds <= 3600:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "timeout_seconds is invalid")
        if not isinstance(output_limit_bytes, int) or isinstance(output_limit_bytes, bool) or not 1024 <= output_limit_bytes <= 1_048_576:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "output_limit_bytes is invalid")
        if not isinstance(artifacts, (list, tuple)) or len(artifacts) > 32:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "artifacts are invalid")
        try:
            configured_artifacts = tuple(
                ArtifactSettings.model_validate(item) for item in artifacts
            )
        except Exception as exc:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "artifact declaration is invalid") from exc
        identifiers = [artifact.id for artifact in configured_artifacts]
        if len(identifiers) != len(set(identifiers)):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "artifact ids must be unique")
        if idempotency_key is not None and not 1 <= len(idempotency_key) <= 128:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "idempotency_key is invalid")
        payload = {
            "project_id": repository.project_id,
            "repository_id": repository.id,
            "executable": executable,
            "arguments": list(arguments),
            "timeout_seconds": float(timeout_seconds),
            "output_limit_bytes": output_limit_bytes,
            "artifacts": [
                {
                    "id": item.id,
                    "path": item.path,
                    "media_type": item.media_type,
                    "required": item.required,
                    "max_bytes": item.max_bytes,
                }
                for item in configured_artifacts
            ],
        }
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        store = self._require_store(execution=True)
        async with self._admission_lock:
            job, created = store.create_execution(
                project_id=repository.project_id,
                repository_id=repository.id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                payload_json=payload_json,
                payload_digest=hashlib.sha256(payload_json.encode()).hexdigest(),
            )
            if created:
                self._queue.put_nowait(job.job_id)
        return job

    async def run_when_globally_idle(
        self,
        operation: Callable[[], Awaitable[object]],
        *,
        operation_name: str = "run_command",
    ):
        """Serialize synchronous execution against all durable job admissions."""
        async with self._admission_lock:
            if self._store is None:
                raise BridgeError(
                    ErrorCode.JOB_EXECUTION_NOT_CONFIGURED,
                    f"{operation_name} requires a configured durable job store",
                )
            if self._store.has_active():
                raise BridgeError(
                    ErrorCode.JOB_BUSY,
                    f"{operation_name} is unavailable while a durable job is queued or running",
                    retryable=True,
                )
            return await operation()

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
        profile = self._require_store().execution_profile(job_id)
        if profile is None:
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
            if await self._cancel_queued(job_id):
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
                    except Exception:  # noqa: BLE001 - contain worker/task failures
                        store = self._require_store()
                        await self._fail_active(job_id, "internal_worker_error")
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
            await self._finish_job(
                job_id, JobStatus.CANCELLED, failure_reason="shutdown"
            )
            final = store.get(job.project_id, job.repository_id, job_id)
            await self._emit(final, "cancel", AuditOutcome.SUCCESS)
            return
        try:
            profile = store.execution_profile(job_id)
            if profile is None:
                profile = self._tasks.get(job.project_id, job.repository_id, job.task_id)
            repository = self._projects.repositories.get(
                job.project_id, job.repository_id
            )
        except BridgeError:
            await self._finish_job(
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
            await self._finish_job(
                job_id, JobStatus.FAILED, failure_reason="process_start_failed"
            )
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
            await self._finish_job(
                job_id, JobStatus.CANCELLED, exit_code=process.returncode
            )
            final = store.get(job.project_id, job.repository_id, job_id)
            await self._emit(final, "cancel", AuditOutcome.SUCCESS)
        elif failure_reason is not None or process.returncode != 0 or artifact_failure:
            reason = failure_reason or (
                "nonzero_exit" if process.returncode != 0 else artifact_failure
            )
            await self._finish_job(
                job_id,
                JobStatus.FAILED,
                exit_code=process.returncode,
                failure_reason=reason,
            )
            final = store.get(job.project_id, job.repository_id, job_id)
            await self._emit(final, "fail", AuditOutcome.ERROR, reason, started)
        else:
            await self._finish_job(
                job_id, JobStatus.SUCCEEDED, exit_code=process.returncode
            )
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

    def _require_store(self, *, execution: bool = False) -> JobStore:
        if self._store is None:
            if execution:
                raise BridgeError(
                    ErrorCode.JOB_EXECUTION_NOT_CONFIGURED,
                    "jobs.database_path is required for repository execution",
                )
            raise BridgeError(ErrorCode.TASK_NOT_FOUND, "No task profiles are configured")
        return self._store
