from __future__ import annotations

import pytest

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.inspect import (
    normalize_bounding_box,
    normalize_centroid,
    normalize_describe,
    normalize_distance,
    normalize_inspect_result,
    normalize_measure,
    normalize_oriented_bbox,
    normalize_relation,
    normalize_thickness,
)


# =========================================================================
# Task 7 Step 1: unit/coordinate normalization (lengths mm, angle deg,
# area mm^2, volume mm^3, geometric points carry explicit frames)
# =========================================================================


def test_area_result_uses_mm_squared():
    res = normalize_inspect_result(
        {
            "operation": "area",
            "quantity": "area",
            "value": 600.0,
            "unit": "mm^2",
        },
        operation="area",
    )
    assert res["operation"] == "area"
    assert res["quantity"] == "area"
    assert res["value"] == 600.0
    assert res["unit"] == "mm^2"


def test_volume_result_uses_mm_cubed():
    res = normalize_inspect_result(
        {
            "operation": "volume",
            "quantity": "volume",
            "value": 2500.0,
            "unit": "mm^3",
        },
        operation="volume",
    )
    assert res["unit"] == "mm^3"
    assert res["quantity"] == "volume"


def test_perimeter_result_uses_mm():
    res = normalize_inspect_result(
        {
            "operation": "perimeter",
            "quantity": "perimeter",
            "value": 40.0,
            "unit": "mm",
        },
        operation="perimeter",
    )
    assert res["unit"] == "mm"


def test_angle_result_uses_degrees():
    res = normalize_inspect_result(
        {
            "operation": "angle",
            "quantity": "angle",
            "value": 45.0,
            "unit": "deg",
        },
        operation="angle",
    )
    assert res["unit"] == "deg"
    assert res["value"] == 45.0


def test_distance_and_minimum_distance_use_mm_with_points():
    for op in ("distance", "minimum_distance"):
        res = normalize_inspect_result(
            {
                "operation": op,
                "quantity": op,
                "value": 20.0,
                "unit": "mm",
                "from": {"x": 0.0, "y": 0.0, "z": 0.0, "frame": {"space": "world"}},
                "to": {"x": 20.0, "y": 0.0, "z": 0.0, "frame": {"space": "world"}},
            },
            operation=op,
        )
        assert res["unit"] == "mm"
        assert res["from_point"]["frame"]["space"] == "world"
        assert res["to_point"]["frame"]["space"] == "world"


def test_geometric_points_include_explicit_frames():
    res = normalize_centroid(
        {
            "operation": "centroid",
            "point": {"x": 5.0, "y": 6.0, "z": 7.0, "frame": {"space": "world"}},
        }
    )
    assert res.point.frame.space == "world"
    assert res.point.x == 5.0


def test_bounding_box_has_explicit_frame():
    res = normalize_bounding_box(
        {
            "operation": "bounding_box",
            "bounding_box": {
                "min": [0.0, 0.0, 0.0],
                "max": [10.0, 10.0, 10.0],
                "frame": {"space": "world"},
            },
        }
    )
    assert res.bounding_box.frame.space == "world"
    assert res.bounding_box.min_point.frame.space == "world"
    assert res.bounding_box.max_point.frame.space == "world"


def test_oriented_bbox_has_center_axes_extents_and_frame():
    res = normalize_oriented_bbox(
        {
            "operation": "oriented_bbox",
            "oriented_bbox": {
                "center": {
                    "x": 5.0,
                    "y": 5.0,
                    "z": 5.0,
                    "frame": {"space": "component", "ref": "ent_comp"},
                },
                "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                "extents": [5.0, 5.0, 5.0],
                "frame": {"space": "component", "ref": "ent_comp"},
            },
        }
    )
    assert len(res.axes) == 3
    assert res.extents == (5.0, 5.0, 5.0)
    assert res.center.frame.space == "component"
    assert res.frame.space == "component"


def test_describe_normalizes_measures_and_frame():
    res = normalize_describe(
        {
            "operation": "describe",
            "target": {
                "ref": "ent_b1",
                "kind": "body",
                "name": "Body1",
                "native_type": "BRepBody",
            },
            "frame": {"space": "world"},
            "measures": {
                "volume": {"quantity": "volume", "value": 1000.0, "unit": "mm^3"},
                "area": {"quantity": "area", "value": 600.0, "unit": "mm^2"},
                "bounding_box": {
                    "min": [0.0, 0.0, 0.0],
                    "max": [10.0, 10.0, 10.0],
                    "frame": {"space": "world"},
                },
            },
        }
    )
    assert res.ref == "ent_b1"
    assert res.kind == "body"
    assert res.frame.space == "world"
    assert res.measures["volume"]["unit"] == "mm^3"
    assert res.measures["area"]["unit"] == "mm^2"
    assert res.measures["bounding_box"]["bounding_box"]["min_point"]["x"] == 0.0
    assert res.measures["bounding_box"]["bounding_box"]["min_point"]["frame"]["space"] == "world"


# =========================================================================
# Task 7 Step 2: unsupported target types return TYPE_MISMATCH or
# UNSUPPORTED_GEOMETRY; never guessed/heuristic values
# =========================================================================


def test_unsupported_marker_raises_type_mismatch():
    with pytest.raises(FusionCadError) as exc:
        normalize_inspect_result({"unsupported": "TYPE_MISMATCH"}, operation="volume")
    assert exc.value.code == ErrorCode.TYPE_MISMATCH


def test_unsupported_marker_raises_unsupported_geometry():
    with pytest.raises(FusionCadError) as exc:
        normalize_inspect_result(
            {"unsupported": "UNSUPPORTED_GEOMETRY"}, operation="perimeter"
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_missing_exact_value_never_guessed():
    with pytest.raises(FusionCadError) as exc:
        normalize_inspect_result(
            {"operation": "volume", "quantity": "volume", "unit": "mm^3"},
            operation="volume",
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_wrong_unit_fails_closed():
    with pytest.raises(FusionCadError) as exc:
        normalize_inspect_result(
            {"operation": "area", "quantity": "area", "value": 10.0, "unit": "mm"},
            operation="area",
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_missing_bounding_box_points_fails_closed():
    with pytest.raises(FusionCadError) as exc:
        normalize_bounding_box(
            {"operation": "bounding_box", "bounding_box": {"frame": {"space": "world"}}}
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_missing_relation_tolerance_fails_closed():
    with pytest.raises(FusionCadError) as exc:
        normalize_relation(
            {
                "operation": "parallel",
                "relation": "parallel",
                "matches": True,
                "measured": {"angle_deg": 0.0},
                "target_a": "ent_a",
                "target_b": "ent_b",
            },
            operation="parallel",
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_missing_distance_points_fails_closed():
    with pytest.raises(FusionCadError) as exc:
        normalize_distance(
            {"operation": "distance", "value": 10.0, "unit": "mm", "quantity": "distance"},
            operation="distance",
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


# =========================================================================
# Task 7 Step 3: relation results return matches, measured deviation, and
# explicit tolerance for parallel/perpendicular/coplanar/concentric
# =========================================================================


def test_parallel_relation_contract():
    res = normalize_relation(
        {
            "operation": "parallel",
            "relation": "parallel",
            "matches": True,
            "measured": {"angle_deg": 0.0},
            "tolerance": {"value": 0.01, "unit": "deg"},
            "target_a": "ent_fa",
            "target_b": "ent_fb",
        },
        operation="parallel",
    )
    assert res.relation == "parallel"
    assert res.matches is True
    assert res.measured["angle_deg"] == 0.0
    assert res.tolerance.value == 0.01
    assert res.tolerance.unit == "deg"


def test_perpendicular_relation_contract():
    res = normalize_relation(
        {
            "operation": "perpendicular",
            "relation": "perpendicular",
            "matches": False,
            "measured": {"angle_deg": 1.2},
            "tolerance": {"value": 0.01, "unit": "deg"},
            "target_a": "ent_fa",
            "target_b": "ent_fb",
        },
        operation="perpendicular",
    )
    assert res.matches is False
    assert res.measured["angle_deg"] == 1.2


def test_coplanar_relation_reports_angle_and_distance_deviation():
    res = normalize_relation(
        {
            "operation": "coplanar",
            "relation": "coplanar",
            "matches": True,
            "measured": {"angle_deg": 0.0, "distance_mm": 0.0},
            "tolerance": {"value": 0.001, "unit": "mm"},
            "target_a": "ent_fa",
            "target_b": "ent_fb",
        },
        operation="coplanar",
    )
    assert res.matches is True
    assert res.measured["angle_deg"] == 0.0
    assert res.measured["distance_mm"] == 0.0
    assert res.tolerance.unit == "mm"


def test_concentric_relation_contract():
    res = normalize_relation(
        {
            "operation": "concentric",
            "relation": "concentric",
            "matches": True,
            "measured": {"distance_mm": 0.0},
            "tolerance": {"value": 0.001, "unit": "mm"},
            "target_a": "ent_ea",
            "target_b": "ent_eb",
        },
        operation="concentric",
    )
    assert res.matches is True
    assert res.measured["distance_mm"] == 0.0
    assert res.tolerance.value == 0.001


def test_relation_missing_matches_bool_fails_closed():
    with pytest.raises(FusionCadError) as exc:
        normalize_relation(
            {
                "operation": "parallel",
                "relation": "parallel",
                "matches": "yes",
                "measured": {"angle_deg": 0.0},
                "tolerance": {"value": 0.01, "unit": "deg"},
                "target_a": "ent_fa",
                "target_b": "ent_fb",
            },
            operation="parallel",
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


# =========================================================================
# Task 7 Step 4: conservative face-to-face thickness (exact unambiguous
# two-face geometry only; no whole-body min-wall heuristic)
# =========================================================================


def test_face_to_face_thickness_unambiguous():
    res = normalize_thickness(
        {
            "operation": "face_to_face_thickness",
            "quantity": "thickness",
            "value": 5.0,
            "unit": "mm",
            "face_a": "ent_fa",
            "face_b": "ent_fb",
            "unambiguous": True,
        }
    )
    assert res.value == 5.0
    assert res.unit == "mm"
    assert res.face_a == "ent_fa"
    assert res.face_b == "ent_fb"
    assert res.unambiguous is True


def test_face_to_face_thickness_ambiguous_rejected():
    with pytest.raises(FusionCadError) as exc:
        normalize_thickness(
            {
                "operation": "face_to_face_thickness",
                "quantity": "thickness",
                "value": 5.0,
                "unit": "mm",
                "face_a": "ent_fa",
                "face_b": "ent_fb",
                "unambiguous": False,
            }
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_face_to_face_thickness_missing_unambiguous_rejected():
    with pytest.raises(FusionCadError) as exc:
        normalize_thickness(
            {
                "operation": "face_to_face_thickness",
                "quantity": "thickness",
                "value": 5.0,
                "unit": "mm",
                "face_a": "ent_fa",
                "face_b": "ent_fb",
            }
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_measure_normalizer_requires_exact_quantity_and_unit():
    res = normalize_measure(
        {"quantity": "volume", "value": 10.0, "unit": "mm^3"},
        operation="volume",
    )
    assert res.value == 10.0
    assert res.quantity == "volume"
    assert res.unit == "mm^3"
