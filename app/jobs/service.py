from __future__ import annotations

import asyncio
import hashlib
import json
import os
import signal
import time
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
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
DurableTerminalHandler = Callable[[dict[str, object], tuple[JobRecord, ...], str], Awaitable[None]]


@dataclass(slots=True)
class TerminalWaiter:
    waiter_id: str
    job_ids: tuple[str, ...]
    policy: str
    callback: TerminalCallback
    durable: bool = False


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
        *,
        max_concurrency: int = 8,
    ) -> None:
        self._store = store
        self._tasks = tasks
        self._projects = projects
        self._policy = policy
        self._audit = audit
        self._artifacts = artifacts
        if not isinstance(max_concurrency, int) or isinstance(max_concurrency, bool) or not 1 <= max_concurrency <= 32:
            raise ValueError("max_concurrency must be between 1 and 32")
        self._max_concurrency = max_concurrency
        self._pending: deque[str] = deque()
        self._dispatch_event = asyncio.Event()
        self._worker: asyncio.Task | None = None
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._active_repositories: set[tuple[str, str]] = set()
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._cancel_requested: set[str] = set()
        self._stopping = False
        self._global_admission_lock = asyncio.Lock()
        self._admission_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._terminal_lock = asyncio.Lock()
        self._terminal_waiters: dict[str, TerminalWaiter] = {}
        self._durable_terminal_handlers: dict[str, DurableTerminalHandler] = {}

    def register_durable_terminal_handler(self, name: str, handler: DurableTerminalHandler) -> None:
        if not isinstance(name, str) or not 1 <= len(name) <= 64 or any(not (char.isalnum() or char in "-_") for char in name):
            raise ValueError("durable terminal handler name is invalid")
        if self._worker is not None:
            raise RuntimeError("durable terminal handlers must be registered before start")
        self._durable_terminal_handlers[name] = handler

    async def wake_on_jobs(
        self,
        repository: Repository,
        job_ids: tuple[str, ...],
        policy: str,
        callback: TerminalCallback,
    ) -> dict:
        """Register a race-free, one-shot in-process callback."""
        return await self._register_terminal_waiter(
            repository, job_ids, policy, callback
        )

    async def wake_on_jobs_durable(
        self,
        repository: Repository,
        job_ids: tuple[str, ...],
        policy: str,
        handler_name: str,
        payload: dict[str, object],
    ) -> dict:
        """Register a terminal callback that is restored after Bridge restart."""
        handler = self._durable_terminal_handlers.get(handler_name)
        if handler is None:
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                "Durable terminal handler is not registered",
                details={"handler_name": handler_name},
            )
        if not isinstance(payload, dict):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "durable waiter payload is invalid")
        try:
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "durable waiter payload is not JSON serializable",
            ) from exc
        if len(encoded.encode("utf-8")) > 16_384:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT, "durable waiter payload is too large"
            )
        payload_copy = json.loads(encoded)

        async def callback(records: tuple[JobRecord, ...], reason: str) -> None:
            await handler(payload_copy, records, reason)

        return await self._register_terminal_waiter(
            repository,
            job_ids,
            policy,
            callback,
            durable_handler=handler_name,
            durable_payload=payload_copy,
        )

    async def _register_terminal_waiter(
        self,
        repository: Repository,
        job_ids: tuple[str, ...],
        policy: str,
        callback: TerminalCallback,
        *,
        durable_handler: str | None = None,
        durable_payload: dict[str, object] | None = None,
    ) -> dict:
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
        durable = durable_handler is not None
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
                waiter = TerminalWaiter(
                    waiter_id, job_ids, policy, callback, durable=durable
                )
                if durable:
                    assert durable_handler is not None
                    assert durable_payload is not None
                    store.save_terminal_waiter(
                        waiter_id=waiter_id,
                        project_id=repository.project_id,
                        repository_id=repository.id,
                        job_ids=job_ids,
                        policy=policy,
                        handler_name=durable_handler,
                        payload=durable_payload,
                    )
                self._terminal_waiters[waiter_id] = waiter
            else:
                fire = (jobs, reason)
        if fire is not None:
            await callback(*fire)
        return {
            "waiter_id": waiter_id,
            "job_ids": list(job_ids),
            "policy": policy,
            "state": "fired" if fire is not None else "waiting",
            "durable": durable,
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
    ) -> list[tuple[TerminalWaiter, tuple[JobRecord, ...], str]]:
        ready: list[tuple[TerminalWaiter, tuple[JobRecord, ...], str]] = []
        for waiter_id, waiter in tuple(self._terminal_waiters.items()):
            jobs = tuple(store.get_by_id(job_id) for job_id in waiter.job_ids)
            if any(job is None for job in jobs):
                continue
            records = tuple(job for job in jobs if job is not None)
            reason = self._waiter_reason(records, waiter.policy)
            if reason is not None:
                del self._terminal_waiters[waiter_id]
                ready.append((waiter, records, reason))
        return ready

    async def _invoke_terminal_callbacks(
        self,
        ready: list[tuple[TerminalWaiter, tuple[JobRecord, ...], str]],
    ) -> None:
        for waiter, jobs, reason in ready:
            try:
                await waiter.callback(jobs, reason)
            except Exception:
                if waiter.durable:
                    async with self._terminal_lock:
                        self._terminal_waiters.setdefault(waiter.waiter_id, waiter)
                raise
            else:
                if waiter.durable:
                    self._require_store().delete_terminal_waiter(waiter.waiter_id)

    async def _restore_durable_terminal_waiters(self) -> None:
        store = self._require_store()
        async with self._terminal_lock:
            for item in store.terminal_waiters():
                waiter_id = str(item["waiter_id"])
                if waiter_id in self._terminal_waiters:
                    continue
                handler_name = str(item["handler_name"])
                handler = self._durable_terminal_handlers.get(handler_name)
                if handler is None:
                    continue
                payload = dict(item["payload"])
                job_ids = tuple(str(value) for value in item["job_ids"])
                policy = str(item["policy"])

                async def callback(
                    records: tuple[JobRecord, ...],
                    reason: str,
                    *,
                    _handler: DurableTerminalHandler = handler,
                    _payload: dict[str, object] = payload,
                ) -> None:
                    await _handler(_payload, records, reason)

                self._terminal_waiters[waiter_id] = TerminalWaiter(
                    waiter_id,
                    job_ids,
                    policy,
                    callback,
                    durable=True,
                )
            ready = self._collect_terminal_callbacks(store)
        await self._invoke_terminal_callbacks(ready)

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
        await self._restore_durable_terminal_waiters()
        self._pending.clear()
        for job in self._store.queued():
            self._pending.append(job.job_id)
        self._stopping = False
        self._worker = asyncio.create_task(self._run_worker())
        self._dispatch_event.set()

    async def stop(self) -> None:
        if self._worker is None:
            return
        self._stopping = True
        for job_id in tuple(self._processes):
            self._cancel_requested.add(job_id)
            await self._terminate(self._processes[job_id])
        self._dispatch_event.set()
        active = tuple(self._active_tasks.values())
        if active:
            await asyncio.gather(*active, return_exceptions=True)
        self._dispatch_event.set()
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
        async with self._admission(repository):
            job, created = store.create(
                project_id=repository.project_id,
                repository_id=repository.id,
                task_id=task_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
            )
            if created:
                self._enqueue(job.job_id)
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
        stdin: str | None = None,
        idempotency_key: str | None = None,
        executor: str | None = None,
        executor_model: str | None = None,
        executor_quota_state: str | None = None,
        environment_keys: tuple[str, ...] = (),
        require_repository_idle: bool = False,
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
        if stdin is not None and (not isinstance(stdin, str) or len(stdin.encode("utf-8")) > 1_048_576):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "stdin is invalid")
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
        for value in (executor, executor_model, executor_quota_state):
            if value is not None and (not isinstance(value, str) or not 1 <= len(value) <= 128):
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "executor attribution is invalid")
        if (not isinstance(environment_keys, tuple) or len(environment_keys) != len(set(environment_keys))
                or any(key not in {"HOME", "SSH_CONNECTION"} for key in environment_keys)):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "environment_keys are invalid")
        payload = {
            "project_id": repository.project_id,
            "repository_id": repository.id,
            "executable": executable,
            "arguments": list(arguments),
            "timeout_seconds": float(timeout_seconds),
            "output_limit_bytes": output_limit_bytes,
            "stdin": stdin,
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
            "executor": executor,
            "executor_model": executor_model,
            "executor_quota_state": executor_quota_state,
            "environment_keys": list(environment_keys),
        }
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        store = self._require_store(execution=True)
        async with self._admission(repository):
            job, created = store.create_execution(
                project_id=repository.project_id,
                repository_id=repository.id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                payload_json=payload_json,
                payload_digest=hashlib.sha256(payload_json.encode()).hexdigest(),
                executor=executor,
                executor_model=executor_model,
                executor_quota_state=executor_quota_state,
                require_repository_idle=require_repository_idle,
            )
            if created:
                self._enqueue(job.job_id)
        return job

    @asynccontextmanager
    async def _admission(self, repository: Repository):
        async with self._global_admission_lock:
            async with self._admission_lock_for(repository):
                yield

    def _admission_lock_for(self, repository: Repository) -> asyncio.Lock:
        key = (repository.project_id, repository.id)
        lock = self._admission_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._admission_locks[key] = lock
        return lock

    def _enqueue(self, job_id: str) -> None:
        self._pending.append(job_id)
        self._dispatch_event.set()

    async def run_when_globally_idle(
        self,
        operation: Callable[[], Awaitable[object]],
        *,
        operation_name: str = "run_command",
    ):
        """Serialize service-wide operations against durable job admission."""
        async with self._global_admission_lock:
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

    async def run_when_repository_idle(
        self,
        repository: Repository,
        operation: Callable[[], Awaitable[object]],
        *,
        operation_name: str = "run_command",
    ):
        """Serialize synchronous execution only against this repository."""
        async with self._admission_lock_for(repository):
            if self._store is None:
                raise BridgeError(
                    ErrorCode.JOB_EXECUTION_NOT_CONFIGURED,
                    f"{operation_name} requires a configured durable job store",
                )
            if self._store.has_active_for_repository(repository.project_id, repository.id):
                raise BridgeError(
                    ErrorCode.JOB_BUSY,
                    f"{operation_name} is unavailable while this repository has a queued or running durable job",
                    retryable=True,
                )
            return await operation()

    def status(self, repository: Repository, job_id: str) -> JobRecord:
        self._require_execute(repository)
        return self._require_store().get(repository.project_id, repository.id, job_id)

    def repository_busy(self, repository: Repository) -> bool:
        self._require_execute(repository)
        return self._require_store().has_active_for_repository(repository.project_id, repository.id)

    def execution_by_idempotency(
        self, repository: Repository, idempotency_key: str
    ) -> JobRecord | None:
        self._require_execute(repository)
        return self._require_store().execution_by_idempotency(
            repository.project_id, repository.id, idempotency_key
        )

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

    def _next_eligible_job(self) -> tuple[str, tuple[str, str]] | None:
        store = self._require_store()
        for _ in range(len(self._pending)):
            job_id = self._pending.popleft()
            job = store.get_by_id(job_id)
            if job is None or job.status is not JobStatus.QUEUED:
                continue
            key = (job.project_id, job.repository_id)
            if key in self._active_repositories:
                self._pending.append(job_id)
                continue
            return job_id, key
        return None

    async def _run_worker(self) -> None:
        while True:
            self._dispatch_event.clear()
            while not self._stopping and len(self._active_tasks) < self._max_concurrency:
                selected = self._next_eligible_job()
                if selected is None:
                    break
                job_id, repository_key = selected
                self._active_repositories.add(repository_key)
                task = asyncio.create_task(self._run_scheduled_job(job_id, repository_key))
                self._active_tasks[job_id] = task
            if self._stopping and not self._active_tasks:
                return
            await self._dispatch_event.wait()

    async def _run_scheduled_job(
        self, job_id: str, repository_key: tuple[str, str]
    ) -> None:
        try:
            try:
                await self._execute(job_id)
            except Exception:  # noqa: BLE001 - contain worker/task failures
                store = self._require_store()
                await self._fail_active(job_id, "internal_worker_error")
                failed = store.get_by_id(job_id)
                if failed is not None:
                    await self._emit(
                        failed, "fail", AuditOutcome.ERROR, "internal_worker_error"
                    )
        finally:
            self._active_tasks.pop(job_id, None)
            self._active_repositories.discard(repository_key)
            self._dispatch_event.set()

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
                env=self._task_environment(store.execution_environment_keys(job_id)),
                start_new_session=True,
                stdin=(asyncio.subprocess.PIPE if profile.stdin_text is not None else None),
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
        stdin_writer = (
            asyncio.create_task(self._feed_stdin(process, profile.stdin_text))
            if profile.stdin_text is not None
            else None
        )
        failure_reason = None
        try:
            await asyncio.wait_for(process.wait(), timeout=profile.timeout_seconds)
        except TimeoutError:
            failure_reason = "timeout"
            await self._terminate(process)
        finally:
            await asyncio.gather(stdout_reader, stderr_reader)
            if stdin_writer is not None:
                await stdin_writer
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

    async def _feed_stdin(self, process: asyncio.subprocess.Process, text: str) -> None:
        assert process.stdin is not None
        try:
            process.stdin.write(text.encode("utf-8"))
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            process.stdin.close()
            try:
                await process.stdin.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass

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
    def _task_environment(extra_keys: tuple[str, ...] = ()) -> dict[str, str]:
        return {
            key: value
            for key in ("PATH", "LANG", "LC_ALL", *extra_keys)
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
