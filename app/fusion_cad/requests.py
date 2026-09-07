from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.fusion_cad.models import (
    DOCUMENT_REF_PATTERN,
    ENTITY_REF_PATTERN,
    MODEL_REVISION_PATTERN,
    TEXT_REF_PATTERN,
    TRANSACTION_ID_PATTERN,
    VIEW_REF_PATTERN,
    CoordinateFrame,
    EntitySelector,
    Point3,
    Vector3,
)

TargetRef = Annotated[str, Field(pattern=ENTITY_REF_PATTERN)] | EntitySelector


# Base request model with strict validation
class _StrictCadBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    node_id: str = Field(..., min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    document_ref: str | None = Field(default=None, pattern=DOCUMENT_REF_PATTERN)


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
    ref: str = Field(..., pattern=ENTITY_REF_PATTERN)
    include_topology: bool = False


class FeatureTreeRequest(_StrictCadBase):
    operation: Literal["feature_tree"]
    component: str | None = Field(default=None, pattern=ENTITY_REF_PATTERN)


class SketchReadRequest(_StrictCadBase):
    operation: Literal["sketch"]
    ref: str = Field(..., pattern=ENTITY_REF_PATTERN)
    include_profiles: bool = True
    include_constraints: bool = True


class ParametersReadRequest(_StrictCadBase):
    operation: Literal["parameters"]
    include_model_params: bool = True
    include_user_params: bool = True


class VisibilityReadRequest(_StrictCadBase):
    operation: Literal["visibility"]
    target: TargetRef | None = None


class SelectionReadRequest(_StrictCadBase):
    operation: Literal["selection"]


class QueryReadRequest(_StrictCadBase):
    operation: Literal["query"]
    selector: EntitySelector
    limit: int = 100


class CapabilitiesReadRequest(_StrictCadBase):
    operation: Literal["capabilities"]


FusionReadRequest = Annotated[
    ModelSnapshotRequest
    | EntityReadRequest
    | FeatureTreeRequest
    | SketchReadRequest
    | ParametersReadRequest
    | VisibilityReadRequest
    | SelectionReadRequest
    | QueryReadRequest
    | CapabilitiesReadRequest,
    Field(discriminator="operation"),
]


# ==========================================
# 2. fusion_inspect requests
# ==========================================

class DescribeInspectRequest(_StrictCadBase):
    operation: Literal["describe"]
    target: TargetRef


class BoundingBoxInspectRequest(_StrictCadBase):
    operation: Literal["bounding_box"]
    target: TargetRef
    frame: CoordinateFrame


class OrientedBboxInspectRequest(_StrictCadBase):
    operation: Literal["oriented_bbox"]
    target: TargetRef


class CentroidInspectRequest(_StrictCadBase):
    operation: Literal["centroid"]
    target: TargetRef
    frame: CoordinateFrame


class AreaInspectRequest(_StrictCadBase):
    operation: Literal["area"]
    target: TargetRef


class PerimeterInspectRequest(_StrictCadBase):
    operation: Literal["perimeter"]
    target: TargetRef


class VolumeInspectRequest(_StrictCadBase):
    operation: Literal["volume"]
    target: TargetRef


class DistanceInspectRequest(_StrictCadBase):
    operation: Literal["distance"]
    target_a: TargetRef
    target_b: TargetRef


class MinimumDistanceInspectRequest(_StrictCadBase):
    operation: Literal["minimum_distance"]
    target_a: TargetRef
    target_b: TargetRef


class AngleInspectRequest(_StrictCadBase):
    operation: Literal["angle"]
    target_a: TargetRef
    target_b: TargetRef


class ParallelInspectRequest(_StrictCadBase):
    operation: Literal["parallel"]
    target_a: TargetRef
    target_b: TargetRef
    tolerance_deg: float = 0.01


class PerpendicularInspectRequest(_StrictCadBase):
    operation: Literal["perpendicular"]
    target_a: TargetRef
    target_b: TargetRef
    tolerance_deg: float = 0.01


class CoplanarInspectRequest(_StrictCadBase):
    operation: Literal["coplanar"]
    target_a: TargetRef
    target_b: TargetRef
    tolerance_mm: float = 0.001


class ConcentricInspectRequest(_StrictCadBase):
    operation: Literal["concentric"]
    target_a: TargetRef
    target_b: TargetRef
    tolerance_deg: float = 0.01
    tolerance_mm: float = 0.001


class FaceToFaceThicknessInspectRequest(_StrictCadBase):
    operation: Literal["face_to_face_thickness"]
    face_a: TargetRef
    face_b: TargetRef


FusionInspectRequest = Annotated[
    DescribeInspectRequest
    | BoundingBoxInspectRequest
    | OrientedBboxInspectRequest
    | CentroidInspectRequest
    | AreaInspectRequest
    | PerimeterInspectRequest
    | VolumeInspectRequest
    | DistanceInspectRequest
    | MinimumDistanceInspectRequest
    | AngleInspectRequest
    | ParallelInspectRequest
    | PerpendicularInspectRequest
    | CoplanarInspectRequest
    | ConcentricInspectRequest
    | FaceToFaceThicknessInspectRequest,
    Field(discriminator="operation"),
]


# ==========================================
# 3. fusion_view requests
# ==========================================

class CameraReadRequest(_StrictCadBase):
    operation: Literal["camera_read"]


class CameraSetRequest(_StrictCadBase):
    operation: Literal["camera_set"]
    eye: Point3 | None = None
    target: Point3 | None = None
    up: Vector3 | None = None
    fov: float | None = None


class FitViewRequest(_StrictCadBase):
    operation: Literal["fit"]


class ZoomEntityViewRequest(_StrictCadBase):
    operation: Literal["zoom_entity"]
    target: TargetRef


class OrientToFaceViewRequest(_StrictCadBase):
    operation: Literal["orient_to_face"]
    target: TargetRef


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
    view_ref: str = Field(..., pattern=VIEW_REF_PATTERN)
    x: float
    y: float
    coordinate_space: Literal["normalized", "pixel"] = "normalized"
    filters: tuple[str, ...] = Field(default_factory=tuple)


FusionViewRequest = Annotated[
    CameraReadRequest
    | CameraSetRequest
    | FitViewRequest
    | ZoomEntityViewRequest
    | OrientToFaceViewRequest
    | StandardViewRequest
    | ScreenshotViewRequest
    | PickRequest,
    Field(discriminator="operation"),
]


# ==========================================
# 4. fusion_metadata requests
# ==========================================

class GetMetadataRequest(_StrictCadBase):
    operation: Literal["get"]
    target: TargetRef
    group: str | None = None


class SetMetadataRequest(_StrictCadBase):
    operation: Literal["set"]
    target: TargetRef
    group: str = "bridge.cad/v1"
    name: str = Field(..., min_length=1)
    value: Any
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)


class RemoveMetadataRequest(_StrictCadBase):
    operation: Literal["remove"]
    target: TargetRef
    group: str = "bridge.cad/v1"
    name: str = Field(..., min_length=1)
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)


class QueryMetadataRequest(_StrictCadBase):
    operation: Literal["query"]
    group: str | None = None
    name: str | None = None
    value: Any | None = None


class TagMetadataRequest(_StrictCadBase):
    operation: Literal["tag"]
    target: TargetRef
    tag_name: str = Field(..., min_length=1)
    tag_value: str = ""
    group: str = "bridge.cad/v1"
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)


class UntagMetadataRequest(_StrictCadBase):
    operation: Literal["untag"]
    target: TargetRef
    tag_name: str = Field(..., min_length=1)
    group: str = "bridge.cad/v1"
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)


class SetRoleMetadataRequest(_StrictCadBase):
    operation: Literal["set_role"]
    target: TargetRef
    role: str = Field(..., min_length=1)
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)


class ClearRoleMetadataRequest(_StrictCadBase):
    operation: Literal["clear_role"]
    target: TargetRef
    role: str | None = None
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)


class ProvenanceMetadataRequest(_StrictCadBase):
    operation: Literal["provenance"]
    target: TargetRef


FusionMetadataRequest = Annotated[
    GetMetadataRequest
    | SetMetadataRequest
    | RemoveMetadataRequest
    | QueryMetadataRequest
    | TagMetadataRequest
    | UntagMetadataRequest
    | SetRoleMetadataRequest
    | ClearRoleMetadataRequest
    | ProvenanceMetadataRequest,
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
    position: Point3
    target_plane_or_face: TargetRef | None = None
    alignment: Literal["left", "center", "right"] = "left"
    flip_x: bool = False
    flip_y: bool = False
    role: str = "decorative_text"
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)


class TextReadRequest(_StrictCadBase):
    operation: Literal["text_read"]
    text_ref: str = Field(..., pattern=TEXT_REF_PATTERN)


class TextUpdateRequest(_StrictCadBase):
    operation: Literal["text_update"]
    text_ref: str = Field(..., pattern=TEXT_REF_PATTERN)
    text: str | None = None
    font: str | None = None
    height_mm: float | None = Field(default=None, gt=0)
    position: Point3 | None = None
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)


class TextDeleteRequest(_StrictCadBase):
    operation: Literal["text_delete"]
    text_ref: str = Field(..., pattern=TEXT_REF_PATTERN)
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)


class TextExtrudeRequest(_StrictCadBase):
    operation: Literal["text_extrude"]
    text_ref: str = Field(..., pattern=TEXT_REF_PATTERN)
    distance_mm: float
    operation_type: Literal["new_body", "join", "cut", "intersect"] = "new_body"
    target_body: TargetRef | None = None
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)


class TextCutRequest(_StrictCadBase):
    operation: Literal["text_cut"]
    text_ref: str = Field(..., pattern=TEXT_REF_PATTERN)
    distance_mm: float
    target_body: TargetRef
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)


class ShowStyleRequest(_StrictCadBase):
    operation: Literal["show"]
    target: TargetRef
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)


class HideStyleRequest(_StrictCadBase):
    operation: Literal["hide"]
    target: TargetRef
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)


class SetVisibilityStyleRequest(_StrictCadBase):
    operation: Literal["set"]
    target: TargetRef
    visible: bool
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)


class ShowOnlyStyleRequest(_StrictCadBase):
    operation: Literal["show_only"]
    target: TargetRef
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)


class IsolateStyleRequest(_StrictCadBase):
    operation: Literal["isolate"]
    target: TargetRef
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)


class RestoreVisibilityStyleRequest(_StrictCadBase):
    operation: Literal["restore"]
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)


FusionStyleRequest = Annotated[
    TextCreateRequest
    | TextReadRequest
    | TextUpdateRequest
    | TextDeleteRequest
    | TextExtrudeRequest
    | TextCutRequest
    | ShowStyleRequest
    | HideStyleRequest
    | SetVisibilityStyleRequest
    | ShowOnlyStyleRequest
    | IsolateStyleRequest
    | RestoreVisibilityStyleRequest,
    Field(discriminator="operation"),
]


# ==========================================
# 6. fusion_validate requests
# ==========================================

class ValidateRunRequest(_StrictCadBase):
    operation: Literal["run"]
    profiles: tuple[str, ...] = Field(
        default_factory=lambda: (
            "parametric_health",
            "model_hygiene",
            "reference_integrity",
            "text_integrity",
            "pre_mutation",
        )
    )
    checks: tuple[str, ...] = Field(default_factory=tuple)
    fail_on: Literal["WARN", "RED"] | None = None


FusionValidateRequest = Annotated[
    ValidateRunRequest,
    Field(discriminator="operation"),
]


# ==========================================
# 7. fusion_transaction requests & actions
# ==========================================

class StageTextCreateAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_type: Literal["text_create"]
    text: str = Field(..., min_length=1)
    font: str = "Arial"
    height_mm: float = Field(..., gt=0)
    position: Point3
    target_plane_or_face: TargetRef | None = None
    alignment: Literal["left", "center", "right"] = "left"
    flip_x: bool = False
    flip_y: bool = False
    role: str = "decorative_text"


class StageTextUpdateAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_type: Literal["text_update"]
    text_ref: str = Field(..., pattern=TEXT_REF_PATTERN)
    text: str | None = None
    font: str | None = None
    height_mm: float | None = Field(default=None, gt=0)
    position: Point3 | None = None


class StageTextDeleteAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_type: Literal["text_delete"]
    text_ref: str = Field(..., pattern=TEXT_REF_PATTERN)


class StageTextExtrudeAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_type: Literal["text_extrude"]
    text_ref: str = Field(..., pattern=TEXT_REF_PATTERN)
    distance_mm: float
    operation_type: Literal["new_body", "join", "cut", "intersect"] = "new_body"
    target_body: TargetRef | None = None


class StageTextCutAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_type: Literal["text_cut"]
    text_ref: str = Field(..., pattern=TEXT_REF_PATTERN)
    distance_mm: float
    target_body: TargetRef


class StageVisibilityShowAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_type: Literal["visibility_show", "show"]
    target: TargetRef


class StageVisibilityHideAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_type: Literal["visibility_hide", "hide"]
    target: TargetRef


class StageVisibilitySetAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_type: Literal["visibility_set", "set"]
    target: TargetRef
    visible: bool


class StageVisibilityShowOnlyAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_type: Literal["visibility_show_only", "show_only"]
    target: TargetRef


class StageVisibilityIsolateAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_type: Literal["visibility_isolate", "isolate"]
    target: TargetRef


class StageVisibilityRestoreAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_type: Literal["visibility_restore", "restore"]


StageVisibilityAction = Annotated[
    StageVisibilityShowAction
    | StageVisibilityHideAction
    | StageVisibilitySetAction
    | StageVisibilityShowOnlyAction
    | StageVisibilityIsolateAction
    | StageVisibilityRestoreAction,
    Field(discriminator="action_type"),
]


class StageMetadataSetAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_type: Literal["metadata_set"]
    target: TargetRef
    name: str = Field(..., min_length=1)
    value: str | int | float | bool
    group: str = "bridge.cad/v1"


class StageMetadataRemoveAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_type: Literal["metadata_remove"]
    target: TargetRef
    name: str = Field(..., min_length=1)
    group: str = "bridge.cad/v1"


class StageMetadataTagAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_type: Literal["metadata_tag"]
    target: TargetRef
    tag_name: str = Field(..., min_length=1)
    tag_value: str = ""
    group: str = "bridge.cad/v1"


class StageMetadataUntagAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_type: Literal["metadata_untag"]
    target: TargetRef
    tag_name: str = Field(..., min_length=1)
    group: str = "bridge.cad/v1"


class StageMetadataSetRoleAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_type: Literal["metadata_set_role"]
    target: TargetRef
    role: str = Field(..., min_length=1)


class StageMetadataClearRoleAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_type: Literal["metadata_clear_role"]
    target: TargetRef
    role: str | None = None


TransactionStageAction = Annotated[
    StageTextCreateAction
    | StageTextUpdateAction
    | StageTextDeleteAction
    | StageTextExtrudeAction
    | StageTextCutAction
    | StageVisibilityShowAction
    | StageVisibilityHideAction
    | StageVisibilitySetAction
    | StageVisibilityShowOnlyAction
    | StageVisibilityIsolateAction
    | StageVisibilityRestoreAction
    | StageMetadataSetAction
    | StageMetadataRemoveAction
    | StageMetadataTagAction
    | StageMetadataUntagAction
    | StageMetadataSetRoleAction
    | StageMetadataClearRoleAction,
    Field(discriminator="action_type"),
]


class TransactionBeginRequest(_StrictCadBase):
    operation: Literal["begin"]
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)


class TransactionStageRequest(_StrictCadBase):
    operation: Literal["stage"]
    transaction_id: str = Field(..., pattern=TRANSACTION_ID_PATTERN)
    action: TransactionStageAction


class TransactionPreviewRequest(_StrictCadBase):
    operation: Literal["preview"]
    transaction_id: str = Field(..., pattern=TRANSACTION_ID_PATTERN)
    include_diff: bool = True
    include_validation: bool = True
    include_screenshot: bool = False
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)


class TransactionCommitRequest(_StrictCadBase):
    operation: Literal["commit"]
    transaction_id: str = Field(..., pattern=TRANSACTION_ID_PATTERN)
    expected_revision: str | None = Field(default=None, pattern=MODEL_REVISION_PATTERN)


class TransactionRollbackRequest(_StrictCadBase):
    operation: Literal["rollback"]
    transaction_id: str = Field(..., pattern=TRANSACTION_ID_PATTERN)


class TransactionAbortRequest(_StrictCadBase):
    operation: Literal["abort"]
    transaction_id: str = Field(..., pattern=TRANSACTION_ID_PATTERN)


class TransactionStatusRequest(_StrictCadBase):
    operation: Literal["status"]
    transaction_id: str | None = Field(default=None, pattern=TRANSACTION_ID_PATTERN)


FusionTransactionRequest = Annotated[
    TransactionBeginRequest
    | TransactionStageRequest
    | TransactionPreviewRequest
    | TransactionCommitRequest
    | TransactionRollbackRequest
    | TransactionAbortRequest
    | TransactionStatusRequest,
    Field(discriminator="operation"),
]
