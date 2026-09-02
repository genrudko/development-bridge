from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ExecutorName(StrEnum):
    CODEX = "codex"
    ANTIGRAVITY = "antigravity"


class QuotaState(StrEnum):
    OK = "ok"
    LOW = "low"
    EXHAUSTED = "exhausted"
    UNKNOWN = "unknown"


class TaskKind(StrEnum):
    IMPLEMENTATION = "implementation"
    REVIEW = "review"
    OTHER = "other"


def normalize_quota(
    *, remaining_fraction: float | None, exhausted: bool = False
) -> QuotaState:
    if exhausted:
        return QuotaState.EXHAUSTED
    if remaining_fraction is None:
        return QuotaState.UNKNOWN
    if not math.isfinite(remaining_fraction) or not 0 <= remaining_fraction <= 1:
        raise ValueError("remaining_fraction must be between 0 and 1")
    if remaining_fraction == 0:
        return QuotaState.EXHAUSTED
    if remaining_fraction <= 0.20:
        return QuotaState.LOW
    return QuotaState.OK


@dataclass(frozen=True, slots=True)
class ExecutorStatus:
    executor: ExecutorName
    available: bool
    authenticated: bool
    busy: bool
    model: str | None
    quota_state: QuotaState
    remaining_fraction: float | None
    reset_time: datetime | None
    last_error: str | None
    last_success_at: datetime | None
    version: str | None

    def public_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "executor": self.executor.value,
            "available": self.available,
            "authenticated": self.authenticated,
            "busy": self.busy,
            "quota_state": self.quota_state.value,
        }
        for key, value in (
            ("model", self.model),
            ("remaining_fraction", self.remaining_fraction),
            ("last_error", self.last_error),
            ("version", self.version),
        ):
            if value is not None:
                result[key] = value
        if self.reset_time is not None:
            result["reset_time"] = self.reset_time.isoformat()
        if self.last_success_at is not None:
            result["last_success_at"] = self.last_success_at.isoformat()
        return result


@dataclass(frozen=True, slots=True)
class ExecutorRequest:
    task: str
    task_kind: TaskKind
    executor: ExecutorName | None
    timeout_seconds: float
    output_limit_bytes: int
    idempotency_key: str | None


@dataclass(frozen=True, slots=True)
class ExecutorLaunch:
    executable: str
    arguments: tuple[str, ...]
    stdin: str | None
    environment_keys: tuple[str, ...]
    executor: ExecutorName
    model: str | None
    quota_state: QuotaState


@dataclass(frozen=True, slots=True)
class ExecutorSelection:
    executor: ExecutorName
    reason: str
