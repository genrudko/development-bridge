from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.api.errors import BridgeError, ErrorCode
from app.fusion_cad.models import (
    DOCUMENT_REF_PATTERN,
    ENTITY_REF_PATTERN,
    MODEL_REVISION_PATTERN,
    ImmutableMapping,
)

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

_SAFE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SAFE_ENTITY_REF_PATTERN = re.compile(ENTITY_REF_PATTERN)
_SAFE_DOC_REF_PATTERN = re.compile(DOCUMENT_REF_PATTERN)
_SAFE_REV_PATTERN = re.compile(MODEL_REVISION_PATTERN)
_SAFE_CAPABILITY_PATTERN = re.compile(r"^[a-z0-9._-]+$")
_SAFE_CODE_PATTERN = re.compile(r"^[A-Z0-9_]{1,64}$")

KNOWN_SAFE_DIAGNOSTICS: frozenset[str] = frozenset(
    {
        "topological_recompute_diverged",
    }
)

DEFAULT_SAFE_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.FUSION_API_ERROR: "Native Fusion API execution failed",
    ErrorCode.INVALID_ARGUMENT: "Invalid CAD request payload or arguments",
    ErrorCode.REF_STALE: "Referenced CAD entity is stale or no longer exists",
    ErrorCode.REF_SPLIT: "Referenced CAD entity split into multiple entities",
    ErrorCode.REF_AMBIGUOUS: "Referenced CAD entity is ambiguous",
    ErrorCode.WRONG_DOCUMENT: "Requested document does not match active document runtime identity",
    ErrorCode.SELECTOR_EMPTY: "CAD selector matched no entities",
    ErrorCode.SELECTOR_AMBIGUOUS: "CAD selector matched multiple ambiguous entities",
    ErrorCode.REVISION_CONFLICT: "CAD document revision conflict",
    ErrorCode.UNSUPPORTED_GEOMETRY: "Unsupported CAD geometry operation",
    ErrorCode.VALIDATION_FAILED: "CAD validation checks failed",
    ErrorCode.TRANSACTION_CONFLICT: "CAD transaction conflict",
    ErrorCode.NO_ACTIVE_DESIGN: "Active document and design required in Fusion runtime context",
    ErrorCode.INTERNAL_ERROR: "Internal CAD workstation error",
    ErrorCode.CAPABILITY_UNAVAILABLE: "CAD capability unavailable",
    ErrorCode.CAPABILITY_DEGRADED: "CAD capability degraded",
    ErrorCode.CHECKPOINT_DIVERGED: "CAD checkpoint diverged",
    ErrorCode.SAVE_CONFIRMATION_REQUIRED: "CAD save confirmation required",
    ErrorCode.OPERATION_UNCERTAIN: "CAD operation state uncertain",
    ErrorCode.VIEW_STALE: "CAD view stale",
    ErrorCode.TYPE_MISMATCH: "CAD entity type mismatch",
    ErrorCode.PRECONDITION_FAILED: "CAD precondition failed",
    ErrorCode.POLICY_VIOLATION: "CAD policy violation",
}


def get_safe_error_message(code: ErrorCode | str | None = None) -> str:
    """Return constant safe public error message by error code."""
    err_code = None
    if isinstance(code, ErrorCode):
        err_code = code
    elif isinstance(code, str):
        try:
            err_code = ErrorCode(code)
        except ValueError:
            err_code = ErrorCode.FUSION_API_ERROR
    return DEFAULT_SAFE_MESSAGES.get(err_code, "CAD operation failed")


def is_token_or_secret(val: Any) -> bool:
    """Check if a string contains known secret tokens or native token patterns."""
    if not isinstance(val, str):
        return False
    return any(p.search(val) is not None for p in TOKEN_PATTERNS)


def sanitize_error_message(msg: str | None, code: ErrorCode | str | None = None) -> str:
    """Return a sanitized safe error message, falling back to constant safe message if untrusted or absent."""
    default_safe = get_safe_error_message(code)
    if not msg:
        return default_safe

    msg_str = str(msg).strip()
    if not msg_str:
        return default_safe

    if (
        "\n" in msg_str
        or "traceback" in msg_str.lower()
        or len(msg_str) > 300
        or is_token_or_secret(msg_str)
    ):
        return default_safe

    return msg_str


def sanitize_validation_errors(
    errors: Sequence[Mapping[str, Any] | Any],
) -> list[dict[str, Any]]:
    """Sanitize Pydantic validation errors, exposing safe type/loc/message metadata only.

    NEVER echo raw input, ctx objects, exception objects, or arbitrary values.
    """
    sanitized: list[dict[str, Any]] = []
    for err in errors:
        if isinstance(err, Mapping):
            loc_parts: list[str | int] = []
            for item in err.get("loc", ()):
                if isinstance(item, int):
                    loc_parts.append(item)
                elif isinstance(item, str):
                    loc_parts.append(str(item))
            sanitized.append(
                {
                    "type": str(err.get("type", "validation_error")),
                    "loc": loc_parts,
                    "msg": str(err.get("msg", "Invalid value")),
                }
            )
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
                str(x)
                for x in err.get("loc", ())
                if isinstance(x, (str, int)) and _SAFE_IDENTIFIER_PATTERN.match(str(x))
            ]
            loc_str = ".".join(loc_parts)
            msg = str(err.get("msg", "Invalid value"))
            if is_token_or_secret(msg) or "\n" in msg or len(msg) > 200:
                msg = "Invalid value"
            if loc_str:
                parts.append(f"{loc_str} ({msg})")
            else:
                parts.append(msg)
        else:
            parts.append("Validation error")
    if parts:
        return f"{prefix}: {'; '.join(parts[:5])}"
    return prefix


def filter_trusted_diagnostics(details: Any) -> dict[str, Any]:
    """Allowlist-based diagnostic filter.

    Default-denies all unknown keys and unverified values.
    Preserves explicitly trusted structured diagnostic fields required by contracts.
    """
    if not isinstance(details, Mapping):
        return {}

    clean: dict[str, Any] = {}

    for k, v in details.items():
        if not isinstance(k, str):
            continue

        # 1. Entity and Document references
        if k in ("ref", "entity", "target"):
            if isinstance(v, str) and _SAFE_ENTITY_REF_PATTERN.match(v):
                clean[k] = v
        elif k in ("document_ref", "active_document_ref", "requested_document_ref"):
            if isinstance(v, str) and (
                _SAFE_DOC_REF_PATTERN.match(v) or _SAFE_IDENTIFIER_PATTERN.match(v)
            ):
                clean[k] = v

        # 2. Revisions and Fingerprints
        elif k in ("expected_revision", "current_revision"):
            if isinstance(v, str) and (
                _SAFE_REV_PATTERN.match(v) or _SAFE_IDENTIFIER_PATTERN.match(v)
            ):
                clean[k] = v
        elif k in (
            "expected_fingerprint",
            "current_fingerprint",
            "baseline_fingerprint",
        ):
            if isinstance(v, str) and _SAFE_IDENTIFIER_PATTERN.match(v):
                clean[k] = v

        # 3. Operations, Transactions, and Structural Context
        elif k in (
            "operation",
            "operation_id",
            "transaction_id",
            "node_id",
            "tool_name",
            "job_id",
            "channel_id",
            "route_id",
        ):
            if isinstance(v, str) and _SAFE_IDENTIFIER_PATTERN.match(v):
                clean[k] = v
        elif k in ("group", "status", "outcome"):
            if isinstance(v, str) and _SAFE_IDENTIFIER_PATTERN.match(v):
                clean[k] = v
        elif k == "applied":
            if isinstance(v, bool):
                clean[k] = v

        # 4. Capabilities and Limitations
        elif k in ("capability", "required_capability", "missing_capability"):
            if isinstance(v, str) and _SAFE_CAPABILITY_PATTERN.match(v):
                clean[k] = v
        elif k == "limitations":
            if isinstance(v, (list, tuple)):
                clean[k] = [
                    str(x)
                    for x in v
                    if isinstance(x, str) and _SAFE_IDENTIFIER_PATTERN.match(x)
                ]
            elif isinstance(v, Mapping):
                clean[k] = {
                    str(lk): str(lv)
                    for lk, lv in v.items()
                    if isinstance(lk, str)
                    and isinstance(lv, (str, bool, int))
                    and _SAFE_IDENTIFIER_PATTERN.match(str(lk))
                    and _SAFE_IDENTIFIER_PATTERN.match(str(lv))
                }

        # 5. Numerical Counts and Entity Collections
        elif k in ("candidate_count", "matched_count"):
            if isinstance(v, int) and not isinstance(v, bool):
                clean[k] = v
        elif k == "matched_refs":
            if isinstance(v, (list, tuple)):
                clean[k] = [
                    str(r)
                    for r in v
                    if isinstance(r, str) and _SAFE_ENTITY_REF_PATTERN.match(r)
                ]
        elif k == "candidates":
            if isinstance(v, (list, tuple)):
                clean_cands: list[dict[str, Any]] = []
                for c in v:
                    if isinstance(c, Mapping) and "ref" in c:
                        cand_ref = str(c["ref"])
                        if _SAFE_ENTITY_REF_PATTERN.match(cand_ref):
                            clean_cands.append({"ref": cand_ref})
                clean[k] = clean_cands

        # 6. Validation Errors
        elif k == "validation_errors":
            if isinstance(v, (list, tuple)):
                clean[k] = sanitize_validation_errors(v)

        # 7. Safe Codes, Formats and Output Types
        elif k == "code":
            if isinstance(v, str) and _SAFE_CODE_PATTERN.match(v):
                clean[k] = v
        elif k in ("content_type", "parsed_type"):
            if isinstance(v, str) and _SAFE_IDENTIFIER_PATTERN.match(v):
                clean[k] = v

        # 8. Known Safe Diagnostic Tokens
        elif k == "diagnostic":
            if isinstance(v, str) and v in KNOWN_SAFE_DIAGNOSTICS:
                clean[k] = v

        # 9. Trusted Nested Diagnostics
        elif k == "nested":
            if isinstance(v, Mapping):
                clean_nested = filter_trusted_diagnostics(v)
                if clean_nested:
                    clean[k] = clean_nested

    return clean


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
            filter_trusted_diagnostics(details)
            if isinstance(details, Mapping)
            else None
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
