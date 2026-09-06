from __future__ import annotations

from typing import Any

import pytest

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.models import (
    BoundingBox,
    CoordinateFrame,
    EntityRef,
    Plane,
    Point3,
    Ray,
    Transform,
    Vector3,
)
from app.fusion_cad.refs import (
    EntityRefRegistry,
    InternalEntityRecord,
    ResolutionOutcome,
    convert_bounding_box,
    convert_plane,
    convert_point,
    convert_ray,
    convert_transform,
    convert_vector,
)


@pytest.mark.parametrize(
    "outcome",
    ["exact", "split", "stale", "wrong_document", "ambiguous"],
)
def test_resolver_preserves_outcome(outcome: ResolutionOutcome) -> None:
    registry = EntityRefRegistry()
    active_doc = "doc_active_1"

    issued_ref = registry.issue(
        document_ref=active_doc,
        native_token="tok_body_1",
        kind="body",
        name="MainBody",
    )
    assert issued_ref.ref.startswith("ent_")
    assert issued_ref.ref != "tok_body_1"

    native_lookup_called = False

    def mock_native_resolver(
        record: InternalEntityRecord,
    ) -> tuple[ResolutionOutcome, list[Any]]:
        nonlocal native_lookup_called
        native_lookup_called = True
        if outcome == "exact":
            return "exact", [{"token": record.native_token, "id": "native_body_1"}]
        elif outcome == "split":
            return "split", [
                {"token": "tok_split_a", "id": "split_1"},
                {"token": "tok_split_b", "id": "split_2"},
            ]
        elif outcome == "stale":
            return "stale", []
        elif outcome == "ambiguous":
            return "ambiguous", [
                {"token": "tok_cand_1", "id": "cand_1"},
                {"token": "tok_cand_2", "id": "cand_2"},
            ]
        elif outcome == "wrong_document":
            return "wrong_document", []
        raise ValueError(f"Unhandled outcome: {outcome}")

    if outcome == "wrong_document":
        res = registry.resolve(
            issued_ref,
            active_document_ref="doc_different_2",
            native_resolver=mock_native_resolver,
        )
        assert res.outcome == "wrong_document"
        assert res.candidates == ()
        assert native_lookup_called is False

        with pytest.raises(FusionCadError) as exc_info:
            registry.resolve_one(
                issued_ref,
                active_document_ref="doc_different_2",
                native_resolver=mock_native_resolver,
            )
        assert exc_info.value.code == ErrorCode.WRONG_DOCUMENT
        assert native_lookup_called is False
    else:
        res = registry.resolve(
            issued_ref,
            active_document_ref=active_doc,
            native_resolver=mock_native_resolver,
        )
        assert res.outcome == outcome
        assert native_lookup_called is True

        if outcome == "exact":
            assert len(res.candidates) == 1
            single = registry.resolve_one(
                issued_ref,
                active_document_ref=active_doc,
                native_resolver=mock_native_resolver,
            )
            assert single["id"] == "native_body_1"

        elif outcome == "split":
            assert len(res.candidates) == 2
            assert res.candidates[0]["id"] == "split_1"
            assert res.candidates[1]["id"] == "split_2"
            with pytest.raises(FusionCadError) as exc_info:
                registry.resolve_one(
                    issued_ref,
                    active_document_ref=active_doc,
                    native_resolver=mock_native_resolver,
                )
            assert exc_info.value.code == ErrorCode.REF_SPLIT
            assert exc_info.value.details.get("candidate_count") == 2

        elif outcome == "stale":
            assert res.candidates == ()
            with pytest.raises(FusionCadError) as exc_info:
                registry.resolve_one(
                    issued_ref,
                    active_document_ref=active_doc,
                    native_resolver=mock_native_resolver,
                )
            assert exc_info.value.code == ErrorCode.REF_STALE

        elif outcome == "ambiguous":
            assert len(res.candidates) == 2
            with pytest.raises(FusionCadError) as exc_info:
                registry.resolve_one(
                    issued_ref,
                    active_document_ref=active_doc,
                    native_resolver=mock_native_resolver,
                )
            assert exc_info.value.code == ErrorCode.REF_AMBIGUOUS
            assert exc_info.value.details.get("candidate_count") == 2


def test_public_ref_is_opaque_and_never_exposes_native_token() -> None:
    registry = EntityRefRegistry()
    raw_token = "adsk::native::token::0123456789abcdef"

    ref = registry.issue(
        document_ref="doc_123",
        native_token=raw_token,
        kind="face",
        stability="persistent",
        native_type="adsk::fusion::BRepFace",
        name="TopFace",
        component_path=("Root", "Sub:1"),
    )

    assert isinstance(ref, EntityRef)
    assert ref.ref.startswith("ent_")
    assert ref.ref != raw_token
    assert raw_token not in ref.ref
    assert not hasattr(ref, "native_token")

    internal = registry.get_internal_record(ref.ref, document_ref="doc_123")
    assert internal is not None
    assert internal.native_token == raw_token
    assert internal.kind == "face"
    assert internal.document_ref == "doc_123"
    assert internal.component_path == ("Root", "Sub:1")


def test_registry_reuse_and_isolation_no_singleton() -> None:
    reg1 = EntityRefRegistry(max_documents=2, max_entries_per_doc=3)
    reg2 = EntityRefRegistry(max_documents=2, max_entries_per_doc=3)

    ref1 = reg1.issue(document_ref="doc_a", native_token="tok_1", kind="body")
    ref1_again = reg1.issue(document_ref="doc_a", native_token="tok_1", kind="body")
    assert ref1.ref == ref1_again.ref

    assert reg2.get_internal_record(ref1.ref, document_ref="doc_a") is None

    reg1.issue(document_ref="doc_a", native_token="tok_2", kind="body")
    reg1.issue(document_ref="doc_a", native_token="tok_3", kind="body")
    reg1.issue(document_ref="doc_a", native_token="tok_4", kind="body")
    assert reg1.get_internal_record(ref1.ref, document_ref="doc_a") is None

    reg1.issue(document_ref="doc_b", native_token="tok_b1", kind="body")
    reg1.issue(document_ref="doc_c", native_token="tok_c1", kind="body")
    assert reg1.has_document("doc_a") is False
    assert reg1.has_document("doc_b") is True
    assert reg1.has_document("doc_c") is True


def test_coordinate_frame_conversions_world_component_sketch() -> None:
    world_frame = CoordinateFrame(space="world")
    comp_frame = CoordinateFrame(space="component", ref="ent_comp_1")
    sketch_frame = CoordinateFrame(space="sketch", ref="ent_sketch_1")

    transform_matrix = (
        (1.0, 0.0, 0.0, 10.0),
        (0.0, 1.0, 0.0, 20.0),
        (0.0, 0.0, 1.0, 30.0),
        (0.0, 0.0, 0.0, 1.0),
    )

    pt = Point3(x=1.0, y=2.0, z=3.0, frame=comp_frame)
    pt_world = convert_point(
        pt, target_frame=world_frame, transform_matrix=transform_matrix
    )
    assert pt_world.frame == world_frame
    assert pt_world.x == 11.0
    assert pt_world.y == 22.0
    assert pt_world.z == 33.0

    pt_identity = convert_point(pt, target_frame=comp_frame)
    assert pt_identity == pt

    vec = Vector3(x=1.0, y=0.0, z=0.0, frame=comp_frame)
    vec_world = convert_vector(
        vec, target_frame=world_frame, transform_matrix=transform_matrix
    )
    assert vec_world.frame == world_frame
    assert vec_world.x == 1.0
    assert vec_world.y == 0.0
    assert vec_world.z == 0.0

    bbox = BoundingBox(
        min_point=Point3(x=0.0, y=0.0, z=0.0, frame=comp_frame),
        max_point=Point3(x=5.0, y=5.0, z=5.0, frame=comp_frame),
        frame=comp_frame,
    )
    bbox_world = convert_bounding_box(
        bbox, target_frame=world_frame, transform_matrix=transform_matrix
    )
    assert bbox_world.frame == world_frame
    assert bbox_world.min_point.frame == world_frame
    assert bbox_world.max_point.frame == world_frame
    assert bbox_world.min_point.x == 10.0
    assert bbox_world.min_point.y == 20.0
    assert bbox_world.min_point.z == 30.0
    assert bbox_world.max_point.x == 15.0
    assert bbox_world.max_point.y == 25.0
    assert bbox_world.max_point.z == 35.0

    plane = Plane(
        origin=Point3(x=0.0, y=0.0, z=0.0, frame=comp_frame),
        normal=Vector3(x=0.0, y=0.0, z=1.0, frame=comp_frame),
        frame=comp_frame,
    )
    plane_world = convert_plane(
        plane, target_frame=world_frame, transform_matrix=transform_matrix
    )
    assert plane_world.frame == world_frame
    assert plane_world.origin.x == 10.0
    assert plane_world.origin.y == 20.0
    assert plane_world.origin.z == 30.0
    assert plane_world.normal.z == 1.0

    ray = Ray(
        origin=Point3(x=1.0, y=1.0, z=1.0, frame=comp_frame),
        direction=Vector3(x=0.0, y=1.0, z=0.0, frame=comp_frame),
        frame=comp_frame,
    )
    ray_world = convert_ray(
        ray, target_frame=world_frame, transform_matrix=transform_matrix
    )
    assert ray_world.frame == world_frame
    assert ray_world.origin.x == 11.0
    assert ray_world.direction.y == 1.0

    xf = Transform(matrix=transform_matrix, frame=comp_frame)
    xf_world = convert_transform(
        xf, target_frame=sketch_frame, transform_matrix=transform_matrix
    )
    assert xf_world.frame == sketch_frame
    # M @ M: translation becomes (20.0, 40.0, 60.0)
    assert xf_world.matrix[0][3] == 20.0
    assert xf_world.matrix[1][3] == 40.0
    assert xf_world.matrix[2][3] == 60.0


def test_cross_frame_conversions_require_verified_transform_no_identity_fallback() -> None:
    world_frame = CoordinateFrame(space="world")
    comp_frame = CoordinateFrame(space="component", ref="ent_comp_1")
    sketch_frame = CoordinateFrame(space="sketch", ref="ent_sketch_1")

    pt = Point3(x=1.0, y=2.0, z=3.0, frame=comp_frame)
    vec = Vector3(x=1.0, y=0.0, z=0.0, frame=comp_frame)
    bbox = BoundingBox(min_point=pt, max_point=pt, frame=comp_frame)
    pln = Plane(origin=pt, normal=vec, frame=comp_frame)
    ray = Ray(origin=pt, direction=vec, frame=comp_frame)
    xf = Transform(
        matrix=(
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ),
        frame=comp_frame,
    )

    # Different frames without transform matrix must fail closed as CAPABILITY_DEGRADED
    for target in (world_frame, sketch_frame):
        with pytest.raises(FusionCadError) as exc_info:
            convert_point(pt, target_frame=target)
        assert exc_info.value.code == ErrorCode.CAPABILITY_DEGRADED

        with pytest.raises(FusionCadError) as exc_info:
            convert_vector(vec, target_frame=target)
        assert exc_info.value.code == ErrorCode.CAPABILITY_DEGRADED

        with pytest.raises(FusionCadError) as exc_info:
            convert_bounding_box(bbox, target_frame=target)
        assert exc_info.value.code == ErrorCode.CAPABILITY_DEGRADED

        with pytest.raises(FusionCadError) as exc_info:
            convert_plane(pln, target_frame=target)
        assert exc_info.value.code == ErrorCode.CAPABILITY_DEGRADED

        with pytest.raises(FusionCadError) as exc_info:
            convert_ray(ray, target_frame=target)
        assert exc_info.value.code == ErrorCode.CAPABILITY_DEGRADED

        with pytest.raises(FusionCadError) as exc_info:
            convert_transform(xf, target_frame=target)
        assert exc_info.value.code == ErrorCode.CAPABILITY_DEGRADED

    # Same-frame identity remains allowed without transform matrix
    assert convert_point(pt, target_frame=comp_frame) == pt
    assert convert_vector(vec, target_frame=comp_frame) == vec
    assert convert_bounding_box(bbox, target_frame=comp_frame) == bbox
    assert convert_plane(pln, target_frame=comp_frame) == pln
    assert convert_ray(ray, target_frame=comp_frame) == ray
    assert convert_transform(xf, target_frame=comp_frame) == xf


def test_convert_transform_mathematical_composition_and_point_consistency() -> None:
    comp_frame = CoordinateFrame(space="component", ref="ent_comp_1")
    world_frame = CoordinateFrame(space="world")

    # Frame conversion matrix M: rotation 90 deg around Z + translation (10, 20, 30)
    # x' = -y + 10, y' = x + 20, z' = z + 30
    frame_m = (
        (0.0, -1.0, 0.0, 10.0),
        (1.0, 0.0, 0.0, 20.0),
        (0.0, 0.0, 1.0, 30.0),
        (0.0, 0.0, 0.0, 1.0),
    )

    # Transform A in component frame: translation (2, 3, 5)
    transform_a = Transform(
        matrix=(
            (1.0, 0.0, 0.0, 2.0),
            (0.0, 1.0, 0.0, 3.0),
            (0.0, 0.0, 1.0, 5.0),
            (0.0, 0.0, 0.0, 1.0),
        ),
        frame=comp_frame,
    )

    converted_xf = convert_transform(
        transform_a, target_frame=world_frame, transform_matrix=frame_m
    )
    assert converted_xf.frame == world_frame

    # Verify consistency with point conversion: for any p, (M @ A) @ p == convert_point(A @ p, target)
    test_pt = Point3(x=4.0, y=7.0, z=1.0, frame=comp_frame)

    # A @ p in comp_frame: (4+2, 7+3, 1+5) = (6, 10, 6)
    pt_after_a = Point3(
        x=transform_a.matrix[0][0] * test_pt.x + transform_a.matrix[0][3],
        y=transform_a.matrix[1][1] * test_pt.y + transform_a.matrix[1][3],
        z=transform_a.matrix[2][2] * test_pt.z + transform_a.matrix[2][3],
        frame=comp_frame,
    )
    assert pt_after_a.x == 6.0 and pt_after_a.y == 10.0 and pt_after_a.z == 6.0

    # convert_point(A @ p, world_frame)
    pt_via_convert = convert_point(
        pt_after_a, target_frame=world_frame, transform_matrix=frame_m
    )
    # Expected: x = -10 + 10 = 0.0, y = 6 + 20 = 26.0, z = 6 + 30 = 36.0
    assert pt_via_convert.x == 0.0
    assert pt_via_convert.y == 26.0
    assert pt_via_convert.z == 36.0

    # Applying converted_xf directly to test_pt
    cm = converted_xf.matrix
    pt_via_composed = Point3(
        x=cm[0][0] * test_pt.x + cm[0][1] * test_pt.y + cm[0][2] * test_pt.z + cm[0][3],
        y=cm[1][0] * test_pt.x + cm[1][1] * test_pt.y + cm[1][2] * test_pt.z + cm[1][3],
        z=cm[2][0] * test_pt.x + cm[2][1] * test_pt.y + cm[2][2] * test_pt.z + cm[2][3],
        frame=world_frame,
    )
    assert pt_via_composed.x == pt_via_convert.x
    assert pt_via_composed.y == pt_via_convert.y
    assert pt_via_composed.z == pt_via_convert.z


def test_resolve_one_exact_with_multiple_candidates_fails_closed_ref_ambiguous() -> None:
    registry = EntityRefRegistry()
    active_doc = "doc_doc1"
    issued = registry.issue(document_ref=active_doc, kind="body", name="TestBody")

    # Native resolver buggy/flaky: declares "exact" but returns 2 candidates
    def buggy_native_resolver(
        record: InternalEntityRecord,
    ) -> tuple[ResolutionOutcome, list[Any]]:
        return "exact", [{"id": "candidate_1"}, {"id": "candidate_2"}]

    with pytest.raises(FusionCadError) as exc_info:
        registry.resolve_one(
            issued,
            active_document_ref=active_doc,
            native_resolver=buggy_native_resolver,
        )

    # Must fail closed with REF_AMBIGUOUS, never return candidate_1
    assert exc_info.value.code == ErrorCode.REF_AMBIGUOUS
    assert exc_info.value.details.get("candidate_count") == 2
    assert exc_info.value.details.get("outcome") == "exact"


def test_resolve_one_exact_with_zero_candidates_fails_closed_ref_stale() -> None:
    registry = EntityRefRegistry()
    active_doc = "doc_doc1"
    issued = registry.issue(document_ref=active_doc, kind="body", name="TestBody")

    def empty_native_resolver(
        record: InternalEntityRecord,
    ) -> tuple[ResolutionOutcome, list[Any]]:
        return "exact", []

    with pytest.raises(FusionCadError) as exc_info:
        registry.resolve_one(
            issued,
            active_document_ref=active_doc,
            native_resolver=empty_native_resolver,
        )

    assert exc_info.value.code == ErrorCode.REF_STALE
