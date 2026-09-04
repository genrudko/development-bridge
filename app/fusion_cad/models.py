from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CoordinateSpace = Literal["world", "component", "occurrence", "sketch"]
StabilityClass = Literal["persistent", "contextual", "transient"]
CapabilityState = Literal["supported", "degraded", "unavailable"]
ValidationVerdict = Literal["GREEN", "WARN", "RED"]
FindingSeverity = Literal["info", "warn", "error"]


class CoordinateFrame(BaseModel):
    """Explicit coordinate space specification for CAD geometry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    space: CoordinateSpace
    ref: str | None = None

    @model_validator(mode="after")
    def validate_frame_ref(self) -> CoordinateFrame:
        if self.space == "world":
            if self.ref is not None:
                raise ValueError("CoordinateFrame with space='world' must have ref=None")
        else:
            if not self.ref:
                raise ValueError(f"CoordinateFrame with space='{self.space}' requires a valid non-empty entity ref")
        return self


class EntityRef(BaseModel):
    """Document-scoped opaque reference to a Fusion CAD entity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str = Field(..., min_length=1, max_length=128)
    kind: str = Field(..., min_length=1, max_length=64)
    document_ref: str = Field(..., min_length=1, max_length=128)
    stability: StabilityClass
    native_type: str | None = None
    name: str | None = None
    component_path: tuple[str, ...] = Field(default_factory=tuple)


class EntitySelector(BaseModel):
    """Declarative selector for querying geometry and semantic entities."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: list[str] | str | None = None
    name: dict[str, Any] | str | None = None
    component_path: list[str] | None = None
    occurrence: str | None = None
    feature_type: str | None = None
    created_by: dict[str, Any] | None = None
    tag: dict[str, Any] | None = None
    role: list[str] | str | None = None
    visible: bool | None = None
    appearance: str | None = None
    bbox_region: dict[str, Any] | None = None
    logical_object: str | None = None
    transaction_id: str | None = None
    recipe: str | None = None


class CapabilityRecord(BaseModel):
    """Truthful record of a runtime capability state and limitations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., min_length=1)
    state: CapabilityState
    implementation: str | None = None
    fusion_version: str | None = None
    relay_version: str | None = None
    limitations: list[str] = Field(default_factory=list)


class DocumentState(BaseModel):
    """Active design document identity and observed revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_ref: str = Field(..., min_length=1)
    model_revision: str = Field(..., min_length=1)
    name: str | None = None
    units: str | None = "mm"
    snapshot_id: str | None = None


class ValidationFinding(BaseModel):
    """Specific diagnostic finding from a model validation check."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: str = Field(..., min_length=1)
    severity: FindingSeverity
    message: str = Field(..., min_length=1)
    entity_refs: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    suggested_action: str | None = None


class ValidationReport(BaseModel):
    """Comprehensive health and hygiene validation report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: ValidationVerdict
    profiles: list[str] = Field(default_factory=list)
    checks_run: list[str] = Field(default_factory=list)
    findings: list[ValidationFinding] = Field(default_factory=list)
    summary: str = Field(..., min_length=1)
    snapshot_id: str | None = None
    model_revision: str | None = None


class ValidationReportRef(BaseModel):
    """Compact reference summary to an external validation report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str | None = None
    verdict: ValidationVerdict | None = None
    summary: str | None = None
    finding_count: int = 0
    report_uri: str | None = None


class ViewRefSummary(BaseModel):
    """Immutable view reference binding a screenshot to revision, camera, and visibility."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    view_ref: str = Field(..., min_length=1)
    model_revision: str = Field(..., min_length=1)
    camera_revision: str | None = None
    visibility_revision: str | None = None
    width: int = Field(..., gt=0)
    height: int = Field(..., gt=0)
    image: str = Field(..., min_length=1)


class Point3(BaseModel):
    """3D point with explicit coordinate frame."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    x: float
    y: float
    z: float
    frame: CoordinateFrame | None = None


class Vector3(BaseModel):
    """3D vector with explicit coordinate frame."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    x: float
    y: float
    z: float
    frame: CoordinateFrame | None = None


class BoundingBox(BaseModel):
    """3D axis-aligned bounding box with explicit coordinate frame."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    min_point: Point3
    max_point: Point3
    frame: CoordinateFrame | None = None


class Transform(BaseModel):
    """4x4 transformation matrix with explicit coordinate frame."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    matrix: list[list[float]]
    frame: CoordinateFrame | None = None


class Plane(BaseModel):
    """Geometric plane defined by origin and normal vector."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    origin: Point3
    normal: Vector3
    frame: CoordinateFrame | None = None


class Ray(BaseModel):
    """Geometric ray defined by origin and direction vector."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    origin: Point3
    direction: Vector3
    frame: CoordinateFrame | None = None


class CadResult(BaseModel):
    """Authoritative result envelope for all Fusion CAD workstation operations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    api_version: str = "fusion.cad/v1"
    status: Literal["succeeded", "failed"] = "succeeded"
    operation_id: str | None = None
    document: DocumentState | None = None
    summary: str = Field(..., min_length=1)
    data: dict[str, Any] = Field(default_factory=dict)
    changed_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    diff: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    capabilities: list[CapabilityRecord] | None = None
