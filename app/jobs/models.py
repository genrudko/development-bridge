from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class JobRecord:
    job_id: str
    project_id: str
    repository_id: str
    task_id: str
    request_id: str
    status: JobStatus
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    failure_reason: str | None = None
    stdout: bytes = b""
    stderr: bytes = b""
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    def status_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "job_id": self.job_id,
            "project_id": self.project_id,
            "repository_id": self.repository_id,
            "task_id": self.task_id,
            "status": self.status.value,
            "created_at": self.created_at,
        }
        for key, value in (
            ("started_at", self.started_at),
            ("finished_at", self.finished_at),
            ("exit_code", self.exit_code),
            ("failure_reason", self.failure_reason),
        ):
            if value is not None:
                result[key] = value
        return result

    def output_dict(self) -> dict[str, str | bool]:
        return {
            "stdout": self.stdout.decode("utf-8", errors="replace"),
            "stderr": self.stderr.decode("utf-8", errors="replace"),
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
        }


@dataclass(frozen=True, slots=True)
class JobArtifact:
    job_id: str
    artifact_id: str
    path: str
    media_type: str
    required: bool
    available: bool
    size_bytes: int | None = None
    sha256: str | None = None
    storage_path: str | None = None
    error: str | None = None

    def public_dict(self, *, download_path: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "artifact_id": self.artifact_id,
            "path": self.path,
            "media_type": self.media_type,
            "required": self.required,
            "available": self.available,
        }
        if self.available:
            result["size_bytes"] = self.size_bytes
            result["sha256"] = self.sha256
            if download_path is not None:
                result["download_path"] = download_path
        return result
