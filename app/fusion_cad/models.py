from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    frame: CoordinateFrame = Field(default_factory=lambda: CoordinateFrame(space="world"))


class Vector3(BaseModel):
    """3D vector with explicit coordinate frame."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    x: float
    y: float
    z: float
    frame: CoordinateFrame = Field(default_factory=lambda: CoordinateFrame(space="world"))


class BoundingBox(BaseModel):
    """3D axis-aligned bounding box with explicit coordinate frame."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    min_point: Point3
    max_point: Point3
    frame: CoordinateFrame = Field(default_factory=lambda: CoordinateFrame(space="world"))


class Transform(BaseModel):
    """4x4 transformation matrix with explicit coordinate frame."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    matrix: tuple[tuple[float, ...], ...]
    frame: CoordinateFrame = Field(default_factory=lambda: CoordinateFrame(space="world"))


class Plane(BaseModel):
    """Geometric plane defined by origin and normal vector."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    origin: Point3
    normal: Vector3
    frame: CoordinateFrame = Field(default_factory=lambda: CoordinateFrame(space="world"))


class Ray(BaseModel):
    """Geometric ray defined by origin and direction vector."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    origin: Point3
    direction: Vector3
    frame: CoordinateFrame = Field(default_factory=lambda: CoordinateFrame(space="world"))


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
    evidence: Mapping[str, Any] = Field(default_factory=dict)
    suggested_action: str | None = None

    @model_validator(mode="after")
    def validate_finding(self) -> ValidationFinding:
        import re

        pattern = re.compile(ENTITY_REF_PATTERN)
        for ref in self.entity_refs:
            if not pattern.match(ref):
                raise ValueError(f"ValidationFinding entity_ref '{ref}' does not match pattern {ENTITY_REF_PATTERN}")
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
    data: Mapping[str, Any] = Field(default_factory=dict)
    changed_refs: tuple[str, ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    artifacts: tuple[Mapping[str, Any], ...] = Field(default_factory=tuple)
    diff: Mapping[str, Any] | None = None
    validation: Mapping[str, Any] | None = None
    capabilities: tuple[CapabilityRecord, ...] | None = None
