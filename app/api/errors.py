from __future__ import annotations

from enum import StrEnum
from typing import Any, Mapping


class ErrorCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    REPOSITORY_NOT_FOUND = "REPOSITORY_NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    GIT_REVISION_NOT_FOUND = "GIT_REVISION_NOT_FOUND"
    GIT_COMMAND_FAILED = "GIT_COMMAND_FAILED"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    CHANGE_PRECONDITION_FAILED = "CHANGE_PRECONDITION_FAILED"
    CHANGE_PLAN_INVALID = "CHANGE_PLAN_INVALID"
    CHANGE_APPLY_FAILED = "CHANGE_APPLY_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class BridgeError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = dict(details or {})


class ToolNameConflictError(RuntimeError):
    pass
