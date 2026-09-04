from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.errors import BridgeError, ErrorCode
from app.fusion_cad.errors import (
    cad_error_to_bridge_error,
    is_cad_error_retryable,
)
from app.fusion_cad.models import (
    BoundingBox,
    CadResult,
    CapabilityRecord,
    CoordinateFrame,
    DocumentState,
    EntityRef,
    EntitySelector,
    Plane,
    Point3,
    Ray,
    Transform,
    ValidationFinding,
    ValidationReport,
    ValidationReportRef,
    Vector3,
    ViewRefSummary,
)


def test_world_frame_rejects_entity_ref() -> None:
    with pytest.raises(ValidationError):
        CoordinateFrame(space="world", ref="ent_component")


def test_occurrence_frame_requires_entity_ref() -> None:
    with pytest.raises(ValidationError):
        CoordinateFrame(space="occurrence", ref=None)


def test_component_frame_requires_entity_ref() -> None:
    with pytest.raises(ValidationError):
        CoordinateFrame(space="component", ref=None)


def test_sketch_frame_requires_entity_ref() -> None:
    with pytest.raises(ValidationError):
        CoordinateFrame(space="sketch", ref=None)


def test_coordinate_frame_valid_instances() -> None:
    world = CoordinateFrame(space="world")
    assert world.space == "world"
    assert world.ref is None

    occ = CoordinateFrame(space="occurrence", ref="ent_occ_1")
    assert occ.space == "occurrence"
    assert occ.ref == "ent_occ_1"

    comp = CoordinateFrame(space="component", ref="ent_comp_1")
    assert comp.space == "component"
    assert comp.ref == "ent_comp_1"

    sketch = CoordinateFrame(space="sketch", ref="ent_sketch_1")
    assert sketch.space == "sketch"
    assert sketch.ref == "ent_sketch_1"


def test_coordinate_frame_is_immutable_and_forbids_extra() -> None:
    frame = CoordinateFrame(space="world")
    with pytest.raises(ValidationError):
        CoordinateFrame(space="world", extra_param=123)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        frame.space = "occurrence"  # type: ignore[misc]


def test_entity_ref_is_document_scoped() -> None:
    value = EntityRef(
        ref="ent_abcd",
        kind="face",
        document_ref="doc_1234",
        stability="persistent",
    )
    assert value.document_ref == "doc_1234"
    assert value.ref == "ent_abcd"
    assert value.kind == "face"
    assert value.stability == "persistent"
    assert value.component_path == ()


def test_entity_ref_forbids_native_token() -> None:
    with pytest.raises(ValidationError):
        EntityRef(
            ref="ent_abcd",
            kind="face",
            document_ref="doc_1234",
            stability="persistent",
            native_token="adsk_internal_token",  # type: ignore[call-arg]
        )


def test_entity_selector_creation_and_immutability() -> None:
    selector = EntitySelector(
        kind=["body"],
        name={"regex": "^AZURE_"},
        component_path=["Root", "LEFT"],
        role=["decorative_text"],
        visible=True,
    )
    assert selector.kind == ["body"]
    assert selector.visible is True
    with pytest.raises(ValidationError):
        EntitySelector(unknown_field="invalid")  # type: ignore[call-arg]


def test_capability_record() -> None:
    cap = CapabilityRecord(
        name="view.pick",
        state="supported",
        implementation="native-preselect",
        fusion_version="2.0.18000",
        relay_version="1.0.0",
        limitations=["viewport only"],
    )
    assert cap.name == "view.pick"
    assert cap.state == "supported"
    assert cap.limitations == ["viewport only"]


def test_cad_result_envelope() -> None:
    result = CadResult(
        api_version="fusion.cad/v1",
        status="succeeded",
        operation_id="op_12345",
        document=DocumentState(document_ref="doc_1", model_revision="rev_1"),
        summary="Extruded text profile successfully",
        data={"body_count": 2},
        changed_refs=["ent_body_1", "ent_body_2"],
    )
    assert result.api_version == "fusion.cad/v1"
    assert result.status == "succeeded"
    assert result.document is not None
    assert result.document.document_ref == "doc_1"
    assert result.changed_refs == ["ent_body_1", "ent_body_2"]


def test_view_ref_summary() -> None:
    view = ViewRefSummary(
        view_ref="view_100",
        model_revision="rev_42",
        camera_revision="cam_1",
        visibility_revision="vis_1",
        width=1920,
        height=1080,
        image="resource://fusion/artifacts/screenshot.png",
    )
    assert view.view_ref == "view_100"
    assert view.width == 1920
    assert view.height == 1080


def test_validation_structures() -> None:
    finding = ValidationFinding(
        check_id="duplicate_body",
        severity="warn",
        message="Suspicious duplicate body detected",
        entity_refs=["ent_b1", "ent_b2"],
        evidence={"delta_volume": 0.0},
        suggested_action="Delete orphaned duplicate body",
    )
    report = ValidationReport(
        verdict="WARN",
        profiles=["model_hygiene"],
        checks_run=["duplicate_body", "timeline_health"],
        findings=[finding],
        summary="1 warning found",
        model_revision="rev_10",
    )
    report_ref = ValidationReportRef(
        report_id="val_10",
        verdict="WARN",
        summary="1 warning found",
        finding_count=1,
    )
    assert report.verdict == "WARN"
    assert len(report.findings) == 1
    assert report_ref.finding_count == 1


def test_geometry_types_with_frame() -> None:
    frame = CoordinateFrame(space="component", ref="ent_comp_1")
    p = Point3(x=10.0, y=20.0, z=30.0, frame=frame)
    v = Vector3(x=0.0, y=0.0, z=1.0, frame=frame)
    bbox = BoundingBox(
        min_point=Point3(x=0.0, y=0.0, z=0.0, frame=frame),
        max_point=Point3(x=10.0, y=10.0, z=10.0, frame=frame),
        frame=frame,
    )
    transform = Transform(
        matrix=[
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        frame=frame,
    )
    plane = Plane(origin=p, normal=v, frame=frame)
    ray = Ray(origin=p, direction=v, frame=frame)

    assert p.x == 10.0
    assert v.z == 1.0
    assert bbox.max_point.x == 10.0
    assert transform.matrix[0][0] == 1.0
    assert plane.normal.z == 1.0
    assert ray.direction.z == 1.0


def test_cad_error_codes_exist_in_error_code_enum() -> None:
    required_codes = [
        "NO_ACTIVE_DESIGN",
        "WRONG_DOCUMENT",
        "REF_STALE",
        "REF_SPLIT",
        "REF_AMBIGUOUS",
        "TYPE_MISMATCH",
        "SELECTOR_EMPTY",
        "SELECTOR_AMBIGUOUS",
        "INVALID_ARGUMENT",
        "PRECONDITION_FAILED",
        "UNSUPPORTED_GEOMETRY",
        "CAPABILITY_UNAVAILABLE",
        "CAPABILITY_DEGRADED",
        "REVISION_CONFLICT",
        "VIEW_STALE",
        "FUSION_API_ERROR",
        "VALIDATION_FAILED",
        "TRANSACTION_CONFLICT",
        "CHECKPOINT_DIVERGED",
        "SAVE_CONFIRMATION_REQUIRED",
        "OPERATION_UNCERTAIN",
    ]
    for code_str in required_codes:
        assert hasattr(ErrorCode, code_str), f"ErrorCode missing {code_str}"
        assert getattr(ErrorCode, code_str).value == code_str


def test_cad_error_mapping_preserves_retryable_discipline() -> None:
    assert not is_cad_error_retryable(ErrorCode.REVISION_CONFLICT)
    assert not is_cad_error_retryable(ErrorCode.TRANSACTION_CONFLICT)
    assert not is_cad_error_retryable(ErrorCode.INVALID_ARGUMENT)
    assert not is_cad_error_retryable(ErrorCode.PRECONDITION_FAILED)
    assert not is_cad_error_retryable(ErrorCode.VALIDATION_FAILED)
    assert not is_cad_error_retryable(ErrorCode.SAVE_CONFIRMATION_REQUIRED)

    err = cad_error_to_bridge_error(
        ErrorCode.REVISION_CONFLICT,
        "Model revision changed from rev_1 to rev_2",
        details={"expected_revision": "rev_1", "actual_revision": "rev_2"},
    )
    assert isinstance(err, BridgeError)
    assert err.code == ErrorCode.REVISION_CONFLICT
    assert err.retryable is False
    assert err.details["expected_revision"] == "rev_1"
