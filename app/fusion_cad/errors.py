from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.api.errors import BridgeError, ErrorCode

CAD_NON_RETRYABLE_CODES: frozenset[ErrorCode] = frozenset({
    ErrorCode.NO_ACTIVE_DESIGN,
    ErrorCode.WRONG_DOCUMENT,
    ErrorCode.REF_STALE,
    ErrorCode.REF_SPLIT,
    ErrorCode.REF_AMBIGUOUS,
    ErrorCode.TYPE_MISMATCH,
    ErrorCode.SELECTOR_EMPTY,
    ErrorCode.SELECTOR_AMBIGUOUS,
    ErrorCode.INVALID_ARGUMENT,
    ErrorCode.PRECONDITION_FAILED,
    ErrorCode.UNSUPPORTED_GEOMETRY,
    ErrorCode.CAPABILITY_UNAVAILABLE,
    ErrorCode.CAPABILITY_DEGRADED,
    ErrorCode.REVISION_CONFLICT,
    ErrorCode.VIEW_STALE,
    ErrorCode.FUSION_API_ERROR,
    ErrorCode.VALIDATION_FAILED,
    ErrorCode.TRANSACTION_CONFLICT,
    ErrorCode.CHECKPOINT_DIVERGED,
    ErrorCode.SAVE_CONFIRMATION_REQUIRED,
    ErrorCode.OPERATION_UNCERTAIN,
})


def is_cad_error_retryable(code: ErrorCode | str) -> bool:
    """Return whether a CAD error code can be retried automatically.

    In CAD mutations and state operations, errors are non-retryable by default
    to prevent applying stale or conflicting modifications without new evidence.
    """
    if isinstance(code, str):
        try:
            code = ErrorCode(code)
        except ValueError:
            return False
    return code not in CAD_NON_RETRYABLE_CODES


class FusionCadError(BridgeError):
    """Domain error for Fusion CAD workstation operations."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        effective_retryable = is_cad_error_retryable(code) if retryable is None else retryable
        super().__init__(code, message, retryable=effective_retryable, details=details)


def cad_error_to_bridge_error(
    code: ErrorCode,
    message: str,
    *,
    details: Mapping[str, Any] | None = None,
    retryable: bool | None = None,
) -> BridgeError:
    return FusionCadError(code, message, retryable=retryable, details=details)
