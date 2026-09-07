from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.api.errors import BridgeError, ErrorCode
from app.fusion_cad.models import (
    DOCUMENT_REF_PATTERN,
    ENTITY_REF_PATTERN,
    MODEL_REVISION_PATTERN,
    OPERATION_ID_PATTERN,
    SNAPSHOT_ID_PATTERN,
    TRANSACTION_ID_PATTERN,
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

# ---------------------------------------------------------------------------
# Trusted public message registry.
#
# DEFAULT_SAFE_MESSAGES values and the explicitly registered constant texts in
# _EXTRA_TRUSTED_PUBLIC_MESSAGES are the ONLY strings that may appear in public
# Fusion CAD diagnostics. Trust is derived from explicit registration in this
# module; it is NEVER inferred from string shape, length, or content. Arbitrary
# untrusted text (including fresh short single-line markers) therefore fails
# closed to the per-error-code constant default message.
# ---------------------------------------------------------------------------

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

_EXTRA_TRUSTED_PUBLIC_MESSAGES: frozenset[str] = frozenset(
    {
        "Native entity resolution failed",
        "Node capability state is unprobed; invoke fusion_read(operation='capabilities') first",
        "expected_revision is required for standalone mutation",
        "No stored baseline for transaction; call transaction:begin first",
        "Document lacks stable runtime identity",
        "Unrecognized domain output from native Fusion script: missing or invalid api_version 'fusion.cad/v1'",
        "Unrecognized domain output format from native Fusion script: missing or invalid api_version 'fusion.cad/v1'",
        "Failed to externalize binary result payload",
        "transaction:begin terminal success with missing, empty, or whitespace real fingerprint; failing closed to prevent unusable baseline",
        "transaction:begin completed without an active document reference or stable runtime identity",
        "Authoritative baseline_fingerprint is required and cannot be empty",
        "Attribute lacks stable owner_id; empty IDs or mutable names are rejected",
    }
)

_TRUSTED_PUBLIC_MESSAGES: frozenset[str] = (
    _EXTRA_TRUSTED_PUBLIC_MESSAGES | frozenset(DEFAULT_SAFE_MESSAGES.values())
)


def trusted_public_message(text: str) -> str:
    """Explicitly register an internal constant string as trusted for public display.

    This is the ONLY sanctioned mechanism for richer-than-default public wording.
    Trust comes from explicit registration; never from string shape or content.
    """
    if text not in _TRUSTED_PUBLIC_MESSAGES:
        raise ValueError(
            "Untrusted public message text; register the exact constant in errors.py first"
        )
    return text


class TrustedDetail:
    """Explicit trusted-provenance marker for dynamic internal metadata.

    A value wrapped in TrustedDetail is explicitly declared by internal code to
    be trusted provenance (validated node ids, classified operation names,
    internal capability names, Python type names, capability limitation prose).
    No value is trusted from its shape or content alone.
    """

    __slots__ = ("value",)

    def __init__(self, value: Any) -> None:
        self.value = value


def trusted_detail(value: Any) -> TrustedDetail:
    """Mark an internal dynamic value as trusted provenance for public diagnostics."""
    return TrustedDetail(value)


# ---------------------------------------------------------------------------
# Strong opaque identity patterns.
#
# These patterns describe machine-generated namespaces owned by the service or
# the Fusion runtime (opaque entity/docs/revision refs, tx/op/snapshot ids,
# SHA fingerprints). They are NOT generic identifier shapes; fresh arbitrary
# markers never match them. They are only ever applied after the key semantics
# (e.g. "target" must be an ent_* opaque ref) are already constrained.
# ---------------------------------------------------------------------------

_SAFE_ENTITY_REF_PATTERN = re.compile(ENTITY_REF_PATTERN)
_SAFE_DOC_REF_PATTERN = re.compile(DOCUMENT_REF_PATTERN)
_SAFE_REV_PATTERN = re.compile(MODEL_REVISION_PATTERN)
_SAFE_TX_PATTERN = re.compile(TRANSACTION_ID_PATTERN)
_SAFE_OP_PATTERN = re.compile(OPERATION_ID_PATTERN)
_SAFE_SNAP_PATTERN = re.compile(SNAPSHOT_ID_PATTERN)
_SAFE_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-fA-F]{8,256}$")
_SAFE_CAPABILITY_PATTERN = re.compile(r"^[a-z0-9._-]{1,128}$")
_SAFE_CODE_PATTERN = re.compile(r"^[A-Z0-9_]{1,64}$")
# Generic shape checks are ONLY ever applied to values that have already been
# explicitly marked as trusted provenance, and to safe validation LOCATION
# semantics. They are never the sole trust decision for untrusted values.
_SAFE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SAFE_LOC_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")

KNOWN_SAFE_DIAGNOSTICS: frozenset[str] = frozenset(
    {
        "topological_recompute_diverged",
    }
)

_KNOWN_STATUS_VALUES: frozenset[str] = frozenset(
    {
        "succeeded",
        "failed",
        "queued",
        "running",
        "claimed",
        "uncertain",
        "timed_out",
        "interrupted",
        "late_succeeded",
        "late_failed",
    }
)

_KNOWN_OUTCOME_VALUES: frozenset[str] = frozenset(
    {
        "exact",
        "split",
        "stale",
        "ambiguous",
        "wrong_document",
    }
)

_KNOWN_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "text",
        "blocks",
        "json",
        "unknown",
    }
)

# Constant trusted wording for Pydantic validation error types. No raw
# msg/input/ctx/validator-controlled text is ever exposed.
_VALIDATION_TYPE_WORDING: dict[str, str] = {
    "missing": "Field is required",
    "extra_forbidden": "Unknown field is not permitted",
    "string_type": "Expected a string value",
    "int_type": "Expected an integer value",
    "number_type": "Expected a numeric value",
    "float_type": "Expected a numeric value",
    "decimal_type": "Expected a numeric value",
    "bool_type": "Expected a boolean value",
    "literal_error": "Value is not within the allowed set",
    "enum": "Value is not within the allowed set",
    "string_pattern_mismatch": "Value does not match the required format",
    "string_too_short": "Value is shorter than the allowed length",
    "string_too_long": "Value is longer than the allowed length",
    "int_too_small": "Value is below the allowed minimum",
    "int_too_big": "Value is above the allowed maximum",
    "float_too_small": "Value is below the allowed minimum",
    "float_too_big": "Value is above the allowed maximum",
    "model_attributes_type": "Expected an object payload",
    "dict_type": "Expected a mapping value",
    "list_type": "Expected a list value",
    "tuple_type": "Expected a tuple value",
    "model_validator": "Value failed model validation",
    "json_invalid": "Input is not valid JSON",
    "union_tag_invalid": "Value does not match any allowed variant",
    "union_tag_not_found": "Value does not match any allowed variant",
    "url_type": "Expected a URL value",
    "uuid_type": "Expected a UUID value",
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
    """Return a constant safe public error message (default-deny).

    Arbitrary untrusted text -- including fresh short single-line markers -- is
    never surfaced. Only explicitly registered trusted public constants
    (_TRUSTED_PUBLIC_MESSAGES) or the constant per-error-code default may appear
    in public diagnostics.
    """
    if isinstance(msg, str):
        msg_str = msg.strip()
        if msg_str in _TRUSTED_PUBLIC_MESSAGES:
            return msg_str
    return get_safe_error_message(code)


def _safe_validation_type(err: Mapping[str, Any]) -> str:
    raw_type = str(err.get("type", ""))
    if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", raw_type):
        return raw_type
    return "validation_error"


def _safe_validation_loc(err: Mapping[str, Any]) -> list[str | int]:
    """Extract safe field location semantics only: schema field names and indices.

    Field names are constrained to identifier shape; arbitrary input values are
    never part of loc.
    """
    loc_parts: list[str | int] = []
    for item in err.get("loc", ()):
        if isinstance(item, int):
            loc_parts.append(item)
        elif isinstance(item, str) and _SAFE_LOC_PATTERN.match(item):
            loc_parts.append(item)
    return loc_parts


def sanitize_validation_errors(
    errors: Sequence[Mapping[str, Any] | Any],
) -> list[dict[str, Any]]:
    """Sanitize Pydantic validation errors, exposing safe type/loc/constant wording only.

    NEVER echoes raw input, ctx, msg, exception objects, or validator-controlled
    text. Messages are constant trusted wording derived from the validation type.
    """
    sanitized: list[dict[str, Any]] = []
    for err in errors:
        if isinstance(err, Mapping):
            err_type = _safe_validation_type(err)
            sanitized.append(
                {
                    "type": err_type,
                    "loc": _safe_validation_loc(err),
                    "msg": _VALIDATION_TYPE_WORDING.get(err_type, "Invalid value"),
                }
            )
        else:
            sanitized.append(
                {
                    "type": "validation_error",
                    "loc": [],
                    "msg": "Invalid value",
                }
            )
    return sanitized


def format_safe_validation_message(
    prefix: str,
    errors: Sequence[Mapping[str, Any] | Any],
) -> str:
    """Format a safe validation message from safe field locations and constant wording.

    Raw input values, msg, and ctx are never interpolated. The resulting message
    still passes through sanitize_error_message and therefore only surfaces if it
    is an explicitly registered trusted constant.
    """
    parts: list[str] = []
    for err in errors:
        if isinstance(err, Mapping):
            loc_parts = [str(x) for x in _safe_validation_loc(err)]
            loc_str = ".".join(loc_parts)
            wording = _VALIDATION_TYPE_WORDING.get(
                _safe_validation_type(err), "Invalid value"
            )
            if loc_str:
                parts.append(f"{loc_str}: {wording}")
            else:
                parts.append(wording)
        else:
            parts.append("Invalid value")
    if parts:
        return f"{prefix}: {'; '.join(parts[:5])}"
    return prefix


def filter_trusted_diagnostics(details: Any) -> dict[str, Any]:
    """Allowlist-based public diagnostic filter with default-deny.

    Keys are a fixed semantic allowlist. Values survive only when they are:
      - safe scalars (bool/int) under explicit scalar keys;
      - known constant vocabulary (status/outcome/content_type/codes/diagnostics);
      - strong opaque runtime identities under their semantic keys
        (ent_* refs, doc_* refs, rev_* revisions, tx_*/op_*/snap_* ids,
         SHA fingerprints);
      - explicit trusted-provenance-marked internal metadata (TrustedDetail).

    Unknown keys and unpatterned or unprovenanced values fail closed. No value is
    ever trusted from generic identifier shape alone.
    """
    if not isinstance(details, Mapping):
        return {}

    clean: dict[str, Any] = {}

    for k, v in details.items():
        if not isinstance(k, str):
            continue

        trusted = isinstance(v, TrustedDetail)
        if trusted:
            v = v.value

        # 1. Strong opaque entity references
        if k in ("ref", "entity", "target"):
            if isinstance(v, str) and _SAFE_ENTITY_REF_PATTERN.match(v):
                clean[k] = v

        # 2. Document references (doc_* opaque namespace)
        elif k in (
            "document_ref",
            "active_document_ref",
            "requested_document_ref",
            "bound_document",
            "result_document",
            "data_document",
        ):
            if isinstance(v, str) and _SAFE_DOC_REF_PATTERN.match(v):
                clean[k] = v

        # 3. Revisions (rev_* opaque namespace)
        elif k in ("expected_revision", "current_revision", "model_revision"):
            if isinstance(v, str) and _SAFE_REV_PATTERN.match(v):
                clean[k] = v

        # 4. Fingerprints (SHA-256 style internal hashes)
        elif k in (
            "expected_fingerprint",
            "current_fingerprint",
            "baseline_fingerprint",
            "result_fingerprint",
        ):
            if isinstance(v, str) and (
                _SAFE_FINGERPRINT_PATTERN.match(v)
                or _SAFE_ENTITY_REF_PATTERN.match(v)
            ):
                clean[k] = v

        # 5. Service-minted opaque ids
        elif k == "transaction_id":
            if isinstance(v, str) and _SAFE_TX_PATTERN.match(v):
                clean[k] = v
        elif k == "operation_id":
            if isinstance(v, str) and _SAFE_OP_PATTERN.match(v):
                clean[k] = v
        elif k == "snapshot_id":
            if isinstance(v, str) and _SAFE_SNAP_PATTERN.match(v):
                clean[k] = v

        # 6. Known constant vocabulary (enum-like safe values, never arbitrary text)
        elif k == "outcome":
            if isinstance(v, str) and v in _KNOWN_OUTCOME_VALUES:
                clean[k] = v
        elif k == "status":
            if (isinstance(v, str) and v in _KNOWN_STATUS_VALUES) or (
                trusted
                and isinstance(v, str)
                and _SAFE_IDENTIFIER_PATTERN.match(v)
            ):
                clean[k] = v
        elif k == "content_type":
            if isinstance(v, str) and v in _KNOWN_CONTENT_TYPES:
                clean[k] = v
        elif k in ("capability", "required_capability", "missing_capability"):
            if trusted and isinstance(v, str) and _SAFE_CAPABILITY_PATTERN.match(v):
                clean[k] = v

        # 7. Dynamic internal metadata: ONLY with explicit trusted provenance,
        #    never from identifier shape alone.
        elif k in (
            "node_id",
            "operation",
            "group",
            "tool_name",
            "job_id",
            "channel_id",
            "route_id",
            "parsed_type",
        ):
            if trusted and isinstance(v, str) and _SAFE_IDENTIFIER_PATTERN.match(v):
                clean[k] = v

        # 8. Safe scalars under explicit scalar keys
        elif k == "applied":
            if isinstance(v, bool):
                clean[k] = v
        elif k in ("candidate_count", "matched_count", "current_sequence"):
            if isinstance(v, int) and not isinstance(v, bool):
                clean[k] = v

        # 9. Entity collections that only carry opaque ent_* refs
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
                    if isinstance(c, Mapping) and isinstance(c.get("ref"), str):
                        cand_ref = c["ref"]
                        if _SAFE_ENTITY_REF_PATTERN.match(cand_ref):
                            clean_cands.append({"ref": cand_ref})
                if clean_cands:
                    clean[k] = clean_cands

        # 10. Fixed security / validation vocabularies
        elif k == "code":
            if isinstance(v, str) and _SAFE_CODE_PATTERN.match(v):
                clean[k] = v
        elif k == "diagnostic":
            if isinstance(v, str) and v in KNOWN_SAFE_DIAGNOSTICS:
                clean[k] = v
        elif k == "nested":
            if isinstance(v, Mapping):
                clean_nested = filter_trusted_diagnostics(v)
                if clean_nested:
                    clean[k] = clean_nested
        elif k == "validation_errors":
            if isinstance(v, (list, tuple)):
                clean[k] = sanitize_validation_errors(v)
        elif k == "limitations":
            # Capability limitations are internal record prose; only explicit
            # trusted provenance may expose them (never identifier-shape pass).
            if trusted and isinstance(v, (list, tuple)):
                clean[k] = [str(x) for x in v if isinstance(x, str)]

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