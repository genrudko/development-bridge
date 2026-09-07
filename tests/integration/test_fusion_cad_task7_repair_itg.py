from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.errors import ErrorCode
from app.desktop_nodes.service import DesktopNodeService
from app.fusion_cad.capabilities import CapabilityMatrix
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.models import CapabilityRecord
from app.fusion_cad.service import FusionCadService

# =========================================================================
# Minimal but representative Adsk Fusion fake for Task 7 bounded-repair tests.
#
# Mirror real property shapes:
#   * circular edges    -> Circle3D-like geometry with center + normal
#   * cylindrical faces -> Cylinder-like geometry with axis origin + axis
#   * planar faces      -> PlaneSurface-like geometry with origin + normal
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


class _Vertex:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.geometry = _P(x, y, z)


class _PlaneGeom:
    def __init__(self, origin=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0)):
        self.objectType = "PlaneSurface"
        self.origin = origin if isinstance(origin, _P) else _P(*origin)
        self.normal = normal if isinstance(normal, _P) else _P(*normal)


class _CylinderGeom:
    def __init__(self, origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0), radius=5.0):
        self.objectType = "Cylinder"
        self.origin = origin if isinstance(origin, _P) else _P(*origin)
        self.axis = axis if isinstance(axis, _P) else _P(*axis)
        self.radius = radius


class _CircleGeom:
    def __init__(self, center=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0), radius=5.0):
        self.objectType = "Circle3D"
        self.center = center if isinstance(center, _P) else _P(*center)
        self.normal = normal if isinstance(normal, _P) else _P(*normal)
        self.radius = radius


class _Face:
    def __init__(self, idx=0, geometry=None, vertices=None, loops=None):
        self.entityToken = f"face_token_{idx}"
        self.area = 10.0
        self.centroid = _P(5.0, 5.0, 5.0)
        self.body = None
        self.geometry = geometry or _PlaneGeom()
        self.vertices = (
            vertices
            if vertices is not None
            else _Coll([_Vertex(0, 0, 0), _Vertex(10, 0, 0), _Vertex(10, 10, 0), _Vertex(0, 10, 0)])
        )
        self.loops = loops if loops is not None else _Coll([object()])


class _Edge:
    def __init__(self, idx=0, geometry=None):
        self.entityToken = f"edge_token_{idx}"
        self.length = 10.0
        self.geometry = geometry
        self.startVertex = _Vertex(0.0, 0.0, 0.0)
        self.endVertex = _Vertex(10.0, 0.0, 0.0)


class _Body:
    def __init__(self):
        self.name = "Body1"
        self.entityToken = "body_token_1"
        self.isSolid = True
        self.area = 50.0
        self._faces = [_Face(0), _Face(1), _Face(2), _Face(3), _Face(4), _Face(5)]
        self._edges = [_Edge(i) for i in range(4)]
        for f in self._faces:
            f.body = self
        self.faces = _Coll(self._faces)
        self.edges = _Coll(self._edges)
        self.vertices = _Coll([_Vertex(0, 0, 0), _Vertex(10, 0, 0), _Vertex(10, 10, 0), _Vertex(0, 10, 0)])


class _Component:
    def __init__(self, body):
        self.name = "Root"
        self.bRepBodies = _Coll([body])


class _Design:
    def __init__(self, body):
        self.rootComponent = _Component(body)
        self._token_map = {body.entityToken: body}
        for f in body._faces:
            self._token_map[f.entityToken] = f
        for e in body._edges:
            self._token_map[e.entityToken] = e

    def findEntityByToken(self, token):
        return self._token_map.get(token)


class _Products:
    def __init__(self, design):
        self._design = design

    def itemByClass(self, cls_name):
        if "Design" in cls_name:
            return self._design
        return None


class _Doc:
    def __init__(self, design):
        self.dataId = "doc_1"
        self._design = design
        self.products = _Products(design)


class _Application:
    _instance = None

    def __init__(self, design):
        self._doc = _Doc(design)

    @property
    def activeDocument(self):
        return self._doc

    @classmethod
    def get(cls):
        return cls._instance


class InspectFusionFake:
    """Installs a representative adsk runtime into sys.modules for the session."""

    def __init__(self):
        self.body = _Body()

    def __enter__(self):
        self._saved = {
            "adsk": sys.modules.get("adsk"),
            "adsk.core": sys.modules.get("adsk.core"),
            "adsk.fusion": sys.modules.get("adsk.fusion"),
        }
        adsk = types.ModuleType("adsk")
        core = types.ModuleType("adsk.core")
        fusion = types.ModuleType("adsk.fusion")
        design = _Design(self.body)
        app = _Application(design)
        _Application._instance = app
        core.Application = _Application
        adsk.core = core
        adsk.fusion = fusion
        sys.modules["adsk"] = adsk
        sys.modules["adsk.core"] = core
        sys.modules["adsk.fusion"] = fusion
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for mod, val in self._saved.items():
            if val is None:
                sys.modules.pop(mod, None)
            else:
                sys.modules[mod] = val


def _inspect_matrix():
    return CapabilityMatrix.from_records(
        [CapabilityRecord(name="inspect.measure", state="supported")]
    )


def _register_refs(cad_service):
    return {
        "face_a": cad_service.ref_registry.issue(
            document_ref="doc_1", kind="face", name="f0", native_token="face_token_0"
        ).ref,
        "face_b": cad_service.ref_registry.issue(
            document_ref="doc_1", kind="face", name="f1", native_token="face_token_1"
        ).ref,
        "face_c": cad_service.ref_registry.issue(
            document_ref="doc_1", kind="face", name="f2", native_token="face_token_2"
        ).ref,
        "edge_a": cad_service.ref_registry.issue(
            document_ref="doc_1", kind="edge", name="e0", native_token="edge_token_0"
        ).ref,
        "edge_b": cad_service.ref_registry.issue(
            document_ref="doc_1", kind="edge", name="e1", native_token="edge_token_1"
        ).ref,
    }


def _make_service(mock_desktop_service):
    cad_service = FusionCadService(mock_desktop_service)
    cad_service.set_node_capabilities("desk-1", _inspect_matrix())

    async def run_rendered_inspect(node_id, tool_name, arguments, journal=None):
        script = arguments["script"]
        scope = {"__name__": "__main__"}
        exec(compile(script, "<rendered-inspect-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    mock_desktop_service.call = run_rendered_inspect  # type: ignore[assignment]
    mock_desktop_service.submit = run_rendered_inspect  # type: ignore[assignment]
    return cad_service


@pytest.fixture
def mock_desktop_service() -> MagicMock:
    service = MagicMock(spec=DesktopNodeService)
    service.call = AsyncMock()
    service.submit = AsyncMock()
    service.store_external_result = MagicMock()
    return service


# =========================================================================
# Finding 2: coplanar reports explicit angular + linear tolerances
# =========================================================================


@pytest.mark.asyncio
async def test_fusion_inspect_coplanar_reports_explicit_angular_and_linear_tolerances(
    mock_desktop_service,
):
    """Proves coplanar uses caller-supplied angular + linear tolerances and reports both."""
    with InspectFusionFake() as fake:
        cad_service = _make_service(mock_desktop_service)
        refs = _register_refs(cad_service)

        fake.body._faces[0].geometry = _PlaneGeom((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
        fake.body._faces[1].geometry = _PlaneGeom((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))

        res = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "coplanar",
                "target_a": refs["face_a"],
                "target_b": refs["face_b"],
                "tolerance_deg": 0.02,
                "tolerance_mm": 0.005,
            },
            group="inspect",
        )
        assert res.status == "succeeded"
        data = res.data
        assert data["relation"] == "coplanar"
        assert data["matches"] is True
        assert data["measured"]["angle_deg"] == 0.0
        assert data["measured"]["distance_mm"] == 0.0
        assert data["tolerances"] == {"angle_deg": 0.02, "distance_mm": 0.005}
        assert data["tolerance"] == {"value": 0.005, "unit": "mm"}


# =========================================================================
# Finding 3: concentric supports representative circular-edge / cylindrical-face
# =========================================================================


@pytest.mark.asyncio
async def test_fusion_inspect_concentric_circular_edges_center_normal(
    mock_desktop_service,
):
    """Circular edges (Circle3D center+normal) resolve concentricity exactly."""
    with InspectFusionFake() as fake:
        cad_service = _make_service(mock_desktop_service)
        refs = _register_refs(cad_service)

        fake.body._edges[0].geometry = _CircleGeom(center=(5, 5, 0), normal=(0, 0, 1), radius=5)
        fake.body._edges[1].geometry = _CircleGeom(center=(5, 5, 0), normal=(0, 0, 1), radius=7)

        res = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "concentric",
                "target_a": refs["edge_a"],
                "target_b": refs["edge_b"],
                "tolerance_deg": 0.01,
                "tolerance_mm": 0.001,
            },
            group="inspect",
        )
        assert res.data["relation"] == "concentric"
        assert res.data["matches"] is True
        assert res.data["measured"]["angle_deg"] == 0.0
        assert res.data["measured"]["offset_mm"] == 0.0
        assert res.data["tolerances"] == {"angle_deg": 0.01, "offset_mm": 0.001}


@pytest.mark.asyncio
async def test_fusion_inspect_concentric_cylindrical_faces_origin_axis(
    mock_desktop_service,
):
    """Cylindrical faces (Cylinder origin+axis) resolve offset exactly."""
    with InspectFusionFake() as fake:
        cad_service = _make_service(mock_desktop_service)
        refs = _register_refs(cad_service)

        fake.body._faces[0].geometry = _CylinderGeom(origin=(5, 5, 0), axis=(0, 0, 1), radius=5)
        fake.body._faces[1].geometry = _CylinderGeom(origin=(5, 6, 0), axis=(0, 0, 1), radius=7)

        res = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "concentric",
                "target_a": refs["face_a"],
                "target_b": refs["face_b"],
                "tolerance_deg": 0.01,
                "tolerance_mm": 0.001,
            },
            group="inspect",
        )
        assert res.data["relation"] == "concentric"
        assert res.data["matches"] is False
        assert res.data["measured"]["angle_deg"] == 0.0
        assert res.data["measured"]["offset_mm"] == pytest.approx(10.0)
        assert res.data["tolerances"]["offset_mm"] == 0.001


@pytest.mark.asyncio
async def test_fusion_inspect_concentric_circular_edge_and_cylindrical_face(
    mock_desktop_service,
):
    """A circular edge can be compared to a cylindrical face (Fusion-real pairing)."""
    with InspectFusionFake() as fake:
        cad_service = _make_service(mock_desktop_service)
        refs = _register_refs(cad_service)

        fake.body._edges[0].geometry = _CircleGeom(center=(5, 5, 0), normal=(0, 0, 1), radius=5)
        fake.body._faces[1].geometry = _CylinderGeom(origin=(5, 5, 0), axis=(0, 0, 1), radius=7)

        res = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "concentric",
                "target_a": refs["edge_a"],
                "target_b": refs["face_b"],
                "tolerance_deg": 0.01,
                "tolerance_mm": 1.0,
            },
            group="inspect",
        )
        assert res.data["relation"] == "concentric"
        assert res.data["matches"] is True
        assert res.data["measured"]["angle_deg"] == 0.0
        assert res.data["measured"]["offset_mm"] == 0.0


@pytest.mark.asyncio
async def test_fusion_inspect_concentric_unsupported_plane_fails_closed(
    mock_desktop_service,
):
    """Concentric fails closed for non-circular geometry (no guessing)."""
    with InspectFusionFake() as fake:
        cad_service = _make_service(mock_desktop_service)
        refs = _register_refs(cad_service)

        fake.body._faces[0].geometry = _PlaneGeom((0, 0, 0), (0, 0, 1))
        fake.body._faces[1].geometry = _PlaneGeom((0, 0, 0), (0, 0, 1))

        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "concentric",
                    "target_a": refs["face_a"],
                    "target_b": refs["face_b"],
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


# =========================================================================
# Finding 1: conservative face-to-face thickness proof
# =========================================================================


@pytest.mark.asyncio
async def test_fusion_inspect_thickness_exact_rectangular_wall_succeeds(
    mock_desktop_service,
):
    """Control: an exact coincident rectangular opposing pair still returns thickness."""
    with InspectFusionFake() as fake:
        cad_service = _make_service(mock_desktop_service)
        refs = _register_refs(cad_service)

        fake.body._faces[0].geometry = _PlaneGeom((0, 0, 0), (0, 0, 1))
        fake.body._faces[1].geometry = _PlaneGeom((0, 0, 5), (0, 0, -1))

        res = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "face_to_face_thickness",
                "face_a": refs["face_a"],
                "face_b": refs["face_b"],
            },
            group="inspect",
        )
        assert res.data["quantity"] == "thickness"
        assert res.data["value"] == pytest.approx(50.0)
        assert res.data["unit"] == "mm"
        assert res.data["unambiguous"] is True


@pytest.mark.asyncio
async def test_fusion_inspect_thickness_concave_l_shape_rejected(mock_desktop_service):
    """Falsifies old bounding-rectangle overlap: an L-shaped concave face is rejected."""
    with InspectFusionFake() as fake:
        cad_service = _make_service(mock_desktop_service)
        refs = _register_refs(cad_service)

        fake.body._faces[0].geometry = _PlaneGeom((0, 0, 0), (0, 0, 1))
        fake.body._faces[1].geometry = _PlaneGeom((0, 0, 5), (0, 0, -1))
        # L-shape shares the exact bounding rectangle of face_a, so the old
        # vertex bounding-rectangle overlap check would falsely accept it.
        fake.body._faces[1].vertices = _Coll(
            [
                _Vertex(0, 0, 5),
                _Vertex(10, 0, 5),
                _Vertex(10, 5, 5),
                _Vertex(5, 5, 5),
                _Vertex(5, 10, 5),
                _Vertex(0, 10, 5),
            ]
        )

        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "face_to_face_thickness",
                    "face_a": refs["face_a"],
                    "face_b": refs["face_b"],
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


@pytest.mark.asyncio
async def test_fusion_inspect_thickness_holed_face_rejected(mock_desktop_service):
    """Falsifies the old logic: a face with an inner loop (hole) is ambiguous."""
    with InspectFusionFake() as fake:
        cad_service = _make_service(mock_desktop_service)
        refs = _register_refs(cad_service)

        fake.body._faces[0].geometry = _PlaneGeom((0, 0, 0), (0, 0, 1))
        fake.body._faces[1].geometry = _PlaneGeom((0, 0, 5), (0, 0, -1))
        # Outer loop keeps the bounding rectangle; an inner loop adds a hole.
        fake.body._faces[1].loops = _Coll([object(), object()])

        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "face_to_face_thickness",
                    "face_a": refs["face_a"],
                    "face_b": refs["face_b"],
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


@pytest.mark.asyncio
async def test_fusion_inspect_thickness_cavity_internal_wall_rejected(
    mock_desktop_service,
):
    """Falsifies: same-body coincident rectangles with an internal parallel partition face."""
    with InspectFusionFake() as fake:
        cad_service = _make_service(mock_desktop_service)
        refs = _register_refs(cad_service)

        fake.body._faces[0].geometry = _PlaneGeom((0, 0, 0), (0, 0, 1))
        fake.body._faces[1].geometry = _PlaneGeom((0, 0, 10), (0, 0, -1))
        # Internal parallel face strictly between the pair -> hollow/cavity partition.
        fake.body._faces[2].geometry = _PlaneGeom((0, 0, 5), (0, 0, 1))

        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "face_to_face_thickness",
                    "face_a": refs["face_a"],
                    "face_b": refs["face_b"],
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


@pytest.mark.asyncio
async def test_fusion_inspect_thickness_cavity_internal_wall_rejected_reversed(
    mock_desktop_service,
):
    """Falsifies order-dependent between-planes bounds: the same cavity/partition
    case with the wall faces reversed (outward-facing normals) must still be
    rejected, not silently accepted as an unambiguous wall pair."""
    with InspectFusionFake() as fake:
        cad_service = _make_service(mock_desktop_service)
        refs = _register_refs(cad_service)

        # Same coincident rectangular opposing pair as the cavity test, but with
        # face_a's signed plane position NOT below face_b's along face_a's normal
        # (the order the old code silently assumed). face_a normal points outward
        # away from face_b, so dot(na, oa) > dot(na, ob).
        fake.body._faces[0].geometry = _PlaneGeom((0, 0, 0), (0, 0, -1))
        fake.body._faces[1].geometry = _PlaneGeom((0, 0, 10), (0, 0, 1))
        # Internal parallel face strictly between the pair -> hollow/cavity partition.
        fake.body._faces[2].geometry = _PlaneGeom((0, 0, 5), (0, 0, 1))

        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "face_to_face_thickness",
                    "face_a": refs["face_a"],
                    "face_b": refs["face_b"],
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


@pytest.mark.asyncio
async def test_fusion_inspect_thickness_partial_overlap_rejected(mock_desktop_service):
    """Falsifies: partial-overlap rectangles are not coincident -> ambiguous/disconnected."""
    with InspectFusionFake() as fake:
        cad_service = _make_service(mock_desktop_service)
        refs = _register_refs(cad_service)

        fake.body._faces[0].geometry = _PlaneGeom((0, 0, 0), (0, 0, 1))
        fake.body._faces[1].geometry = _PlaneGeom((0, 0, 5), (0, 0, -1))
        # Rectangle merely overlaps face_A's bounding box, but does not coincide.
        fake.body._faces[1].vertices = _Coll(
            [
                _Vertex(5, 5, 5),
                _Vertex(15, 5, 5),
                _Vertex(15, 15, 5),
                _Vertex(5, 15, 5),
            ]
        )

        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "face_to_face_thickness",
                    "face_a": refs["face_a"],
                    "face_b": refs["face_b"],
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


# =========================================================================
# Task 7 P0 findings: line-angle/relation and circular-concentric proofs
#
# Falsify the two remaining P0 findings:
#   * angle/parallel/perpendicular on edge/sketch_curve inputs must proceed
#     ONLY for positively proven straight-line (Line3D) curves; Arc3D/Spline
#     geometry must fail closed UNSUPPORTED_GEOMETRY instead of a chord-based
#     plausible angle/relation result.
#   * concentricity on edge/sketch_curve inputs must proceed ONLY for
#     positively proven circle/arc (Circle3D/Arc3D) geometry; ellipse-like
#     geometry exposing center+normal must fail closed UNSUPPORTED_GEOMETRY.
# =========================================================================


class _LineGeom:
    def __init__(self, sp=(0.0, 0.0, 0.0), ep=(10.0, 0.0, 0.0)):
        self.curveType = "Line3D"
        self.objectType = "Line3D"
        self.startPoint = sp if isinstance(sp, _P) else _P(*sp)
        self.endPoint = ep if isinstance(ep, _P) else _P(*ep)


class _ArcGeom:
    def __init__(
        self,
        sp=(0.0, 0.0, 0.0),
        ep=(10.0, 0.0, 0.0),
        center=(5.0, 0.0, 0.0),
        normal=(0.0, 0.0, 1.0),
        radius=5.0,
    ):
        self.curveType = "Arc3D"
        self.objectType = "Arc3D"
        self.startPoint = sp if isinstance(sp, _P) else _P(*sp)
        self.endPoint = ep if isinstance(ep, _P) else _P(*ep)
        self.center = center if isinstance(center, _P) else _P(*center)
        self.normal = normal if isinstance(normal, _P) else _P(*normal)
        self.radius = radius


class _SplineGeom:
    def __init__(self, sp=(0.0, 0.0, 0.0), ep=(10.0, 0.0, 0.0)):
        self.curveType = "Spline3D"
        self.objectType = "Spline3D"
        self.startPoint = sp if isinstance(sp, _P) else _P(*sp)
        self.endPoint = ep if isinstance(ep, _P) else _P(*ep)


class _EllipseGeom:
    def __init__(
        self,
        center=(5.0, 5.0, 0.0),
        normal=(0.0, 0.0, 1.0),
        major=5.0,
        minor=3.0,
    ):
        self.curveType = "Ellipse3D"
        self.objectType = "Ellipse3D"
        self.center = center if isinstance(center, _P) else _P(*center)
        self.normal = normal if isinstance(normal, _P) else _P(*normal)
        self.majorRadius = major
        self.minorRadius = minor


class _EllipticalArcGeom:
    def __init__(
        self,
        center=(5.0, 5.0, 0.0),
        normal=(0.0, 0.0, 1.0),
        major=5.0,
        minor=3.0,
    ):
        self.curveType = "EllipticalArc3D"
        self.objectType = "EllipticalArc3D"
        self.center = center if isinstance(center, _P) else _P(*center)
        self.normal = normal if isinstance(normal, _P) else _P(*normal)
        self.majorRadius = major
        self.minorRadius = minor


class _UnknownGeom:
    """Unverifiable curve type that still exposes start/end points and center+normal."""

    def __init__(self, sp=(0.0, 0.0, 0.0), ep=(10.0, 0.0, 0.0)):
        self.curveType = "FooCurve3D"
        self.objectType = "FooCurve3D"
        self.startPoint = sp if isinstance(sp, _P) else _P(*sp)
        self.endPoint = ep if isinstance(ep, _P) else _P(*ep)
        self.center = _P(5.0, 0.0, 0.0)
        self.normal = _P(0.0, 0.0, 1.0)


@pytest.mark.asyncio
async def test_fusion_inspect_angle_curved_edge_rejected(mock_desktop_service):
    """Falsify P0 finding: angle on curved Arc3D/Spline edges must fail closed
    UNSUPPORTED_GEOMETRY instead of reporting a plausible chord-based angle."""
    with InspectFusionFake() as fake:
        cad_service = _make_service(mock_desktop_service)
        refs = _register_refs(cad_service)

        fake.body._edges[0].geometry = _LineGeom((0, 0, 0), (10, 0, 0))
        for curved in (
            _ArcGeom((0, 0, 0), (10, 0, 0)),
            _SplineGeom((0, 0, 0), (10, 0, 0)),
        ):
            fake.body._edges[1].geometry = curved
            with pytest.raises(FusionCadError) as exc:
                await cad_service.execute(
                    {
                        "node_id": "desk-1",
                        "operation": "angle",
                        "target_a": refs["edge_a"],
                        "target_b": refs["edge_b"],
                    },
                    group="inspect",
                )
            assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["parallel", "perpendicular"])
async def test_fusion_inspect_curved_edge_relation_rejected(
    mock_desktop_service, operation
):
    """Falsify P0 finding: parallel/perpendicular on a curved edge must fail closed
    UNSUPPORTED_GEOMETRY instead of a chord-based relation result."""
    with InspectFusionFake() as fake:
        cad_service = _make_service(mock_desktop_service)
        refs = _register_refs(cad_service)

        fake.body._edges[0].geometry = _LineGeom((0, 0, 0), (10, 0, 0))
        fake.body._edges[1].geometry = _ArcGeom((0, 0, 0), (10, 0, 0))
        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": operation,
                    "target_a": refs["edge_a"],
                    "target_b": refs["edge_b"],
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


@pytest.mark.asyncio
async def test_fusion_inspect_concentric_ellipse_like_edge_center_normal_rejected(
    mock_desktop_service,
):
    """Falsify P0 finding: ellipse-like geometry exposing center+normal must not be
    misclassified as circular for concentricity."""
    with InspectFusionFake() as fake:
        cad_service = _make_service(mock_desktop_service)
        refs = _register_refs(cad_service)

        fake.body._edges[0].geometry = _EllipseGeom(center=(5, 5, 0), normal=(0, 0, 1))
        fake.body._edges[1].geometry = _EllipseGeom(center=(5, 5, 0), normal=(0, 0, 1))
        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "concentric",
                    "target_a": refs["edge_a"],
                    "target_b": refs["edge_b"],
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


@pytest.mark.asyncio
async def test_fusion_inspect_straight_line_angle_and_relation_controls(
    mock_desktop_service,
):
    """Control: positively proven straight Line3D edges still resolve angle,
    parallel, and perpendicular exactly."""
    with InspectFusionFake() as fake:
        cad_service = _make_service(mock_desktop_service)
        refs = _register_refs(cad_service)

        fake.body._edges[0].geometry = _LineGeom((0, 0, 0), (10, 0, 0))
        fake.body._edges[1].geometry = _LineGeom((0, 0, 0), (0, 10, 0))

        res_angle = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "angle",
                "target_a": refs["edge_a"],
                "target_b": refs["edge_b"],
            },
            group="inspect",
        )
        assert res_angle.data["unit"] == "deg"
        assert res_angle.data["value"] == pytest.approx(90.0)

        res_par = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "parallel",
                "target_a": refs["edge_a"],
                "target_b": refs["edge_b"],
                "tolerance_deg": 0.01,
            },
            group="inspect",
        )
        assert res_par.data["relation"] == "parallel"
        assert res_par.data["matches"] is False
        assert res_par.data["measured"]["angle_deg"] == pytest.approx(90.0)

        res_perp = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "perpendicular",
                "target_a": refs["edge_a"],
                "target_b": refs["edge_b"],
                "tolerance_deg": 0.01,
            },
            group="inspect",
        )
        assert res_perp.data["relation"] == "perpendicular"
        assert res_perp.data["matches"] is True

        fake.body._edges[1].geometry = _LineGeom((0, 0, 0), (10, 0, 0))
        res_par2 = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "parallel",
                "target_a": refs["edge_a"],
                "target_b": refs["edge_b"],
                "tolerance_deg": 0.01,
            },
            group="inspect",
        )
        assert res_par2.data["matches"] is True


@pytest.mark.asyncio
async def test_fusion_inspect_circle_and_arc_concentric_controls(
    mock_desktop_service,
):
    """Control: positively proven Circle3D and Arc3D edges remain concentric-supported."""
    with InspectFusionFake() as fake:
        cad_service = _make_service(mock_desktop_service)
        refs = _register_refs(cad_service)

        fake.body._edges[0].geometry = _CircleGeom(
            center=(5, 5, 0), normal=(0, 0, 1), radius=5
        )
        fake.body._edges[1].geometry = _ArcGeom(
            (0, 0, 0), (10, 0, 0), center=(5, 5, 0), normal=(0, 0, 1), radius=5
        )
        res = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "concentric",
                "target_a": refs["edge_a"],
                "target_b": refs["edge_b"],
                "tolerance_deg": 0.01,
                "tolerance_mm": 0.001,
            },
            group="inspect",
        )
        assert res.data["relation"] == "concentric"
        assert res.data["matches"] is True
        assert res.data["measured"]["angle_deg"] == 0.0
        assert res.data["measured"]["offset_mm"] == 0.0


# =========================================================================
# Debug sweep: falsify the repair with unknown / elliptical-arc geometry
# =========================================================================


@pytest.mark.asyncio
async def test_fusion_inspect_unknown_curve_type_fails_closed(mock_desktop_service):
    """Debug sweep: an unknown/unverifiable curve type exposing start/end points and
    center+normal must fail closed for both angle (straight-line proof) and
    concentricity (circular proof)."""
    with InspectFusionFake() as fake:
        cad_service = _make_service(mock_desktop_service)
        refs = _register_refs(cad_service)

        fake.body._edges[0].geometry = _UnknownGeom((0, 0, 0), (10, 0, 0))
        fake.body._edges[1].geometry = _UnknownGeom((0, 0, 0), (10, 0, 0))

        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "angle",
                    "target_a": refs["edge_a"],
                    "target_b": refs["edge_b"],
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY

        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "concentric",
                    "target_a": refs["edge_a"],
                    "target_b": refs["edge_b"],
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


@pytest.mark.asyncio
async def test_fusion_inspect_elliptical_arc_center_normal_rejected(
    mock_desktop_service,
):
    """Debug sweep: EllipticalArc3D exposing center+normal must fail closed for
    concentricity (only Circle3D/Arc3D are positively proven circular)."""
    with InspectFusionFake() as fake:
        cad_service = _make_service(mock_desktop_service)
        refs = _register_refs(cad_service)

        fake.body._edges[0].geometry = _EllipticalArcGeom(
            center=(5, 5, 0), normal=(0, 0, 1)
        )
        fake.body._edges[1].geometry = _EllipticalArcGeom(
            center=(5, 5, 0), normal=(0, 0, 1)
        )
        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "concentric",
                    "target_a": refs["edge_a"],
                    "target_b": refs["edge_b"],
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY