"""Transactional metadata, roles, tags, and provenance for fusion.cad/v1.

Task 10 domain rules implemented here:

- Reserved namespace: Bridge reads/writes ONLY the ``bridge.cad/v1`` attribute
  group keys. Unrelated Fusion attribute groups are never touched or surfaced.
- Explicit metadata writes are normal revision-safe mutations: they require
  ``expected_revision`` and participate in the same revision/freshness guard as
  every other mutation.
- Provenance (creator tool/operation, operation id, transaction id, recipe,
  logical object ref, created revision, role/tags) is part of the SAME mutation
  command payload as the geometry/metadata change. There is no hidden
  post-commit metadata command.
- Provenance identity is the DURABLE COMMAND identity: the operation id shared
  with the desktop operation journal for the same command, and a truthful
  ``created_revision`` — the revision in which the created/changed entity
  exists after the command applies (deterministically ``rev_{sequence + 1}``,
  because the Fusion-side guard fails any command whose post-apply fingerprint
  equals the pre-apply one and the RevisionTracker advances exactly one
  sequence per distinct fingerprint). The pre-mutation expected revision is
  never recorded as ``created_revision``.
- Selector support: role/tag/provenance selector criteria are derived from
  persisted model attribute records carried by entities, never from transient
  Bridge-side memory.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.models import (
    MODEL_REVISION_PATTERN,
    OPERATION_ID_PATTERN,
    TEXT_REF_PATTERN,
    TRANSACTION_ID_PATTERN,
)

RESERVED_METADATA_GROUP = "bridge.cad/v1"
PROVENANCE_ATTRIBUTE_NAME = "provenance"
ROLE_ATTRIBUTE_NAME = "role"
TAG_ATTRIBUTE_PREFIX = "tag:"

PROVENANCE_CREATOR_TOOL = "bridge.fusion-cad-agent"

_METADATA_WRITE_OPERATIONS = frozenset(
    {"set", "remove", "tag", "untag", "set_role", "clear_role"}
)

_PROVENANCE_JSON_LOADS = json.JSONDecoder().decode


def assert_reserved_metadata_group(group: str | None) -> str:
    """Restrict metadata reads/writes to the reserved Bridge namespace.

    Returns the resolved group name (defaulting to ``bridge.cad/v1``) and fails
    closed with ``INVALID_ARGUMENT`` for any foreign group so unrelated Fusion
    attributes are preserved untouched.
    """
    resolved = group if group is not None else RESERVED_METADATA_GROUP
    if not isinstance(resolved, str) or resolved != RESERVED_METADATA_GROUP:
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Metadata operations are restricted to the reserved Bridge namespace "
            "'bridge.cad/v1'; unrelated Fusion attribute groups are never read or written",
            details={"group": "non-reserved"},
        )
    return resolved


class ProvenanceTag(BaseModel):
    """One tag recorded in provenance (mirrors the persisted tag attribute)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., min_length=1)
    value: str = ""


class ProvenanceRecord(BaseModel):
    """Provenance recorded inside the same mutation command that changes the model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    creator_tool: str = Field(..., min_length=1)
    creator_operation: str = Field(..., min_length=1)
    operation_id: str = Field(..., pattern=OPERATION_ID_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)
    recipe: str | None = None
    logical_object_ref: str | None = Field(default=None, pattern=TEXT_REF_PATTERN)
    created_revision: str = Field(..., pattern=MODEL_REVISION_PATTERN)
    role: str | None = None
    tags: tuple[ProvenanceTag, ...] = Field(default_factory=tuple)


def _validate_operation_id(operation: str, operation_id: Any) -> str:
    if (
        not isinstance(operation_id, str)
        or re.fullmatch(OPERATION_ID_PATTERN, operation_id) is None
    ):
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Provenance operation_id must be the durable command operation id "
            "(pattern 'op_...' shared with the desktop operation journal)",
            details={"operation": op_key(operation)},
        )
    return operation_id


def _validate_created_revision(operation: str, created_revision: Any) -> str:
    if (
        not isinstance(created_revision, str)
        or re.fullmatch(MODEL_REVISION_PATTERN, created_revision) is None
    ):
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Provenance requires the truthful post-mutation created_revision (the "
            "revision in which the created/changed entity exists); it must be "
            "resolved from the revision tracker, never guessed from the "
            "pre-mutation expected revision",
            details={"operation": op_key(operation)},
        )
    return created_revision


def build_provenance_record(
    *,
    operation: str,
    created_revision: str,
    operation_id: str | None = None,
    creator_operation: str | None = None,
    transaction_id: str | None = None,
    tag_name: str | None = None,
    tag_value: str | None = None,
    role: str | None = None,
    recipe: str | None = None,
    logical_object_ref: str | None = None,
) -> ProvenanceRecord:
    """Build the provenance record for one metadata/geometry mutation command.

    ``operation_id`` must be the durable command operation id shared with the
    desktop operation journal for the SAME command; when omitted a fresh id is
    generated and the caller must use ``record.operation_id`` as the journal
    operation id so both stay identical.

    ``created_revision`` records the revision in which the created/changed
    entity exists after this command applies. Callers must resolve it from the
    RevisionTracker (deterministically ``rev_{sequence + 1}`` for a successful
    mutation); the pre-mutation expected revision is not a truthful substitute
    and a missing or malformed value fails closed.
    """
    rev = _validate_created_revision(operation, created_revision)
    if operation_id is None:
        op_id = f"op_{uuid.uuid4().hex[:12]}"
    else:
        op_id = _validate_operation_id(operation, operation_id)
    tags: tuple[ProvenanceTag, ...] = ()
    if isinstance(tag_name, str) and tag_name.strip():
        tags = (ProvenanceTag(name=tag_name, value=tag_value or ""),)
    return ProvenanceRecord(
        creator_tool=PROVENANCE_CREATOR_TOOL,
        creator_operation=creator_operation
        if isinstance(creator_operation, str) and creator_operation.strip()
        else f"fusion_metadata:{operation}",
        operation_id=op_id,
        transaction_id=transaction_id,
        recipe=recipe,
        logical_object_ref=logical_object_ref,
        created_revision=rev,
        role=role,
        tags=tags,
    )


def op_key(operation: Any) -> str:
    return str(operation) if operation else "unknown"


def provenance_attribute_value(record: ProvenanceRecord) -> str:
    """Canonical deterministic JSON serialization for the persisted attribute value."""
    return json.dumps(
        record.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def try_parse_provenance_attribute(value: Any) -> ProvenanceRecord | None:
    """Parse a persisted provenance value; return None when absent or malformed.

    Never raises: selector metadata views must tolerate unrelated or corrupted
    persisted data without fabricating provenance.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = _PROVENANCE_JSON_LOADS(value)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    try:
        return ProvenanceRecord.model_validate(parsed)
    except Exception:  # noqa: BLE001 - malformed persisted provenance is not trusted
        return None


def parse_provenance_attribute(value: Any) -> ProvenanceRecord:
    """Strictly parse a persisted provenance value; fail closed when malformed.

    The raw persisted value is never echoed in the error (no native or user
    payload leakage through error confidentiality).
    """
    record = try_parse_provenance_attribute(value)
    if record is None:
        raise FusionCadError(
            ErrorCode.FUSION_API_ERROR,
            "Persisted provenance attribute is malformed and cannot be trusted",
            details={"attribute": PROVENANCE_ATTRIBUTE_NAME},
        )
    return record


def canonical_attribute_value(value: Any) -> str:
    """Canonical string form for a persisted attribute value.

    Strings persist verbatim; every other JSON-serializable value persists as
    deterministic compact JSON. Non-serializable values fail closed.
    """
    if isinstance(value, str):
        return value
    try:
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Metadata value must be a string or JSON-serializable value",
            details={"value_type": type(value).__name__},
        ) from exc


def tag_attribute_name(tag_name: str) -> str:
    if not isinstance(tag_name, str) or not tag_name.strip():
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Tag name must be a non-empty string",
        )
    return f"{TAG_ATTRIBUTE_PREFIX}{tag_name}"


class MetadataWrite(BaseModel):
    """One reserved-namespace attribute write applied by the mutation command."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., min_length=1)
    value: str


class MetadataRemoval(BaseModel):
    """One reserved-namespace attribute removal applied by the mutation command.

    ``value`` optionally restricts removal to the attribute carrying exactly
    that value (used by role-scoped clear_role).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., min_length=1)
    value: str | None = None


class MetadataMutationPlan(BaseModel):
    """The complete metadata side of ONE mutation command.

    Includes the explicit requested writes/removals plus the provenance write so
    geometry/metadata change and provenance are always one atomic command.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    writes: tuple[MetadataWrite, ...] = Field(default_factory=tuple)
    removals: tuple[MetadataRemoval, ...] = Field(default_factory=tuple)
    provenance: ProvenanceRecord


def _plan_provenance(
    payload: Mapping[str, Any],
    *,
    operation: str,
    operation_id: str | None,
    created_revision: str | None,
    tag_name: str | None = None,
    tag_value: str | None = None,
    role: str | None = None,
) -> ProvenanceRecord:
    """Build the provenance record for a plan, propagating required fields.

    The durable command operation id, recipe, and logical object ref travel
    with the SAME command payload into the persisted provenance record; the
    post-mutation created_revision must be supplied by the caller (resolved
    from the RevisionTracker) and is never inferred from the pre-mutation
    expected revision.
    """
    return build_provenance_record(
        operation=operation,
        created_revision=created_revision,
        operation_id=operation_id,
        transaction_id=payload.get("transaction_id"),
        recipe=payload.get("recipe"),
        logical_object_ref=payload.get("logical_object_ref"),
        tag_name=tag_name,
        tag_value=tag_value,
        role=role,
    )


def build_metadata_mutation_plan(
    payload: Mapping[str, Any],
    *,
    operation_id: str | None = None,
    created_revision: str | None = None,
) -> MetadataMutationPlan:
    """Build the one-command metadata plan for an explicit metadata mutation.

    Validates the reserved namespace, requires ``expected_revision`` (metadata
    writes are normal revision-safe mutations), and always appends the
    provenance attribute write.

    ``operation_id`` must be the durable command operation id shared with the
    desktop operation journal; when omitted a fresh id is generated and the
    caller must reuse ``plan.provenance.operation_id`` for the journal.
    ``created_revision`` must be the truthful post-mutation revision resolved
    from the RevisionTracker; a plan without it fails closed instead of
    recording the pre-mutation expected revision.
    """
    operation = payload.get("operation")
    if operation not in _METADATA_WRITE_OPERATIONS:
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Operation is not an explicit metadata mutation",
            details={"operation": op_key(operation)},
        )
    assert_reserved_metadata_group(payload.get("group"))

    expected_revision = payload.get("expected_revision")
    if not isinstance(expected_revision, str) or not expected_revision.strip():
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "expected_revision is required for explicit metadata mutations",
            details={"operation": op_key(operation)},
        )

    writes: list[MetadataWrite] = []
    removals: list[MetadataRemoval] = []

    if operation == "set":
        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                "Metadata set requires a non-empty attribute name",
            )
        writes.append(
            MetadataWrite(name=name, value=canonical_attribute_value(payload.get("value")))
        )
    elif operation == "remove":
        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                "Metadata remove requires a non-empty attribute name",
            )
        removals.append(MetadataRemoval(name=name))
    elif operation == "tag":
        tag_name = payload.get("tag_name")
        if not isinstance(tag_name, str) or not tag_name.strip():
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                "Metadata tag requires a non-empty tag name",
            )
        writes.append(
            MetadataWrite(
                name=tag_attribute_name(tag_name),
                value=canonical_attribute_value(payload.get("tag_value") or ""),
            )
        )
    elif operation == "untag":
        tag_name = payload.get("tag_name")
        if not isinstance(tag_name, str) or not tag_name.strip():
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                "Metadata untag requires a non-empty tag name",
            )
        removals.append(MetadataRemoval(name=tag_attribute_name(tag_name)))
    elif operation == "set_role":
        role = payload.get("role")
        if not isinstance(role, str) or not role.strip():
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                "Metadata set_role requires a non-empty role",
            )
        writes.append(MetadataWrite(name=ROLE_ATTRIBUTE_NAME, value=role))
    elif operation == "clear_role":
        role = payload.get("role")
        removals.append(
            MetadataRemoval(
                name=ROLE_ATTRIBUTE_NAME,
                value=role if isinstance(role, str) and role.strip() else None,
            )
        )

    provenance = _plan_provenance(
        payload,
        operation=operation,
        operation_id=operation_id,
        created_revision=created_revision,
        tag_name=payload.get("tag_name") if operation == "tag" else None,
        tag_value=payload.get("tag_value") if operation == "tag" else None,
        role=payload.get("role") if operation == "set_role" else None,
    )
    writes.append(
        MetadataWrite(
            name=PROVENANCE_ATTRIBUTE_NAME,
            value=provenance_attribute_value(provenance),
        )
    )

    return MetadataMutationPlan(
        writes=tuple(writes), removals=tuple(removals), provenance=provenance
    )


def apply_metadata_mutation_plan(
    payload: dict[str, Any],
    *,
    operation_id: str | None = None,
    created_revision: str | None = None,
) -> dict[str, Any]:
    """Attach the one-command metadata plan to a mutate script payload.

    The plan is executed by the same script execution that applies the geometry
    or metadata change; no separate metadata command exists.
    """
    plan = build_metadata_mutation_plan(
        payload, operation_id=operation_id, created_revision=created_revision
    )
    payload["group"] = RESERVED_METADATA_GROUP
    payload["metadata_writes"] = [w.model_dump(mode="json") for w in plan.writes]
    payload["metadata_removals"] = [
        r.model_dump(mode="json", exclude_none=True) for r in plan.removals
    ]
    payload["provenance"] = plan.provenance.model_dump(mode="json", exclude_none=True)
    return payload


def apply_geometry_provenance_plan(
    payload: dict[str, Any],
    *,
    operation: str,
    creator_operation: str,
    operation_id: str | None = None,
    created_revision: str | None = None,
) -> dict[str, Any]:
    """Attach a provenance-only metadata plan for ONE geometry mutation command.

    This is the common safe path shared with later geometry features (Task 11):
    the provenance attribute write is executed by the SAME mutate script
    execution that creates/changes geometry — no second command, no hidden
    post-commit metadata command, and the same atomic plan application
    (preflight, undo-log compensation, post-fingerprint verification) as
    explicit metadata mutations. The plan carries ONLY the provenance write;
    explicit metadata operations keep using build_metadata_mutation_plan.

    ``creator_operation`` must name the actual creating/changing operation
    (e.g. ``fusion_style:text_create``); it is never fabricated here.
    """
    provenance = build_provenance_record(
        operation=operation,
        creator_operation=creator_operation,
        created_revision=created_revision,
        operation_id=operation_id,
        transaction_id=payload.get("transaction_id"),
        recipe=payload.get("recipe"),
        logical_object_ref=payload.get("logical_object_ref"),
    )
    payload["group"] = RESERVED_METADATA_GROUP
    payload["metadata_writes"] = [
        MetadataWrite(
            name=PROVENANCE_ATTRIBUTE_NAME,
            value=provenance_attribute_value(provenance),
        ).model_dump(mode="json")
    ]
    payload["metadata_removals"] = []
    payload["provenance"] = provenance.model_dump(mode="json", exclude_none=True)
    return payload


def _record_field(record: Any, field: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(field)
    return getattr(record, field, None)


def entity_metadata_view(entity: Any) -> dict[str, Any]:
    """Derive selector metadata from an entity's PERSISTED attribute records.

    Only ``bridge.cad/v1`` group records are considered; unrelated groups are
    ignored. Provenance records contribute created_by/transaction_id/recipe/
    logical_object; role and tag records contribute role/tags. The view contains
    no transient Bridge state.
    """
    view: dict[str, Any] = {
        "tags": [],
        "role": None,
        "created_by": None,
        "transaction_id": None,
        "recipe": None,
        "logical_object": None,
    }
    if entity is None:
        return view
    if isinstance(entity, Mapping):
        attributes = entity.get("attributes")
    else:
        attributes = getattr(entity, "attributes", None)
    if not attributes:
        return view

    for record in attributes:
        group = _record_field(record, "group")
        if group != RESERVED_METADATA_GROUP:
            continue
        name = _record_field(record, "name")
        value = _record_field(record, "value")
        if not isinstance(name, str):
            continue
        if name == ROLE_ATTRIBUTE_NAME:
            view["role"] = value
        elif name.startswith(TAG_ATTRIBUTE_PREFIX):
            view["tags"].append(
                {
                    "group": group,
                    "name": name[len(TAG_ATTRIBUTE_PREFIX) :],
                    "value": value,
                }
            )
        elif name == PROVENANCE_ATTRIBUTE_NAME:
            record_view = try_parse_provenance_attribute(value)
            if record_view is None:
                continue
            view["created_by"] = {
                "tool": record_view.creator_tool,
                "operation": record_view.creator_operation,
                "operation_id": record_view.operation_id,
            }
            if record_view.transaction_id is not None:
                view["transaction_id"] = record_view.transaction_id
            if record_view.recipe is not None:
                view["recipe"] = record_view.recipe
            if record_view.logical_object_ref is not None:
                view["logical_object"] = record_view.logical_object_ref
        elif name == "logical_object":
            view["logical_object"] = value
        elif name == "recipe":
            view["recipe"] = value
        elif name == "transaction_id":
            view["transaction_id"] = value
    return view
