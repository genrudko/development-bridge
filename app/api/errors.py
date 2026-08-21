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
    GIT_INDEX_EMPTY = "GIT_INDEX_EMPTY"
    GIT_OPERATION_IN_PROGRESS = "GIT_OPERATION_IN_PROGRESS"
    GIT_PUSH_PLAN_INVALID = "GIT_PUSH_PLAN_INVALID"
    GIT_PUSH_REJECTED = "GIT_PUSH_REJECTED"
    GIT_BRANCH_EXISTS = "GIT_BRANCH_EXISTS"
    GIT_BRANCH_NOT_FOUND = "GIT_BRANCH_NOT_FOUND"
    GIT_UPSTREAM_NOT_CONFIGURED = "GIT_UPSTREAM_NOT_CONFIGURED"
    GIT_WORKTREE_DIRTY = "GIT_WORKTREE_DIRTY"
    GIT_FAST_FORWARD_REJECTED = "GIT_FAST_FORWARD_REJECTED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    CHANGE_PRECONDITION_FAILED = "CHANGE_PRECONDITION_FAILED"
    CHANGE_PLAN_INVALID = "CHANGE_PLAN_INVALID"
    CHANGE_APPLY_FAILED = "CHANGE_APPLY_FAILED"
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    JOB_NOT_CANCELLABLE = "JOB_NOT_CANCELLABLE"
    ARTIFACT_NOT_FOUND = "ARTIFACT_NOT_FOUND"
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
