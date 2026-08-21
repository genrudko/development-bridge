from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    request_id: str
    tool: str
    outcome: AuditOutcome
    duration_ms: int
    project_id: str | None = None
    repository_id: str | None = None
    error_code: str | None = None
    event: str | None = None
    job_id: str | None = None
    task_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        return payload
