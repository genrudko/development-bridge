from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import TypeAdapter, ValidationError

from app.api.errors import ErrorCode
from app.desktop_nodes.service import DesktopNodeService
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.inspect import (
    normalize_inspect_result,
    normalize_measure,
    normalize_relation,
)
from app.fusion_cad.requests import FusionInspectRequest
from app.fusion_cad.scripts import FusionCadScriptBundle
from app.fusion_cad.service import FusionCadService


# =========================================================================
# Rendered inspect script scope used by the script-level regression tests.
# =========================================================================


@pytest.fixture(scope="module")
def inspect_scope():
    bundle = FusionCadScriptBundle()
    script = bundle.build("inspect", {"operation": "test_op"})
    scope: dict = {"__name__": "__main__"}
    exec(compile(script, "<rendered-inspect-script>", "exec"), scope)  # noqa: S102
    return scope


class _P:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)


class _Coll:
    def __init__(self, items=None):
        self._items = list(items or [])

    @property
    def count(self):
        return len(self._items)

    def item(self, idx):
        return self._items[idx]


class _Vertex:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.geometry = _P(x, y, z)


class _PlaneGeom:
    def __init__(self, origin=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0)):
        self.objectType = "PlaneSurface"
        self.origin = _P(*origin)
        self.normal = _P(*normal)


def _square_face(token):
    face = _Face(token)
    face.geometry = _PlaneGeom()
    face.vertices = _Coll(
        [_Vertex(0, 0, 0), _Vertex(10, 0, 0), _Vertex(10, 10, 0), _Vertex(0, 10, 0)]
    )
    face.loops = _Coll([object()])
    return face


class _Face:
    def __init__(self, token):
        self.entityToken = token
        self.area = 100.0
        self.centroid = _P(5.0, 5.0, 5.0)
        self.body = None


class _Body:
    def __init__(self, is_solid=True):
        self.name = "WallBody"
        self.isSolid = is_solid
        self.vertices = _Coll([])
        self.faces = _Coll([_square_face(f"wall_face_{i}") for i in range(6)])
        for f in self.faces._items:
            f.body = self


# =========================================================================
# FINAL REVIEW BLOCKER 1: point/vector helpers must fail closed on missing
# or non-finite coordinates instead of silently substituting 0.0.
# =========================================================================


def _pt(**kwargs):
    return types.SimpleNamespace(**kwargs)


@pytest.mark.parametrize(
    "bad",
    [
        _pt(y=1.0, z=1.0),  # missing x
        _pt(x=1.0, z=1.0),  # missing y
        _pt(x=1.0, y=1.0),  # missing z
        _pt(x=float("nan"), y=1.0, z=1.0),
        _pt(x=float("inf"), y=1.0, z=1.0),
        _pt(x=1.0, y=float("-inf"), z=1.0),
        _pt(x=True, y=1.0, z=1.0),  # bool is not a numeric coordinate
        _pt(x="1.0", y=1.0, z=1.0),  # non-numeric
    ],
)
def test_inspect_script_point_dict_fails_closed_on_invalid_coordinates(
    inspect_scope, bad
):
    with pytest.raises(inspect_scope["FusionScriptError"]) as exc:
        inspect_scope["_point_dict"](bad)
    assert exc.value.code == "UNSUPPORTED_GEOMETRY"


def test_inspect_script_point_dict_exact_finite_coordinates(inspect_scope):
    res = inspect_scope["_point_dict"](_P(1.0, 2.0, 3.0))
    assert res["x"] == pytest.approx(10.0)
    assert res["y"] == pytest.approx(20.0)
    assert res["z"] == pytest.approx(30.0)
    assert res["frame"] == {"space": "world", "ref": None}


@pytest.mark.parametrize(
    "bad",
    [
        _pt(y=1.0, z=1.0),
        _pt(x=1.0, z=1.0),
        _pt(x=1.0, y=1.0),
        _pt(x=float("nan"), y=1.0, z=1.0),
        _pt(x=float("inf"), y=1.0, z=1.0),
        _pt(x=1.0, y=float("-inf"), z=1.0),
        _pt(x=False, y=1.0, z=1.0),
        _pt(x=None, y=1.0, z=1.0),
        _pt(x="x", y=1.0, z=1.0),
    ],
)
def test_inspect_script_vec3_fails_closed_on_invalid_coordinates(inspect_scope, bad):
    with pytest.raises(inspect_scope["FusionScriptError"]) as exc:
        inspect_scope["_vec3"](bad)
    assert exc.value.code == "UNSUPPORTED_GEOMETRY"


def test_inspect_script_vec3_exact_finite_coordinates(inspect_scope):
    assert inspect_scope["_vec3"](_P(1.0, 2.0, 3.0)) == [1.0, 2.0, 3.0]


# =========================================================================
# FINAL REVIEW BLOCKER 2: request relation tolerance fields must reject
# negative / NaN / inf values while preserving defaults, with no raw
# validation leakage through the Task 6 boundary.
# =========================================================================

_RELATION_OPS = (
    ("parallel", ("tolerance_deg",)),
    ("perpendicular", ("tolerance_deg",)),
    ("coplanar", ("tolerance_deg", "tolerance_mm")),
    ("concentric", ("tolerance_deg", "tolerance_mm")),
)


@pytest.mark.parametrize(
    ("op", "fields"),
    [
        ("parallel", ("tolerance_deg",)),
        ("perpendicular", ("tolerance_deg",)),
        ("coplanar", ("tolerance_deg", "tolerance_mm")),
        ("concentric", ("tolerance_deg", "tolerance_mm")),
    ],
)
@pytest.mark.parametrize(
    "bad",
    [-1.0, float("-inf"), float("inf"), float("nan")],
)
def test_request_relation_tolerance_rejects_invalid_values(op, fields, bad):
    adapter = TypeAdapter(FusionInspectRequest)
    base = {
        "node_id": "desk-1",
        "operation": op,
        "target_a": "ent_a",
        "target_b": "ent_b",
    }
    for field in fields:
        with pytest.raises(ValidationError):
            adapter.validate_python({**base, field: bad})


@pytest.mark.parametrize(
    ("op", "fields"),
    [
        ("parallel", ("tolerance_deg",)),
        ("perpendicular", ("tolerance_deg",)),
        ("coplanar", ("tolerance_deg", "tolerance_mm")),
        ("concentric", ("tolerance_deg", "tolerance_mm")),
    ],
)
def test_request_relation_tolerance_preserves_defaults_and_accepts_zero(op, fields):
    adapter = TypeAdapter(FusionInspectRequest)
    base = {
        "node_id": "desk-1",
        "operation": op,
        "target_a": "ent_a",
        "target_b": "ent_b",
    }
    req = adapter.validate_python(base)
    assert req.tolerance_deg == 0.01
    if "tolerance_mm" in fields:
        assert req.tolerance_mm == 0.001
    # Zero is a finite non-negative tolerance and must be accepted.
    ok = adapter.validate_python({**base, fields[0]: 0.0})
    assert getattr(ok, fields[0]) == 0.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("op", "field"),
    [
        ("parallel", "tolerance_deg"),
        ("perpendicular", "tolerance_deg"),
        ("coplanar", "tolerance_mm"),
        ("concentric", "tolerance_deg"),
    ],
)
@pytest.mark.parametrize("bad", [-1.0, float("-inf"), float("inf"), float("nan")])
async def test_service_relation_tolerance_rejection_has_no_raw_leak(op, field, bad):
    desktop = MagicMock(spec=DesktopNodeService)
    desktop.call = AsyncMock()
    desktop.submit = AsyncMock()
    cad_service = FusionCadService(desktop)

    with pytest.raises(FusionCadError) as exc:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": op,
                "target_a": "ent_a",
                "target_b": "ent_b",
                field: bad,
            },
            group="inspect",
        )
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT
    # Task 6 error boundary: raw validation values never leak.
    raw = str(bad)
    assert raw not in str(exc.value)
    assert raw not in str(exc.value.details)
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None
    # Validation fails before any script dispatch.
    assert desktop.call.await_count == 0
    assert desktop.submit.await_count == 0


# =========================================================================
# FINAL REVIEW BLOCKER 3: normalization must enforce operation-specific
# public contracts (exact quantity/relation/measured keys/units) and finite
# numeric measurements/tolerances.
# =========================================================================


@pytest.mark.parametrize(
    ("op", "quantity", "value", "unit"),
    [
        ("area", "perimeter", 10.0, "mm"),
        ("perimeter", "area", 10.0, "mm^2"),
        ("volume", "area", 10.0, "mm^2"),
        ("distance", "minimum_distance", 10.0, "mm"),
        ("minimum_distance", "distance", 10.0, "mm"),
        ("angle", "distance", 10.0, "mm"),
    ],
)
def test_normalize_measure_rejects_mismatched_quantity(op, quantity, value, unit):
    with pytest.raises(FusionCadError) as exc:
        normalize_measure(
            {"operation": op, "quantity": quantity, "value": value, "unit": unit},
            operation=op,
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


@pytest.mark.parametrize(
    "op",
    ["area", "perimeter", "volume", "distance", "minimum_distance", "angle"],
)
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_normalize_measure_rejects_non_finite_value(op, bad):
    with pytest.raises(FusionCadError) as exc:
        normalize_measure(
            {
                "operation": op,
                "quantity": "thickness" if op == "face_to_face_thickness" else op,
                "value": bad,
                "unit": "mm" if op in ("perimeter", "distance", "minimum_distance") else ("mm^2" if op == "area" else ("mm^3" if op == "volume" else "deg")),
            },
            operation=op,
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_normalize_thickness_requires_exact_thickness_quantity():
    with pytest.raises(FusionCadError) as exc:
        normalize_inspect_result(
            {
                "operation": "face_to_face_thickness",
                "quantity": "face_to_face_thickness",
                "value": 5.0,
                "unit": "mm",
                "face_a": "ent_fa",
                "face_b": "ent_fb",
                "unambiguous": True,
            },
            operation="face_to_face_thickness",
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_normalize_thickness_rejects_non_finite_value():
    with pytest.raises(FusionCadError) as exc:
        normalize_inspect_result(
            {
                "operation": "face_to_face_thickness",
                "quantity": "thickness",
                "value": float("inf"),
                "unit": "mm",
                "face_a": "ent_fa",
                "face_b": "ent_fb",
                "unambiguous": True,
            },
            operation="face_to_face_thickness",
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_relation_relation_must_equal_requested_operation():
    with pytest.raises(FusionCadError) as exc:
        normalize_relation(
            {
                "operation": "parallel",
                "relation": "perpendicular",
                "matches": True,
                "measured": {"angle_deg": 0.0},
                "tolerance": {"value": 0.01, "unit": "deg"},
                "target_a": "ent_a",
                "target_b": "ent_b",
            },
            operation="parallel",
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


@pytest.mark.parametrize(
    ("op", "measured", "unit"),
    [
        ("parallel", {"angle_deg": 0.0, "extra": 1.0}, "deg"),
        ("coplanar", {"angle_deg": 0.0}, "mm"),
        ("concentric", {"angle_deg": 0.0, "offset_mm": 0.0, "extra": 0.0}, "mm"),
    ],
)
def test_relation_measured_keys_must_match_operation(op, measured, unit):
    with pytest.raises(FusionCadError) as exc:
        normalize_relation(
            {
                "operation": op,
                "relation": op,
                "matches": True,
                "measured": measured,
                "tolerance": {"value": 0.001, "unit": unit},
                "target_a": "ent_a",
                "target_b": "ent_b",
            },
            operation=op,
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


@pytest.mark.parametrize(
    ("op", "unit"),
    [
        ("parallel", "mm"),
        ("perpendicular", "mm"),
        ("coplanar", "deg"),
        ("concentric", "deg"),
    ],
)
def test_relation_tolerance_unit_must_match_operation(op, unit):
    with pytest.raises(FusionCadError) as exc:
        normalize_relation(
            {
                "operation": op,
                "relation": op,
                "matches": True,
                "measured": {"angle_deg": 0.0},
                "tolerance": {"value": 0.001, "unit": unit},
                "target_a": "ent_a",
                "target_b": "ent_b",
            },
            operation=op,
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_relation_measured_value_must_be_finite():
    with pytest.raises(FusionCadError) as exc:
        normalize_relation(
            {
                "operation": "parallel",
                "relation": "parallel",
                "matches": True,
                "measured": {"angle_deg": float("nan")},
                "tolerance": {"value": 0.01, "unit": "deg"},
                "target_a": "ent_a",
                "target_b": "ent_b",
            },
            operation="parallel",
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_relation_tolerance_value_must_be_finite():
    with pytest.raises(FusionCadError) as exc:
        normalize_relation(
            {
                "operation": "parallel",
                "relation": "parallel",
                "matches": True,
                "measured": {"angle_deg": 0.0},
                "tolerance": {"value": float("inf"), "unit": "deg"},
                "target_a": "ent_a",
                "target_b": "ent_b",
            },
            operation="parallel",
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_relation_tolerances_dict_values_must_be_finite():
    with pytest.raises(FusionCadError) as exc:
        normalize_relation(
            {
                "operation": "coplanar",
                "relation": "coplanar",
                "matches": True,
                "measured": {"angle_deg": 0.0, "distance_mm": 0.0},
                "tolerance": {"value": 0.001, "unit": "mm"},
                "tolerances": {"angle_deg": float("nan"), "distance_mm": 0.001},
                "target_a": "ent_a",
                "target_b": "ent_b",
            },
            operation="coplanar",
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


# =========================================================================
# FINAL REVIEW BLOCKER 4: face_to_face_thickness must positively prove
# body.isSolid is True before reporting thickness (six-face surface bodies
# and missing/false isSolid reject UNSUPPORTED_GEOMETRY).
# =========================================================================


def _rect_prism_body(is_solid=True):
    body = _Body(is_solid)
    body.faces._items[0].geometry = _PlaneGeom((0, 0, 0), (0, 0, 1))
    body.faces._items[1].geometry = _PlaneGeom((0, 0, 5), (0, 0, -1))
    return body


def test_thickness_solid_rectangular_wall_control(inspect_scope):
    body = _rect_prism_body(is_solid=True)
    res = inspect_scope["_face_to_face_thickness"](
        body.faces.item(0), body.faces.item(1), "ent_fa", "ent_fb"
    )
    assert res["quantity"] == "thickness"
    assert res["value"] == pytest.approx(50.0)
    assert res["unit"] == "mm"
    assert res["unambiguous"] is True


def test_thickness_false_isSolid_surface_body_rejected(inspect_scope):
    body = _rect_prism_body(is_solid=False)
    with pytest.raises(inspect_scope["FusionScriptError"]) as exc:
        inspect_scope["_face_to_face_thickness"](
            body.faces.item(0), body.faces.item(1), "ent_fa", "ent_fb"
        )
    assert exc.value.code == "UNSUPPORTED_GEOMETRY"


def test_thickness_missing_isSolid_rejected(inspect_scope):
    body = _rect_prism_body(is_solid=True)
    del body.isSolid
    with pytest.raises(inspect_scope["FusionScriptError"]) as exc:
        inspect_scope["_face_to_face_thickness"](
            body.faces.item(0), body.faces.item(1), "ent_fa", "ent_fb"
        )
    assert exc.value.code == "UNSUPPORTED_GEOMETRY"