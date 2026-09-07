from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from app.api.errors import ErrorCode
from app.desktop_nodes.service import DesktopNodeService
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.inspect import (
    normalize_bounding_box,
    normalize_centroid,
    normalize_describe,
    normalize_distance,
    normalize_oriented_bbox,
)
from app.fusion_cad.service import FusionCadService

# =========================================================================
# FINAL REVIEW BLOCKER 1: _inject_inspect_target_hints must resolve opaque
# refs within the effective document context only. Cross-document opaque refs
# fail WRONG_DOCUMENT, unknown/stale active-doc refs fail REF_STALE, and an
# exact active-doc ref still injects its native hint. Foreign native tokens
# are never injected.
# =========================================================================


def _fresh_service() -> FusionCadService:
    desktop = MagicMock(spec=DesktopNodeService)
    return FusionCadService(desktop)


def test_finding1_active_doc_ref_injects_native_hint():
    cad_service = _fresh_service()
    cad_service.revision_tracker.observe("doc_a", "fp-a")
    ref_a = cad_service.ref_registry.issue(
        document_ref="doc_a", kind="body", name="Body1", native_token="tok_a"
    ).ref

    payload = {"node_id": "desk-1", "operation": "describe", "target": ref_a}
    cad_service._inject_inspect_target_hints(payload)

    hint = payload["target"]
    assert isinstance(hint, dict)
    assert hint["ref"] == ref_a
    assert hint["native_token"] == "tok_a"
    assert hint["kind"] == "body"


def test_finding1_cross_document_ref_fails_wrong_document():
    cad_service = _fresh_service()
    cad_service.revision_tracker.observe("doc_a", "fp-a")
    # Ref registered to a DIFFERENT document than the effective (active) one.
    ref_b = cad_service.ref_registry.issue(
        document_ref="doc_b", kind="body", name="Body1", native_token="tok_b"
    ).ref

    payload = {"node_id": "desk-1", "operation": "describe", "target": ref_b}
    with pytest.raises(FusionCadError) as exc:
        cad_service._inject_inspect_target_hints(payload)
    assert exc.value.code == ErrorCode.WRONG_DOCUMENT
    # Foreign native token must not be injected anywhere.
    assert "tok_b" not in str(payload)


def test_finding1_unknown_stale_active_doc_ref_fails_ref_stale():
    cad_service = _fresh_service()
    cad_service.revision_tracker.observe("doc_a", "fp-a")

    payload = {"node_id": "desk-1", "operation": "describe", "target": "ent_unknown_zz"}
    with pytest.raises(FusionCadError) as exc:
        cad_service._inject_inspect_target_hints(payload)
    assert exc.value.code == ErrorCode.REF_STALE


def test_finding1_cross_document_is_checked_even_without_active_doc_but_with_request_doc():
    cad_service = _fresh_service()
    cad_service.revision_tracker.observe("doc_other", "fp-other")
    ref_b = cad_service.ref_registry.issue(
        document_ref="doc_b", kind="body", name="Body1", native_token="tok_b"
    ).ref

    # Effective doc context comes from the request document_ref.
    payload = {
        "node_id": "desk-1",
        "operation": "describe",
        "document_ref": "doc_x",
        "target": ref_b,
    }
    with pytest.raises(FusionCadError) as exc:
        cad_service._inject_inspect_target_hints(payload)
    assert exc.value.code == ErrorCode.WRONG_DOCUMENT


# =========================================================================
# FINAL REVIEW BLOCKER 2: script _resolve_entity must fail closed (REF_STALE)
# when a target carries an authoritative native_token hint and native lookup
# fails/returns zero, instead of falling back to unique kind/name substitution.
# Split remains REF_SPLIT. Contextual kind/name fallback remains available
# only for truly unregistered contextual targets (no native hint).
# =========================================================================


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


class _FakeBody:
    name = "Body1"

    def __init__(self):
        self.faces = _Coll([])
        self.edges = _Coll([])


class _FakeRoot:
    name = "Root"

    def __init__(self):
        self.bRepBodies = _Coll([_FakeBody()])


class _FakeDesign:
    """findEntityByToken always fails (returns None) -> every native lookup is stale."""

    def __init__(self):
        self.rootComponent = _FakeRoot()

    def findEntityByToken(self, token):
        return None


@pytest.fixture(scope="module")
def inspect_scope():
    from app.fusion_cad.scripts import FusionCadScriptBundle

    bundle = FusionCadScriptBundle()
    script = bundle.build("inspect", {"operation": "test_op"})
    scope: dict = {"__name__": "__main__"}
    exec(compile(script, "<rendered-inspect-script>", "exec"), scope)  # noqa: S102
    return scope


def _install_adsk_fake_design(design):
    adsk = types.ModuleType("adsk")
    adsk_core = types.ModuleType("adsk.core")
    adsk_fusion = types.ModuleType("adsk.fusion")

    class _Products:
        def __init__(self, d):
            self._d = d

        def itemByClass(self, cls):
            return self._d if "Design" in cls else None

    class _Doc:
        def __init__(self, d):
            self.products = _Products(d)

    class _App:
        _instance = None

        def __init__(self, doc):
            self._doc = doc

        @property
        def activeDocument(self):
            return self._doc

        @classmethod
        def get(cls):
            return cls._instance

    doc = _Doc(design)
    app = _App(doc)
    _App._instance = app
    adsk_core.Application = _App
    adsk.core = adsk_core
    adsk.fusion = adsk_fusion

    saved = {m: sys.modules.get(m) for m in ("adsk", "adsk.core", "adsk.fusion")}
    sys.modules["adsk"] = adsk
    sys.modules["adsk.core"] = adsk_core
    sys.modules["adsk.fusion"] = adsk_fusion
    return saved


def _restore_adsk(saved):
    for mod, val in saved.items():
        if val is None:
            sys.modules.pop(mod, None)
        else:
            sys.modules[mod] = val


def test_finding2_stale_token_with_unique_same_name_candidate_does_not_substitute(
    inspect_scope,
):
    """Falsifies the fallback: stale registered native token + unique same-name
    candidate must resolve to REF_STALE, never to the kind/name candidate."""
    design = _FakeDesign()
    saved = _install_adsk_fake_design(design)
    try:
        target = {
            "ref": "ent_body_1",
            "kind": "body",
            "name": "Body1",
            "native_token": "stale_token_not_in_runtime",
        }
        with pytest.raises(inspect_scope["FusionScriptError"]) as exc:
            inspect_scope["_resolve_entity"](target)
        assert exc.value.code == "REF_STALE"
    finally:
        _restore_adsk(saved)


def test_finding2_contextual_kind_name_fallback_still_works_without_native_hint(
    inspect_scope,
):
    """Control: a truly unregistered contextual target (no native hint) may still
    use the kind/name fallback that existing P0 semantics require."""
    design = _FakeDesign()
    saved = _install_adsk_fake_design(design)
    try:
        res = inspect_scope["_resolve_entity"](
            {"ref": "ent_body_1", "kind": "body", "name": "Body1"}
        )
        assert res is _FakeBody or res.name == "Body1"
    finally:
        _restore_adsk(saved)


# =========================================================================
# FINAL REVIEW BLOCKER 3: _coerce_frame/_coerce_point must not default
# missing frames to world, and normalize_describe must reject bare numeric
# measures (no implicit quantity/unit/default mm). Missing frames and bare
# numeric measures fail closed with UNSUPPORTED_GEOMETRY.
# =========================================================================


def test_finding3_centroid_missing_frame_fails_closed():
    with pytest.raises(FusionCadError) as exc:
        normalize_centroid({"point": {"x": 1.0, "y": 2.0, "z": 3.0}})
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_finding3_bounding_box_missing_frame_fails_closed():
    with pytest.raises(FusionCadError) as exc:
        normalize_bounding_box(
            {"bounding_box": {"min": [0, 0, 0], "max": [1, 1, 1]}}
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_finding3_oriented_bbox_missing_frame_fails_closed():
    with pytest.raises(FusionCadError) as exc:
        normalize_oriented_bbox(
            {
                "oriented_bbox": {
                    "center": {
                        "x": 0.0,
                        "y": 0.0,
                        "z": 0.0,
                        "frame": {"space": "world"},
                    },
                    "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                    "extents": [1, 1, 1],
                }
            }
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_finding3_distance_point_missing_frame_fails_closed():
    with pytest.raises(FusionCadError) as exc:
        normalize_distance(
            {
                "operation": "distance",
                "quantity": "distance",
                "value": 10.0,
                "unit": "mm",
                "from": {"x": 0, "y": 0, "z": 0, "frame": {"space": "world"}},
                "to": {"x": 10, "y": 0, "z": 0},
            },
            operation="distance",
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_finding3_describe_missing_top_level_frame_fails_closed():
    with pytest.raises(FusionCadError) as exc:
        normalize_describe(
            {
                "operation": "describe",
                "target": {"ref": "ent_b1", "kind": "body"},
                "measures": {
                    "volume": {"quantity": "volume", "value": 1000.0, "unit": "mm^3"}
                },
            }
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_finding3_describe_rejects_bare_numeric_measure():
    with pytest.raises(FusionCadError) as exc:
        normalize_describe(
            {
                "operation": "describe",
                "target": {"ref": "ent_b1", "kind": "body"},
                "frame": {"space": "world"},
                "measures": {"volume": 1000.0},
            }
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_finding3_describe_measure_missing_quantity_unit_or_value_fails_closed():
    with pytest.raises(FusionCadError) as exc:
        normalize_describe(
            {
                "operation": "describe",
                "target": {"ref": "ent_b1", "kind": "body"},
                "frame": {"space": "world"},
                "measures": {"area": {"value": 600.0}},
            }
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


def test_finding3_preserves_valid_explicit_world_frame_results():
    """Valid explicit world-frame geometry from the Fusion script is preserved."""
    res_cent = normalize_centroid(
        {
            "point": {
                "x": 5.0,
                "y": 6.0,
                "z": 7.0,
                "frame": {"space": "world"},
            }
        }
    )
    assert res_cent.point.frame.space == "world"

    res_bb = normalize_bounding_box(
        {
            "bounding_box": {
                "min": [0, 0, 0],
                "max": [10, 10, 10],
                "frame": {"space": "world"},
            }
        }
    )
    assert res_bb.bounding_box.frame.space == "world"

    res_desc = normalize_describe(
        {
            "operation": "describe",
            "target": {"ref": "ent_b1", "kind": "body", "name": "Body1"},
            "frame": {"space": "world"},
            "measures": {
                "volume": {"quantity": "volume", "value": 1000.0, "unit": "mm^3"},
                "bounding_box": {
                    "min": [0, 0, 0],
                    "max": [10, 10, 10],
                    "frame": {"space": "world"},
                },
            },
        }
    )
    assert res_desc.frame.space == "world"
    assert res_desc.measures["volume"]["unit"] == "mm^3"

# =========================================================================
# FINAL REVIEW OBB REPAIR (latest Codex re-review):
#  - Finding 4: _face_oriented_bbox must fail closed (UNSUPPORTED_GEOMETRY)
#    for curved/unknown boundary edges; vertex projection is exact only for
#    positively verified straight-edged polygonal faces (extrema of a linear
#    function over a polygon occur at vertices).
#  - Finding 5: _body_oriented_bbox must NEVER relabel the axis-aligned
#    body.boundingBox as an oriented_bbox; without an exact Fusion OBB / measure
#    API it must fail closed with UNSUPPORTED_GEOMETRY.
# =========================================================================


class _ObbPoint:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)


class _ObbVertex:
    def __init__(self, x, y, z):
        self.geometry = _ObbPoint(x, y, z)


class _ObbEdgeGeom:
    def __init__(self, curve_type):
        self.objectType = curve_type
        self.curveType = curve_type


class _ObbEdge:
    def __init__(self, curve_type="Line3D", geometry=None):
        self.geometry = geometry if geometry is not None else _ObbEdgeGeom(curve_type)


class _ObbLoop:
    def __init__(self, edges):
        self.edges = _Coll(edges)


class _ObbFaceGeom:
    def __init__(self, origin, normal, reference_vector=None):
        self.objectType = "PlaneSurface"
        self.origin = origin
        self.normal = normal
        if reference_vector is not None:
            self.referenceVector = reference_vector


class _ObbFace:
    def __init__(self, geom, loops, vertices):
        self.geometry = geom
        self.loops = _Coll(loops)
        self.vertices = _Coll(vertices)


def _square_obb_face(edge_types):
    """Planar face on z=0 with four boundary edge types and square corners."""
    origin = _ObbPoint(0.0, 0.0, 0.0)
    normal = _ObbPoint(0.0, 0.0, 1.0)
    vertices = [
        _ObbVertex(0.0, 0.0, 0.0),
        _ObbVertex(10.0, 0.0, 0.0),
        _ObbVertex(10.0, 10.0, 0.0),
        _ObbVertex(0.0, 10.0, 0.0),
    ]
    loop = _ObbLoop([_ObbEdge(t) for t in edge_types])
    return _ObbFace(_ObbFaceGeom(origin, normal), [loop], vertices)


def test_finding4_curved_edge_face_oriented_bbox_fails_closed(inspect_scope):
    """Falsifies the under-sized guess: a planar face with a curved boundary edge
    must NOT return a vertex-only projected oriented_bbox (extrema can lie
    between vertices on the curve); it must fail closed with UNSUPPORTED_GEOMETRY."""
    face = _square_obb_face(["Arc3D", "Line3D", "Line3D", "Line3D"])
    with pytest.raises(inspect_scope["FusionScriptError"]) as exc:
        inspect_scope["_face_oriented_bbox"](face)
    assert exc.value.code == "UNSUPPORTED_GEOMETRY"


def test_finding4_unknown_curve_face_oriented_bbox_fails_closed(inspect_scope):
    """An edge whose curve type cannot be proven straight must also fail closed."""
    face = _square_obb_face(["Line3D", "Line3D", "Line3D", "Line3D"])
    face.loops.item(0).edges.item(2).geometry = _ObbEdgeGeom("Spline3D")
    with pytest.raises(inspect_scope["FusionScriptError"]) as exc:
        inspect_scope["_face_oriented_bbox"](face)
    assert exc.value.code == "UNSUPPORTED_GEOMETRY"


def test_finding4_missing_edge_geometry_face_oriented_bbox_fails_closed(inspect_scope):
    """An edge without readable geometry cannot be proven straight; fail closed."""
    face = _square_obb_face(["Line3D", "Line3D", "Line3D", "Line3D"])
    face.loops.item(0).edges.item(1).geometry = None
    with pytest.raises(inspect_scope["FusionScriptError"]) as exc:
        inspect_scope["_face_oriented_bbox"](face)
    assert exc.value.code == "UNSUPPORTED_GEOMETRY"


def test_finding4_straight_edge_polygonal_face_oriented_bbox_exact(inspect_scope):
    """Control: a positively verified straight-edged polygonal face returns an
    exact vertex-projected oriented_bbox (extrema of a polygon occur at vertices)."""
    face = _square_obb_face(["Line3D", "Line3D", "Line3D", "Line3D"])
    res = inspect_scope["_face_oriented_bbox"](face)
    assert set(res.keys()) == {"center", "axes", "extents", "frame"}
    assert len(res["axes"]) == 3
    assert all(len(a) == 3 for a in res["axes"])
    # 10 cm square -> 100 mm, half-extents 50 mm; planar normal extent 0 mm.
    assert res["extents"] == [50.0, 50.0, 0.0]
    assert res["frame"] == {"space": "world", "ref": None}


def test_finding5_body_oriented_bbox_fails_closed_never_relabels_aabb(inspect_scope):
    """Falsifies the relabel bug: _body_oriented_bbox must NEVER return the
    axis-aligned body.boundingBox as an oriented bounding box; without an exact
    Fusion OBB / measure API it fails closed with UNSUPPORTED_GEOMETRY."""
    class _BB:
        def __init__(self, min_pt, max_pt):
            self.minPoint = min_pt
            self.maxPoint = max_pt

    class _Body:
        pass

    body = _Body()
    body.boundingBox = _BB(
        _ObbPoint(2.0, 3.0, 4.0), _ObbPoint(12.0, 13.0, 14.0)
    )
    with pytest.raises(inspect_scope["FusionScriptError"]) as exc:
        inspect_scope["_body_oriented_bbox"](body)
    assert exc.value.code == "UNSUPPORTED_GEOMETRY"
