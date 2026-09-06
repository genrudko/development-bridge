from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.api.errors import BridgeError, ErrorCode
from app.fusion_cad.models import ImmutableMapping

CAD_NON_RETRYABLE_CODES: frozenset[ErrorCode] = frozenset(
    {
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
    }
)

NATIVE_TOKEN_KEYS: frozenset[str] = frozenset(
    {
        "entityToken",
        "entitytoken",
        "native_token",
        "nativetoken",
        "token",
        "entity_token",
        "nativeToken",
        "secret",
        "token_secret",
    }
)

TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"secret::", re.IGNORECASE),
    re.compile(r"AQAA[A-Za-z0-9+/=]{16,}"),
    re.compile(r"token::", re.IGNORECASE),
)

DEFAULT_SAFE_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.FUSION_API_ERROR: "Native Fusion API execution failed",
    ErrorCode.INVALID_ARGUMENT: "Invalid CAD request payload or arguments",
    ErrorCode.REF_STALE: "Referenced CAD entity is stale or no longer exists",
    ErrorCode.REF_SPLIT: "Referenced CAD entity split into multiple entities",
    ErrorCode.REF_AMBIGUOUS: "Referenced CAD entity is ambiguous",
    ErrorCode.WRONG_DOCUMENT: "CAD entity belongs to a different document",
    ErrorCode.SELECTOR_EMPTY: "CAD selector matched no entities",
    ErrorCode.SELECTOR_AMBIGUOUS: "CAD selector matched multiple ambiguous entities",
    ErrorCode.REVISION_CONFLICT: "CAD document revision conflict",
    ErrorCode.UNSUPPORTED_GEOMETRY: "Unsupported CAD geometry operation",
    ErrorCode.VALIDATION_FAILED: "CAD validation checks failed",
    ErrorCode.TRANSACTION_CONFLICT: "CAD transaction conflict",
    ErrorCode.NO_ACTIVE_DESIGN: "No active CAD design available",
    ErrorCode.INTERNAL_ERROR: "Internal CAD workstation error",
}


def is_token_or_secret(val: Any) -> bool:
    """Check if a string contains known secret tokens or native token patterns."""
    if not isinstance(val, str):
        return False
    return any(p.search(val) is not None for p in TOKEN_PATTERNS)


def sanitize_error_message(msg: str | None, code: ErrorCode | str | None = None) -> str:
    """Return a sanitized safe error message, falling back to constant safe message if secrets/tokens present."""
    err_code = None
    if isinstance(code, ErrorCode):
        err_code = code
    elif isinstance(code, str):
        try:
            err_code = ErrorCode(code)
        except ValueError:
            err_code = ErrorCode.FUSION_API_ERROR

    default_safe = DEFAULT_SAFE_MESSAGES.get(err_code, "CAD operation failed")

    if not msg:
        return default_safe

    msg_str = str(msg)
    # If raw traceback or secret/token detected, do not expose raw error string
    if "traceback (most recent call last)" in msg_str.lower() or is_token_or_secret(
        msg_str
    ):
        return default_safe

    return msg_str


def sanitize_public_payload(val: Any) -> Any:
    """Recursively sanitize public payloads by removing native token aliases without stringifying values.

    Preserves legitimate public opaque refs, semantic fields, and python types (float, int, bool, str, None).
    Handles Mapping, ImmutableMapping, list, tuple, and nested structures.
    """
    if isinstance(val, Mapping):
        clean_map: dict[Any, Any] = {}
        for k, v in val.items():
            k_str = str(k)
            if k_str in NATIVE_TOKEN_KEYS or k_str.lower() in NATIVE_TOKEN_KEYS:
                continue
            if is_token_or_secret(k_str):
                continue
            if isinstance(v, str) and is_token_or_secret(v):
                continue
            clean_map[k] = sanitize_public_payload(v)
        if isinstance(val, ImmutableMapping):
            return ImmutableMapping(clean_map)
        return clean_map
    if isinstance(val, tuple):
        return tuple(sanitize_public_payload(x) for x in val)
    if isinstance(val, list):
        return [sanitize_public_payload(x) for x in val]
    if isinstance(val, set):
        return {sanitize_public_payload(x) for x in val}
    if isinstance(val, frozenset):
        return frozenset(sanitize_public_payload(x) for x in val)
    return val


def sanitize_validation_errors(
    errors: Sequence[Mapping[str, Any] | Any],
) -> list[dict[str, Any]]:
    """Sanitize Pydantic validation errors, keeping structured diagnostics without leaking input secrets."""
    sanitized: list[dict[str, Any]] = []
    for err in errors:
        if isinstance(err, Mapping):
            item: dict[str, Any] = {
                "type": str(err.get("type", "validation_error")),
                "loc": [str(x) for x in err.get("loc", ())],
                "msg": str(err.get("msg", "Invalid value")),
            }
            raw_input = err.get("input")
            if raw_input is not None and not is_token_or_secret(str(raw_input)):
                clean_input = sanitize_public_payload(raw_input)
                if not is_token_or_secret(str(clean_input)):
                    item["input"] = clean_input
            sanitized.append(item)
        else:
            sanitized.append({"msg": "Validation error"})
    return sanitized


def format_safe_validation_message(
    prefix: str, errors: Sequence[Mapping[str, Any] | Any]
) -> str:
    """Format a safe validation error message including field locations and messages,
    strictly excluding raw input values to prevent secret leakage.
    """
    parts: list[str] = []
    for err in errors:
        if isinstance(err, Mapping):
            loc_parts = [
                "[redacted]" if is_token_or_secret(str(x)) else str(x)
                for x in err.get("loc", ())
            ]
            loc_str = ".".join(loc_parts)
            msg = str(err.get("msg", "Invalid value"))
            if is_token_or_secret(msg):
                msg = "[redacted]"
            if loc_str:
                parts.append(f"{loc_str} ({msg})")
            else:
                parts.append(msg)
        else:
            parts.append("Validation error")
    if parts:
        return f"{prefix}: {'; '.join(parts[:5])}"
    return prefix


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
        message: str | None = None,
        *,
        retryable: bool | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        effective_retryable = (
            is_cad_error_retryable(code) if retryable is None else retryable
        )
        clean_msg = sanitize_error_message(message, code)
        clean_details = (
            sanitize_public_payload(dict(details))
            if isinstance(details, Mapping)
            else (sanitize_public_payload(details) if details is not None else None)
        )
        super().__init__(
            code, clean_msg, retryable=effective_retryable, details=clean_details
        )
        self.__cause__ = None
        self.__context__ = None
        self.__suppress_context__ = True


def cad_error_to_bridge_error(
    code: ErrorCode,
    message: str | None = None,
    *,
    details: Mapping[str, Any] | None = None,
    retryable: bool | None = None,
) -> BridgeError:
    return FusionCadError(code, message, retryable=retryable, details=details)
