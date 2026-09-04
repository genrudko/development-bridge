from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.fusion_cad.models import CoordinateFrame, EntitySelector


# Base request model with strict validation
class _StrictCadBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    node_id: str = Field(..., min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


# ==========================================
# 1. fusion_read requests
# ==========================================

class ModelSnapshotRequest(_StrictCadBase):
    operation: Literal["model_snapshot"]
    include_bodies: bool = True
    include_sketches: bool = True
    include_features: bool = True
    include_parameters: bool = True
    include_views: bool = False
    detail: Literal["compact", "full"] = "compact"


class EntityReadRequest(_StrictCadBase):
    operation: Literal["entity"]
    ref: str = Field(..., min_length=1)
    include_topology: bool = False


class FeatureTreeRequest(_StrictCadBase):
    operation: Literal["feature_tree"]
    component: str | None = None


class SketchReadRequest(_StrictCadBase):
    operation: Literal["sketch"]
    ref: str = Field(..., min_length=1)
    include_profiles: bool = True
    include_constraints: bool = True


class ParametersReadRequest(_StrictCadBase):
    operation: Literal["parameters"]
    include_model_params: bool = True
    include_user_params: bool = True


class VisibilityReadRequest(_StrictCadBase):
    operation: Literal["visibility"]
    target: str | None = None


class SelectionReadRequest(_StrictCadBase):
    operation: Literal["selection"]


class QueryReadRequest(_StrictCadBase):
    operation: Literal["query"]
    selector: EntitySelector | dict[str, Any]
    limit: int = 100


class CapabilitiesReadRequest(_StrictCadBase):
    operation: Literal["capabilities"]


FusionReadRequest = Annotated[
    ModelSnapshotRequest | EntityReadRequest | FeatureTreeRequest | SketchReadRequest | ParametersReadRequest | VisibilityReadRequest | SelectionReadRequest | QueryReadRequest | CapabilitiesReadRequest,
    Field(discriminator="operation"),
]


# ==========================================
# 2. fusion_inspect requests
# ==========================================

class DescribeInspectRequest(_StrictCadBase):
    operation: Literal["describe"]
    target: str | EntitySelector | dict[str, Any]


class BoundingBoxInspectRequest(_StrictCadBase):
    operation: Literal["bounding_box"]
    target: str | EntitySelector | dict[str, Any]
    frame: CoordinateFrame | None = None


class OrientedBboxInspectRequest(_StrictCadBase):
    operation: Literal["oriented_bbox"]
    target: str | EntitySelector | dict[str, Any]


class CentroidInspectRequest(_StrictCadBase):
    operation: Literal["centroid"]
    target: str | EntitySelector | dict[str, Any]
    frame: CoordinateFrame | None = None


class AreaInspectRequest(_StrictCadBase):
    operation: Literal["area"]
    target: str | EntitySelector | dict[str, Any]


class PerimeterInspectRequest(_StrictCadBase):
    operation: Literal["perimeter"]
    target: str | EntitySelector | dict[str, Any]


class VolumeInspectRequest(_StrictCadBase):
    operation: Literal["volume"]
    target: str | EntitySelector | dict[str, Any]


class DistanceInspectRequest(_StrictCadBase):
    operation: Literal["distance"]
    target_a: str | EntitySelector | dict[str, Any]
    target_b: str | EntitySelector | dict[str, Any]


class MinimumDistanceInspectRequest(_StrictCadBase):
    operation: Literal["minimum_distance"]
    target_a: str | EntitySelector | dict[str, Any]
    target_b: str | EntitySelector | dict[str, Any]


class AngleInspectRequest(_StrictCadBase):
    operation: Literal["angle"]
    target_a: str | EntitySelector | dict[str, Any]
    target_b: str | EntitySelector | dict[str, Any]


class ParallelInspectRequest(_StrictCadBase):
    operation: Literal["parallel"]
    target_a: str | EntitySelector | dict[str, Any]
    target_b: str | EntitySelector | dict[str, Any]
    tolerance_deg: float = 0.01


class PerpendicularInspectRequest(_StrictCadBase):
    operation: Literal["perpendicular"]
    target_a: str | EntitySelector | dict[str, Any]
    target_b: str | EntitySelector | dict[str, Any]
    tolerance_deg: float = 0.01


class CoplanarInspectRequest(_StrictCadBase):
    operation: Literal["coplanar"]
    target_a: str | EntitySelector | dict[str, Any]
    target_b: str | EntitySelector | dict[str, Any]
    tolerance_mm: float = 0.001


class ConcentricInspectRequest(_StrictCadBase):
    operation: Literal["concentric"]
    target_a: str | EntitySelector | dict[str, Any]
    target_b: str | EntitySelector | dict[str, Any]
    tolerance_mm: float = 0.001


class FaceToFaceThicknessInspectRequest(_StrictCadBase):
    operation: Literal["face_to_face_thickness"]
    face_a: str | EntitySelector | dict[str, Any]
    face_b: str | EntitySelector | dict[str, Any]


FusionInspectRequest = Annotated[
    DescribeInspectRequest | BoundingBoxInspectRequest | OrientedBboxInspectRequest | CentroidInspectRequest | AreaInspectRequest | PerimeterInspectRequest | VolumeInspectRequest | DistanceInspectRequest | MinimumDistanceInspectRequest | AngleInspectRequest | ParallelInspectRequest | PerpendicularInspectRequest | CoplanarInspectRequest | ConcentricInspectRequest | FaceToFaceThicknessInspectRequest,
    Field(discriminator="operation"),
]


# ==========================================
# 3. fusion_view requests
# ==========================================

class CameraReadRequest(_StrictCadBase):
    operation: Literal["camera_read"]


class CameraSetRequest(_StrictCadBase):
    operation: Literal["camera_set"]
    eye: list[float] | None = None
    target: list[float] | None = None
    up: list[float] | None = None
    fov: float | None = None


class FitViewRequest(_StrictCadBase):
    operation: Literal["fit"]


class ZoomEntityViewRequest(_StrictCadBase):
    operation: Literal["zoom_entity"]
    target: str | EntitySelector | dict[str, Any]


class OrientToFaceViewRequest(_StrictCadBase):
    operation: Literal["orient_to_face"]
    target: str | EntitySelector | dict[str, Any]


class StandardViewRequest(_StrictCadBase):
    operation: Literal["standard_view"]
    view_type: Literal["top", "bottom", "front", "back", "left", "right", "iso", "isometric", "home"]


class ScreenshotViewRequest(_StrictCadBase):
    operation: Literal["screenshot"]
    width: int = 1920
    height: int = 1080
    transparent_background: bool = False


class PickRequest(_StrictCadBase):
    operation: Literal["pick"]
    view_ref: str = Field(..., min_length=1)
    x: float
    y: float
    coordinate_space: Literal["normalized", "pixel"] = "normalized"
    filters: list[str] = Field(default_factory=list)


FusionViewRequest = Annotated[
    CameraReadRequest | CameraSetRequest | FitViewRequest | ZoomEntityViewRequest | OrientToFaceViewRequest | StandardViewRequest | ScreenshotViewRequest | PickRequest,
    Field(discriminator="operation"),
]


# ==========================================
# 4. fusion_metadata requests
# ==========================================

class GetMetadataRequest(_StrictCadBase):
    operation: Literal["get"]
    target: str | EntitySelector | dict[str, Any]
    group: str | None = None


class SetMetadataRequest(_StrictCadBase):
    operation: Literal["set"]
    target: str | EntitySelector | dict[str, Any]
    group: str = "bridge.cad/v1"
    name: str = Field(..., min_length=1)
    value: Any
    expected_revision: str | None = None
    transaction_id: str | None = None


class RemoveMetadataRequest(_StrictCadBase):
    operation: Literal["remove"]
    target: str | EntitySelector | dict[str, Any]
    group: str = "bridge.cad/v1"
    name: str = Field(..., min_length=1)
    expected_revision: str | None = None
    transaction_id: str | None = None


class QueryMetadataRequest(_StrictCadBase):
    operation: Literal["query"]
    group: str | None = None
    name: str | None = None
    value: Any | None = None


class TagMetadataRequest(_StrictCadBase):
    operation: Literal["tag"]
    target: str | EntitySelector | dict[str, Any]
    tag_name: str = Field(..., min_length=1)
    tag_value: str = ""
    group: str = "bridge.cad/v1"
    expected_revision: str | None = None
    transaction_id: str | None = None


class UntagMetadataRequest(_StrictCadBase):
    operation: Literal["untag"]
    target: str | EntitySelector | dict[str, Any]
    tag_name: str = Field(..., min_length=1)
    group: str = "bridge.cad/v1"
    expected_revision: str | None = None
    transaction_id: str | None = None


class SetRoleMetadataRequest(_StrictCadBase):
    operation: Literal["set_role"]
    target: str | EntitySelector | dict[str, Any]
    role: str = Field(..., min_length=1)
    expected_revision: str | None = None
    transaction_id: str | None = None


class ClearRoleMetadataRequest(_StrictCadBase):
    operation: Literal["clear_role"]
    target: str | EntitySelector | dict[str, Any]
    role: str | None = None
    expected_revision: str | None = None
    transaction_id: str | None = None


class ProvenanceMetadataRequest(_StrictCadBase):
    operation: Literal["provenance"]
    target: str | EntitySelector | dict[str, Any]


FusionMetadataRequest = Annotated[
    GetMetadataRequest | SetMetadataRequest | RemoveMetadataRequest | QueryMetadataRequest | TagMetadataRequest | UntagMetadataRequest | SetRoleMetadataRequest | ClearRoleMetadataRequest | ProvenanceMetadataRequest,
    Field(discriminator="operation"),
]


# ==========================================
# 5. fusion_style requests (text + visibility)
# ==========================================

class TextCreateRequest(_StrictCadBase):
    operation: Literal["text_create"]
    text: str = Field(..., min_length=1)
    font: str = "Arial"
    height_mm: float = Field(..., gt=0)
    position: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    target_plane_or_face: str | None = None
    alignment: str = "left"
    flip_x: bool = False
    flip_y: bool = False
    role: str = "decorative_text"
    expected_revision: str | None = None
    transaction_id: str | None = None


class TextReadRequest(_StrictCadBase):
    operation: Literal["text_read"]
    text_ref: str = Field(..., min_length=1)


class TextUpdateRequest(_StrictCadBase):
    operation: Literal["text_update"]
    text_ref: str = Field(..., min_length=1)
    text: str | None = None
    font: str | None = None
    height_mm: float | None = Field(default=None, gt=0)
    position: list[float] | None = None
    expected_revision: str | None = None
    transaction_id: str | None = None


class TextDeleteRequest(_StrictCadBase):
    operation: Literal["text_delete"]
    text_ref: str = Field(..., min_length=1)
    expected_revision: str | None = None
    transaction_id: str | None = None


class TextExtrudeRequest(_StrictCadBase):
    operation: Literal["text_extrude"]
    text_ref: str = Field(..., min_length=1)
    distance_mm: float
    operation_type: Literal["new_body", "join", "cut", "intersect"] = "new_body"
    target_body: str | None = None
    expected_revision: str | None = None
    transaction_id: str | None = None


class TextCutRequest(_StrictCadBase):
    operation: Literal["text_cut"]
    text_ref: str = Field(..., min_length=1)
    distance_mm: float
    target_body: str = Field(..., min_length=1)
    expected_revision: str | None = None
    transaction_id: str | None = None


class ShowStyleRequest(_StrictCadBase):
    operation: Literal["show"]
    target: str | EntitySelector | dict[str, Any]
    expected_revision: str | None = None
    transaction_id: str | None = None


class HideStyleRequest(_StrictCadBase):
    operation: Literal["hide"]
    target: str | EntitySelector | dict[str, Any]
    expected_revision: str | None = None
    transaction_id: str | None = None


class SetVisibilityStyleRequest(_StrictCadBase):
    operation: Literal["set"]
    target: str | EntitySelector | dict[str, Any]
    visible: bool
    expected_revision: str | None = None
    transaction_id: str | None = None


class ShowOnlyStyleRequest(_StrictCadBase):
    operation: Literal["show_only"]
    target: str | EntitySelector | dict[str, Any]
    expected_revision: str | None = None
    transaction_id: str | None = None


class IsolateStyleRequest(_StrictCadBase):
    operation: Literal["isolate"]
    target: str | EntitySelector | dict[str, Any]
    expected_revision: str | None = None
    transaction_id: str | None = None


class RestoreVisibilityStyleRequest(_StrictCadBase):
    operation: Literal["restore"]
    expected_revision: str | None = None
    transaction_id: str | None = None


FusionStyleRequest = Annotated[
    TextCreateRequest | TextReadRequest | TextUpdateRequest | TextDeleteRequest | TextExtrudeRequest | TextCutRequest | ShowStyleRequest | HideStyleRequest | SetVisibilityStyleRequest | ShowOnlyStyleRequest | IsolateStyleRequest | RestoreVisibilityStyleRequest,
    Field(discriminator="operation"),
]


# ==========================================
# 6. fusion_validate requests
# ==========================================

class ValidateRunRequest(_StrictCadBase):
    operation: Literal["run"]
    profiles: list[str] = Field(
        default_factory=lambda: [
            "parametric_health",
            "model_hygiene",
            "reference_integrity",
            "text_integrity",
            "pre_mutation",
        ]
    )
    checks: list[str] = Field(default_factory=list)
    fail_on: Literal["WARN", "RED"] | None = None


FusionValidateRequest = Annotated[
    ValidateRunRequest,
    Field(discriminator="operation"),
]


# ==========================================
# 7. fusion_transaction requests
# ==========================================

class TransactionBeginRequest(_StrictCadBase):
    operation: Literal["begin"]
    expected_revision: str | None = None


class TransactionStageRequest(_StrictCadBase):
    operation: Literal["stage"]
    transaction_id: str = Field(..., min_length=1)
    action: dict[str, Any]


class TransactionPreviewRequest(_StrictCadBase):
    operation: Literal["preview"]
    transaction_id: str = Field(..., min_length=1)
    include_diff: bool = True
    include_validation: bool = True
    include_screenshot: bool = False


class TransactionCommitRequest(_StrictCadBase):
    operation: Literal["commit"]
    transaction_id: str = Field(..., min_length=1)
    expected_revision: str | None = None


class TransactionRollbackRequest(_StrictCadBase):
    operation: Literal["rollback"]
    transaction_id: str = Field(..., min_length=1)


class TransactionAbortRequest(_StrictCadBase):
    operation: Literal["abort"]
    transaction_id: str = Field(..., min_length=1)


class TransactionStatusRequest(_StrictCadBase):
    operation: Literal["status"]
    transaction_id: str | None = None


FusionTransactionRequest = Annotated[
    TransactionBeginRequest | TransactionStageRequest | TransactionPreviewRequest | TransactionCommitRequest | TransactionRollbackRequest | TransactionAbortRequest | TransactionStatusRequest,
    Field(discriminator="operation"),
]
