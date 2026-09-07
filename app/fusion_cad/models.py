from __future__ import annotations

from collections.abc import Iterator, Mapping
from types import MappingProxyType
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    GetJsonSchemaHandler,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

ENTITY_REF_PATTERN = r"^ent_[A-Za-z0-9._-]+$"
DOCUMENT_REF_PATTERN = r"^doc_[A-Za-z0-9._-]+$"
MODEL_REVISION_PATTERN = r"^rev_[A-Za-z0-9._-]+$"
VIEW_REF_PATTERN = r"^view_[A-Za-z0-9._-]+$"
CAMERA_REVISION_PATTERN = r"^cam_[A-Za-z0-9._-]+$"
VISIBILITY_REVISION_PATTERN = r"^vis_[A-Za-z0-9._-]+$"
OPERATION_ID_PATTERN = r"^op_[A-Za-z0-9._-]+$"
TRANSACTION_ID_PATTERN = r"^tx_[A-Za-z0-9._-]+$"
SNAPSHOT_ID_PATTERN = r"^snap_[A-Za-z0-9._-]+$"
VALIDATION_REPORT_ID_PATTERN = r"^val_[A-Za-z0-9._-]+$"
TEXT_REF_PATTERN = r"^(text|ent)_[A-Za-z0-9._-]+$"

CoordinateSpace = Literal["world", "component", "occurrence", "sketch"]
StabilityClass = Literal["persistent", "contextual", "transient"]
CapabilityState = Literal["supported", "degraded", "unavailable"]
ValidationVerdict = Literal["GREEN", "WARN", "RED"]
FindingSeverity = Literal["info", "warn", "error"]


def freeze_value(val: Any) -> Any:
    """Recursively convert nested mappings and sequences into immutable equivalents."""
    if val is None or isinstance(val, (bool, int, float, str)):
        return val
    if isinstance(val, ImmutableMapping):
        return val
    if isinstance(val, Mapping):
        return ImmutableMapping(val)
    if isinstance(val, (list, tuple, set, frozenset)):
        return tuple(freeze_value(x) for x in val)
    if isinstance(val, BaseModel):
        return val
    return val


def unfreeze_value(val: Any) -> Any:
    """Recursively convert immutable mappings and tuples back into standard dicts/lists for serialization."""
    if isinstance(val, Mapping):
        return {k: unfreeze_value(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [unfreeze_value(x) for x in val]
    return val


class ImmutableMapping(Mapping[str, Any]):
    """Recursively immutable mapping structure preventing top-level and nested modifications."""

    __slots__ = ("_data", "_hash")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raw = dict(*args, **kwargs)
        frozen: dict[str, Any] = {}
        for k, v in raw.items():
            if not isinstance(k, str):
                raise TypeError(f"ImmutableMapping keys must be strings, got {type(k).__name__}")
            frozen[k] = freeze_value(v)
        object.__setattr__(self, "_data", MappingProxyType(frozen))
        object.__setattr__(self, "_hash", None)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"ImmutableMapping({dict(self._data)!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return dict(self) == dict(other)
        return False

    def __hash__(self) -> int:
        if self._hash is None:
            try:
                h = hash(
                    tuple(
                        sorted(
                            (
                                k,
                                v
                                if isinstance(v, (int, float, str, bool, tuple, type(None)))
                                else str(v),
                            )
                            for k, v in self._data.items()
                        )
                    )
                )
            except (TypeError, ValueError):
                h = hash(tuple(sorted(self._data.keys())))
            object.__setattr__(self, "_hash", h)
        return self._hash

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.chain_schema(
            [
                core_schema.dict_schema(core_schema.str_schema(), core_schema.any_schema()),
                core_schema.no_info_plain_validator_function(cls._validate),
            ],
            serialization=core_schema.plain_serializer_function_ser_schema(
                unfreeze_value,
                return_schema=core_schema.dict_schema(
                    core_schema.str_schema(), core_schema.any_schema()
                ),
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return {"type": "object", "additionalProperties": True}

    @classmethod
    def _validate(cls, value: Any) -> ImmutableMapping:
        if isinstance(value, ImmutableMapping):
            return value
        if isinstance(value, Mapping):
            return cls(value)
        raise ValueError(f"Expected mapping for ImmutableMapping, got {type(value).__name__}")


FrozenDict = ImmutableMapping


class CoordinateFrame(BaseModel):
    """Explicit coordinate space specification for CAD geometry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    space: CoordinateSpace
    ref: str | None = Field(default=None, pattern=ENTITY_REF_PATTERN)

    @model_validator(mode="after")
    def validate_frame_ref(self) -> CoordinateFrame:
        if self.space == "world":
            if self.ref is not None:
                raise ValueError("CoordinateFrame with space='world' must have ref=None")
        else:
            if not self.ref:
                raise ValueError(
                    f"CoordinateFrame with space='{self.space}' requires a valid non-empty entity ref matching {ENTITY_REF_PATTERN}"
                )
        return self


class EntityRef(BaseModel):
    """Document-scoped opaque reference to a Fusion CAD entity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str = Field(..., pattern=ENTITY_REF_PATTERN, max_length=128)
    kind: str = Field(..., min_length=1, max_length=64)
    document_ref: str = Field(..., pattern=DOCUMENT_REF_PATTERN, max_length=128)
    stability: StabilityClass
    native_type: str | None = None
    name: str | None = None
    component_path: tuple[str, ...] = Field(default_factory=tuple)


class NamePattern(BaseModel):
    """Name pattern matching criteria for selectors."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    regex: str = Field(..., min_length=1)


class CreatedBySelector(BaseModel):
    """Provenance creator criteria for selectors."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: str = Field(..., min_length=1)
    operation: str | None = None
    operation_id: str | None = Field(default=None, pattern=OPERATION_ID_PATTERN)


class TagSelector(BaseModel):
    """Metadata tag criteria for selectors."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., min_length=1)
    value: str | None = None
    group: str = "bridge.cad/v1"


class Point3(BaseModel):
    """3D point with explicit coordinate frame."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    x: float
    y: float
    z: float
    frame: CoordinateFrame


class Vector3(BaseModel):
    """3D vector with explicit coordinate frame."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    x: float
    y: float
    z: float
    frame: CoordinateFrame


class BoundingBox(BaseModel):
    """3D axis-aligned bounding box with explicit coordinate frame."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    min_point: Point3
    max_point: Point3
    frame: CoordinateFrame


class Transform(BaseModel):
    """4x4 transformation matrix with explicit coordinate frame."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    matrix: tuple[tuple[float, ...], ...]
    frame: CoordinateFrame


class Plane(BaseModel):
    """Geometric plane defined by origin and normal vector."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    origin: Point3
    normal: Vector3
    frame: CoordinateFrame


class Ray(BaseModel):
    """Geometric ray defined by origin and direction vector."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    origin: Point3
    direction: Vector3
    frame: CoordinateFrame


class EntitySelector(BaseModel):
    """Declarative selector for querying geometry and semantic entities."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: tuple[str, ...] | str | None = None
    name: NamePattern | str | None = None
    component_path: tuple[str, ...] | None = None
    occurrence: str | None = Field(default=None, pattern=ENTITY_REF_PATTERN)
    feature_type: str | None = None
    created_by: CreatedBySelector | None = None
    tag: TagSelector | None = None
    role: tuple[str, ...] | str | None = None
    visible: bool | None = None
    appearance: str | None = None
    bbox_region: BoundingBox | None = None
    logical_object: str | None = Field(default=None, pattern=TEXT_REF_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)
    recipe: str | None = None


class CapabilityRecord(BaseModel):
    """Truthful record of a runtime capability state and limitations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., min_length=1)
    state: CapabilityState
    implementation: str | None = None
    fusion_version: str | None = None
    relay_version: str | None = None
    limitations: tuple[str, ...] = Field(default_factory=tuple)


class DocumentState(BaseModel):
    """Active design document identity and observed revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_ref: str = Field(..., pattern=DOCUMENT_REF_PATTERN)
    model_revision: str = Field(..., pattern=MODEL_REVISION_PATTERN)
    name: str | None = None
    units: str | None = "mm"
    snapshot_id: str | None = Field(default=None, pattern=SNAPSHOT_ID_PATTERN)


class ValidationFinding(BaseModel):
    """Specific diagnostic finding from a model validation check."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: str = Field(..., min_length=1)
    severity: FindingSeverity
    message: str = Field(..., min_length=1)
    entity_refs: tuple[str, ...] = Field(default_factory=tuple)
    evidence: ImmutableMapping = Field(default_factory=ImmutableMapping)
    suggested_action: str | None = None

    @model_validator(mode="after")
    def validate_finding(self) -> ValidationFinding:
        import re

        pattern = re.compile(ENTITY_REF_PATTERN)
        for ref in self.entity_refs:
            if not pattern.match(ref):
                raise ValueError(
                    f"ValidationFinding entity_ref '{ref}' does not match pattern {ENTITY_REF_PATTERN}"
                )
        return self


class ValidationReport(BaseModel):
    """Comprehensive health and hygiene validation report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: ValidationVerdict
    profiles: tuple[str, ...] = Field(default_factory=tuple)
    checks_run: tuple[str, ...] = Field(default_factory=tuple)
    findings: tuple[ValidationFinding, ...] = Field(default_factory=tuple)
    summary: str = Field(..., min_length=1)
    snapshot_id: str | None = Field(default=None, pattern=SNAPSHOT_ID_PATTERN)
    model_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)


class ValidationReportRef(BaseModel):
    """Compact reference summary to an external validation report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str | None = Field(default=None, pattern=VALIDATION_REPORT_ID_PATTERN)
    verdict: ValidationVerdict | None = None
    summary: str | None = None
    finding_count: int = 0
    report_uri: str | None = None


class ViewRefSummary(BaseModel):
    """Immutable view reference binding a screenshot to revision, camera, and visibility."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    view_ref: str = Field(..., pattern=VIEW_REF_PATTERN)
    model_revision: str = Field(..., pattern=MODEL_REVISION_PATTERN)
    camera_revision: str | None = Field(default=None, pattern=CAMERA_REVISION_PATTERN)
    visibility_revision: str | None = Field(default=None, pattern=VISIBILITY_REVISION_PATTERN)
    width: int = Field(..., gt=0)
    height: int = Field(..., gt=0)
    image: str = Field(..., min_length=1)


class CadResult(BaseModel):
    """Authoritative result envelope for all Fusion CAD workstation operations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    api_version: Literal["fusion.cad/v1"] = "fusion.cad/v1"
    status: Literal["succeeded", "failed"] = "succeeded"
    operation_id: str | None = Field(default=None, pattern=OPERATION_ID_PATTERN)
    document: DocumentState | None = None
    summary: str = Field(..., min_length=1)
    data: ImmutableMapping = Field(default_factory=ImmutableMapping)
    changed_refs: tuple[str, ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    artifacts: tuple[ImmutableMapping, ...] = Field(default_factory=tuple)
    diff: ImmutableMapping | None = None
    validation: ImmutableMapping | None = None
    capabilities: tuple[CapabilityRecord, ...] | None = None
