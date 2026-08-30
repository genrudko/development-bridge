from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.api.errors import BridgeError, ErrorCode
from app.tasks import ArtifactDeclaration, TaskProfile

from .models import JobArtifact, JobRecord, JobStatus

REPOSITORY_EXEC_TASK_ID = "__repository_exec__"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class JobStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def initialize(self) -> tuple[JobRecord, ...]:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    idempotency_key TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    exit_code INTEGER,
                    failure_reason TEXT,
                    stdout BLOB NOT NULL DEFAULT X'',
                    stderr BLOB NOT NULL DEFAULT X'',
                    stdout_truncated INTEGER NOT NULL DEFAULT 0,
                    stderr_truncated INTEGER NOT NULL DEFAULT 0,
                    executor TEXT,
                    executor_model TEXT,
                    executor_quota_state TEXT,
                    UNIQUE(project_id, repository_id, task_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS jobs_queue
                ON jobs(status, created_at);
                CREATE TABLE IF NOT EXISTS job_artifacts (
                    job_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    required INTEGER NOT NULL,
                    available INTEGER NOT NULL,
                    size_bytes INTEGER,
                    sha256 TEXT,
                    storage_path TEXT,
                    error TEXT,
                    PRIMARY KEY(job_id, artifact_id),
                    FOREIGN KEY(job_id) REFERENCES jobs(job_id)
                );
                CREATE TABLE IF NOT EXISTS job_execution_specs (
                    job_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(job_id)
                );
                CREATE TABLE IF NOT EXISTS job_terminal_waiters (
                    waiter_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    job_ids_json TEXT NOT NULL,
                    policy TEXT NOT NULL,
                    handler_name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS job_terminal_waiters_scope
                ON job_terminal_waiters(project_id, repository_id, created_at);
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
            for name in ("executor", "executor_model", "executor_quota_state"):
                if name not in columns:
                    connection.execute(f"ALTER TABLE jobs ADD COLUMN {name} TEXT")
            interrupted = self._rows(
                connection.execute(
                    "SELECT * FROM jobs WHERE status = ?", (JobStatus.RUNNING.value,)
                ).fetchall()
            )
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, finished_at = ?, failure_reason = ?
                WHERE status = ?
                """,
                (
                    JobStatus.FAILED.value,
                    _now(),
                    "interrupted_by_restart",
                    JobStatus.RUNNING.value,
                ),
            )
            return interrupted

    def save_terminal_waiter(self, *, waiter_id: str, project_id: str, repository_id: str, job_ids: tuple[str, ...], policy: str, handler_name: str, payload: dict[str, object]) -> None:
        with self._connect() as connection:
            connection.execute("INSERT INTO job_terminal_waiters (waiter_id, project_id, repository_id, job_ids_json, policy, handler_name, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (waiter_id, project_id, repository_id, json.dumps(list(job_ids), separators=(",", ":")), policy, handler_name, json.dumps(payload, sort_keys=True, separators=(",", ":")), _now()))

    def delete_terminal_waiter(self, waiter_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM job_terminal_waiters WHERE waiter_id = ?", (waiter_id,))

    def terminal_waiters(self) -> tuple[dict[str, object], ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM job_terminal_waiters ORDER BY created_at, waiter_id").fetchall()
        return tuple({"waiter_id": row["waiter_id"], "project_id": row["project_id"], "repository_id": row["repository_id"], "job_ids": tuple(json.loads(row["job_ids_json"])), "policy": row["policy"], "handler_name": row["handler_name"], "payload": json.loads(row["payload_json"])} for row in rows)

    def queued(self) -> tuple[JobRecord, ...]:
        with self._connect() as connection:
            return self._rows(
                connection.execute(
                    "SELECT * FROM jobs WHERE status = ? ORDER BY created_at, job_id",
                    (JobStatus.QUEUED.value,),
                ).fetchall()
            )

    def has_active(self) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM jobs WHERE status IN (?, ?) LIMIT 1",
                (JobStatus.QUEUED.value, JobStatus.RUNNING.value),
            ).fetchone()
        return row is not None

    def has_active_for_repository(self, project_id: str, repository_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT 1 FROM jobs
                   WHERE project_id = ? AND repository_id = ?
                     AND status IN (?, ?) LIMIT 1""",
                (project_id, repository_id, JobStatus.QUEUED.value, JobStatus.RUNNING.value),
            ).fetchone()
        return row is not None

    def execution_by_idempotency(
        self, project_id: str, repository_id: str, idempotency_key: str
    ) -> JobRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT * FROM jobs WHERE project_id=? AND repository_id=?
                   AND task_id=? AND idempotency_key=?""",
                (project_id, repository_id, REPOSITORY_EXEC_TASK_ID, idempotency_key),
            ).fetchone()
        return None if row is None else self._row(row)

    def create(
        self,
        *,
        project_id: str,
        repository_id: str,
        task_id: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> tuple[JobRecord, bool]:
        job_id = "job_" + uuid4().hex
        created_at = _now()
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO jobs (
                        job_id, project_id, repository_id, task_id, request_id,
                        idempotency_key, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        project_id,
                        repository_id,
                        task_id,
                        request_id,
                        idempotency_key,
                        JobStatus.QUEUED.value,
                        created_at,
                    ),
                )
            except sqlite3.IntegrityError:
                if idempotency_key is None:
                    raise
                row = connection.execute(
                    """
                    SELECT * FROM jobs
                    WHERE project_id = ? AND repository_id = ?
                      AND task_id = ? AND idempotency_key = ?
                    """,
                    (project_id, repository_id, task_id, idempotency_key),
                ).fetchone()
                assert row is not None
                return self._row(row), False
        return self.get(project_id, repository_id, job_id), True

    def create_execution(
        self,
        *,
        project_id: str,
        repository_id: str,
        request_id: str,
        idempotency_key: str | None,
        payload_json: str,
        payload_digest: str,
        executor: str | None = None,
        executor_model: str | None = None,
        executor_quota_state: str | None = None,
        require_repository_idle: bool = False,
    ) -> tuple[JobRecord, bool]:
        job_id = "job_" + uuid4().hex
        created_at = _now()
        with self._connect() as connection:
            if idempotency_key is not None:
                existing = connection.execute(
                    """SELECT j.*, s.payload_digest FROM jobs j
                       LEFT JOIN job_execution_specs s ON s.job_id=j.job_id
                       WHERE j.project_id=? AND j.repository_id=?
                         AND j.task_id=? AND j.idempotency_key=?""",
                    (project_id, repository_id, REPOSITORY_EXEC_TASK_ID, idempotency_key),
                ).fetchone()
                if existing is not None:
                    if existing["payload_digest"] != payload_digest:
                        raise BridgeError(ErrorCode.IDEMPOTENCY_CONFLICT,
                            "idempotency_key is already bound to another execution specification")
                    return self._row(existing), False
            if require_repository_idle:
                active = connection.execute(
                    """SELECT 1 FROM jobs WHERE project_id=? AND repository_id=?
                       AND status IN (?, ?) LIMIT 1""",
                    (project_id, repository_id, JobStatus.QUEUED.value, JobStatus.RUNNING.value),
                ).fetchone()
                if active is not None:
                    raise BridgeError(ErrorCode.JOB_BUSY,
                        "Executor submission is unavailable while this repository has an active job",
                        retryable=True)
            try:
                connection.execute(
                    """
                    INSERT INTO jobs (
                        job_id, project_id, repository_id, task_id, request_id,
                        idempotency_key, status, created_at, executor,
                        executor_model, executor_quota_state
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id, project_id, repository_id, REPOSITORY_EXEC_TASK_ID,
                        request_id, idempotency_key, JobStatus.QUEUED.value, created_at,
                        executor, executor_model, executor_quota_state,
                    ),
                )
                connection.execute(
                    """INSERT INTO job_execution_specs
                       (job_id, payload_json, payload_digest) VALUES (?, ?, ?)""",
                    (job_id, payload_json, payload_digest),
                )
            except sqlite3.IntegrityError:
                if idempotency_key is None:
                    raise
                row = connection.execute(
                    """SELECT j.*, s.payload_digest
                       FROM jobs j LEFT JOIN job_execution_specs s ON s.job_id=j.job_id
                       WHERE j.project_id=? AND j.repository_id=?
                         AND j.task_id=? AND j.idempotency_key=?""",
                    (project_id, repository_id, REPOSITORY_EXEC_TASK_ID, idempotency_key),
                ).fetchone()
                assert row is not None
                if row["payload_digest"] != payload_digest:
                    raise BridgeError(
                        ErrorCode.IDEMPOTENCY_CONFLICT,
                        "idempotency_key is already bound to another execution specification",
                    )
                return self._row(row), False
        return self.get(project_id, repository_id, job_id), True

    def execution_profile(self, job_id: str) -> TaskProfile | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM job_execution_specs WHERE job_id=?",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        return TaskProfile(
            payload["project_id"],
            payload["repository_id"],
            REPOSITORY_EXEC_TASK_ID,
            "Ad-hoc repository execution",
            payload["executable"],
            tuple(payload["arguments"]),
            payload["timeout_seconds"],
            payload["output_limit_bytes"],
            tuple(
                ArtifactDeclaration(
                    item["id"], item["path"], item["media_type"],
                    item["required"], item["max_bytes"],
                )
                for item in payload["artifacts"]
            ),
            payload.get("stdin"),
        )

    def execution_environment_keys(self, job_id: str) -> tuple[str, ...]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM job_execution_specs WHERE job_id=?", (job_id,)
            ).fetchone()
        if row is None:
            return ()
        payload = json.loads(row["payload_json"])
        return tuple(payload.get("environment_keys", ()))

    def get(self, project_id: str, repository_id: str, job_id: str) -> JobRecord:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM jobs
                WHERE project_id = ? AND repository_id = ? AND job_id = ?
                """,
                (project_id, repository_id, job_id),
            ).fetchone()
        if row is None:
            raise BridgeError(
                ErrorCode.JOB_NOT_FOUND,
                "Job was not found for the repository",
                details={"job_id": job_id},
            )
        return self._row(row)

    def get_by_id(self, job_id: str) -> JobRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return None if row is None else self._row(row)

    def start(self, job_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET status = ?, started_at = ?
                WHERE job_id = ? AND status = ?
                """,
                (JobStatus.RUNNING.value, _now(), job_id, JobStatus.QUEUED.value),
            )
            return cursor.rowcount == 1

    def append_output(self, job_id: str, stream: str, data: bytes, limit: int) -> None:
        column = "stdout" if stream == "stdout" else "stderr"
        truncated_column = f"{column}_truncated"
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {column}, {truncated_column} FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                return
            existing = bytes(row[0])
            combined = existing + data
            bounded = combined[:limit]
            truncated = bool(row[1]) or len(combined) > limit
            connection.execute(
                f"UPDATE jobs SET {column} = ?, {truncated_column} = ? WHERE job_id = ?",
                (bounded, int(truncated), job_id),
            )

    def finish(
        self,
        job_id: str,
        status: JobStatus,
        *,
        exit_code: int | None = None,
        failure_reason: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, finished_at = ?, exit_code = ?, failure_reason = ?
                WHERE job_id = ? AND status = ?
                """,
                (
                    status.value,
                    _now(),
                    exit_code,
                    failure_reason,
                    job_id,
                    JobStatus.RUNNING.value,
                ),
            )

    def fail_active(self, job_id: str, reason: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, finished_at = ?, failure_reason = ?
                WHERE job_id = ? AND status IN (?, ?)
                """,
                (
                    JobStatus.FAILED.value,
                    _now(),
                    reason,
                    job_id,
                    JobStatus.QUEUED.value,
                    JobStatus.RUNNING.value,
                ),
            )

    def cancel_queued(self, job_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET status = ?, finished_at = ?
                WHERE job_id = ? AND status = ?
                """,
                (JobStatus.CANCELLED.value, _now(), job_id, JobStatus.QUEUED.value),
            )
            return cursor.rowcount == 1

    def save_artifacts(
        self, job_id: str, artifacts: tuple[JobArtifact, ...]
    ) -> None:
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO job_artifacts (
                    job_id, artifact_id, path, media_type, required, available,
                    size_bytes, sha256, storage_path, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        job_id,
                        artifact.artifact_id,
                        artifact.path,
                        artifact.media_type,
                        int(artifact.required),
                        int(artifact.available),
                        artifact.size_bytes,
                        artifact.sha256,
                        artifact.storage_path,
                        artifact.error,
                    )
                    for artifact in artifacts
                ],
            )

    def artifacts(self, job_id: str) -> tuple[JobArtifact, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM job_artifacts WHERE job_id = ? ORDER BY artifact_id",
                (job_id,),
            ).fetchall()
        return tuple(
            JobArtifact(
                job_id=row["job_id"],
                artifact_id=row["artifact_id"],
                path=row["path"],
                media_type=row["media_type"],
                required=bool(row["required"]),
                available=bool(row["available"]),
                size_bytes=row["size_bytes"],
                sha256=row["sha256"],
                storage_path=row["storage_path"],
                error=row["error"],
            )
            for row in rows
        )

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self._path, timeout=5)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            yield connection
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _rows(rows) -> tuple[JobRecord, ...]:
        return tuple(JobStore._row(row) for row in rows)

    @staticmethod
    def _row(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            job_id=row["job_id"],
            project_id=row["project_id"],
            repository_id=row["repository_id"],
            task_id=row["task_id"],
            request_id=row["request_id"],
            status=JobStatus(row["status"]),
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            exit_code=row["exit_code"],
            failure_reason=row["failure_reason"],
            stdout=bytes(row["stdout"]),
            stderr=bytes(row["stderr"]),
            stdout_truncated=bool(row["stdout_truncated"]),
            stderr_truncated=bool(row["stderr_truncated"]),
            executor=row["executor"],
            executor_model=row["executor_model"],
            executor_quota_state=row["executor_quota_state"],
        )
