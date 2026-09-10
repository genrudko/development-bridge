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
from app.fusion_cad.snapshots import BodySummary, ModelSnapshot, SnapshotCounts

# =========================================================================
# Minimal representative Adsk Fusion fake for Task 7 final review repair.
#
# Supports:
#   * body entities resolving by native token with an exact `area`
#   * face entities resolving by native token with an exact `area`
#   * 6-face thickness bodies with settable per-face geometry/vertices/loops
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
    """Nonplanar geometry: has axis/origin but NO normal -> _face_plane must fail."""

    def __init__(self, origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0), radius=5.0):
        self.objectType = "Cylinder"
        self.origin = origin if isinstance(origin, _P) else _P(*origin)
        self.axis = axis if isinstance(axis, _P) else _P(*axis)
        self.radius = radius


def _default_face(idx, token):
    f = _Face(token=token)
    f.geometry = _PlaneGeom()
    f.vertices = _Coll(
        [
            _Vertex(0, 0, 0),
            _Vertex(10, 0, 0),
            _Vertex(10, 10, 0),
            _Vertex(0, 10, 0),
        ]
    )
    f.loops = _Coll([object()])
    return f


class _Face:
    def __init__(self, token="face_token_x"):
        self.entityToken = token
        self.objectType = "adsk::fusion::BRepFace"
        self.area = 10.0
        self.centroid = _P(5.0, 5.0, 5.0)
        self.body = None
        self.geometry = _PlaneGeom()
        self.vertices = _Coll(
            [
                _Vertex(0, 0, 0),
                _Vertex(10, 0, 0),
                _Vertex(10, 10, 0),
                _Vertex(0, 10, 0),
            ]
        )
        self.loops = _Coll([object()])


class _ThicknessBody:
    def __init__(self):
        self.name = "WallBody"
        self.entityToken = "wall_body_token"
        self.objectType = "adsk::fusion::BRepBody"
        self.isSolid = True
        self.volume = 500.0
        self.area = 50.0
        self._faces = [
            _default_face(i, f"wall_face_token_{i}") for i in range(6)
        ]
        for f in self._faces:
            f.body = self
        self.faces = _Coll(self._faces)
        self.edges = _Coll([])
        self.vertices = _Coll([])


class _Body:
    def __init__(self, token, name, area=50.0):
        self.entityToken = token
        self.objectType = "adsk::fusion::BRepBody"
        self.name = name
        self.isSolid = True
        self.volume = 500.0
        self.area = area


class _Design:
    def __init__(self):
        self._token_map = {}

    def register(self, token, entity):
        self._token_map[token] = entity

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


class InspectRuntime:
    """Installs a representative adsk runtime into sys.modules for the session."""

    def __init__(self):
        self.design = _Design()
        self.application = _Application(self.design)
        _Application._instance = self.application

    def __enter__(self):
        self._saved = {
            "adsk": sys.modules.get("adsk"),
            "adsk.core": sys.modules.get("adsk.core"),
            "adsk.fusion": sys.modules.get("adsk.fusion"),
        }
        adsk = types.ModuleType("adsk")
        core = types.ModuleType("adsk.core")
        fusion = types.ModuleType("adsk.fusion")
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


def _make_service(mock_desktop_service):
    cad_service = FusionCadService(mock_desktop_service)
    cad_service.set_node_capabilities("desk-1", _inspect_matrix())

    async def run_rendered_inspect(node_id, tool_name, arguments, journal=None):
        script = arguments["object"]["script"]
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
# FINDING 1: EntitySelector inspection targets resolve through Task5
# SelectorEngine with EXACT-ONE cardinality and inject native hints.
# =========================================================================


def _seed_snapshot_and_registry(cad_service, *, include_faces=False):
    bodies = (
        BodySummary(
            ref="ent_b_arm", name="ArmBody", component_path=("Root",), is_solid=True
        ),
        BodySummary(
            ref="ent_b_brk",
            name="BracketBody",
            component_path=("Root",),
            is_solid=True,
        ),
    )
    snap_kwargs = {
        "snapshot_id": "snap_inspect_final_1",
        "document_ref": "doc_1",
        "model_revision": "rev_1",
        "structural_hash": "hash_inspect_final_1",
        "counts": SnapshotCounts(bodies=2),
        "bodies": bodies,
    }
    if include_faces:
        from app.fusion_cad.models import ImmutableMapping

        snap_kwargs["faces"] = (
            ImmutableMapping(
                {
                    "ref": "ent_f_panel",
                    "kind": "face",
                    "name": "PanelFace",
                    "component_path": ["Root"],
                    "tags": [
                        {
                            "group": "bridge.cad/v1",
                            "name": "layout",
                            "value": "schedule",
                        }
                    ],
                    "role": ["decorative_text"],
                }
            ),
        )
        snap_kwargs["counts"] = SnapshotCounts(bodies=2, faces=1)
    snap = ModelSnapshot(**snap_kwargs)
    cad_service.snapshot_store.put(snap)

    cad_service.ref_registry.issue(
        document_ref="doc_1",
        kind="body",
        name="ArmBody",
        component_path=("Root",),
        native_token="arm_token_1",
        opaque_ref="ent_b_arm",
    )
    cad_service.ref_registry.issue(
        document_ref="doc_1",
        kind="body",
        name="BracketBody",
        component_path=("Root",),
        native_token="bracket_token_1",
        opaque_ref="ent_b_brk",
    )
    if include_faces:
        cad_service.ref_registry.issue(
            document_ref="doc_1",
            kind="face",
            name="PanelFace",
            component_path=("Root",),
            native_token="panel_face_token_1",
            opaque_ref="ent_f_panel",
        )


@pytest.mark.asyncio
async def test_inspect_selector_regex_name_component_path_resolves_native_hint(
    mock_desktop_service,
):
    """Proves an inspect EntitySelector (regex name + component_path) resolves
    through Task5 SelectorEngine exact-one and injects a native resolution hint,
    rather than being passed through for a kind/name-only script fallback."""
    with InspectRuntime() as rt:
        rt.design.register("arm_token_1", _Body("arm_token_1", "ArmBody"))
        rt.design.register(
            "bracket_token_1", _Body("bracket_token_1", "BracketBody")
        )

        cad_service = _make_service(mock_desktop_service)
        _seed_snapshot_and_registry(cad_service)

        res = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "area",
                "target": {
                    "kind": "body",
                    "name": {"regex": "^Arm"},
                    "component_path": ["Root"],
                },
                "document_ref": "doc_1",
            },
            group="inspect",
        )
        assert res.status == "succeeded"
        assert res.data["quantity"] == "area"
        assert res.data["value"] == pytest.approx(5000.0)
        # Invariant: the hidden native token never leaks into the public result.
        assert "arm_token_1" not in str(res.model_dump(mode="python"))


@pytest.mark.asyncio
async def test_inspect_selector_role_tag_provenance_style_face_resolves_native_hint(
    mock_desktop_service,
):
    """Proves an inspect EntitySelector on role/tag/metadata (full-detail snapshot
    face record) resolves exact-one through Task5 SelectorEngine and injects a
    native hint, not a kind/name literal fallback."""
    with InspectRuntime() as rt:
        rt.design.register("arm_token_1", _Body("arm_token_1", "ArmBody"))
        rt.design.register(
            "bracket_token_1", _Body("bracket_token_1", "BracketBody")
        )
        rt.design.register("panel_face_token_1", _Face("panel_face_token_1"))

        cad_service = _make_service(mock_desktop_service)
        _seed_snapshot_and_registry(cad_service, include_faces=True)

        res = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "area",
                "target": {
                    "kind": "face",
                    "tag": {
                        "group": "bridge.cad/v1",
                        "name": "layout",
                        "value": "schedule",
                    },
                    "role": "decorative_text",
                },
                "document_ref": "doc_1",
            },
            group="inspect",
        )
        assert res.status == "succeeded"
        assert res.data["quantity"] == "area"
        assert res.data["value"] == pytest.approx(1000.0)
        # Invariant: the hidden native token never leaks into the public result.
        assert "panel_face_token_1" not in str(res.model_dump(mode="python"))


@pytest.mark.asyncio
async def test_inspect_selector_empty_fails_closed_before_dispatch(
    mock_desktop_service,
):
    """Proves an inspect EntitySelector matching nothing fails SELECTOR_EMPTY
    before any script dispatch (no kind/name fallback reaching the script)."""
    with InspectRuntime() as rt:
        rt.design.register("arm_token_1", _Body("arm_token_1", "ArmBody"))
        rt.design.register(
            "bracket_token_1", _Body("bracket_token_1", "BracketBody")
        )

        cad_service = _make_service(mock_desktop_service)
        _seed_snapshot_and_registry(cad_service)

        dispatched: list[bool] = []

        async def guard_call(node_id, tool_name, arguments, journal=None):
            dispatched.append(True)
            return {"status": "should_not_happen"}

        mock_desktop_service.call = guard_call  # type: ignore[assignment]

        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "area",
                    "target": {"kind": "body", "name": "NoSuchBody"},
                    "document_ref": "doc_1",
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.SELECTOR_EMPTY
        # Fail closed: no script dispatched
        assert dispatched == []


@pytest.mark.asyncio
async def test_inspect_selector_ambiguous_fails_closed_before_dispatch(
    mock_desktop_service,
):
    """Proves an inspect EntitySelector matching multiple targets fails
    SELECTOR_AMBIGUOUS before any script dispatch."""
    with InspectRuntime() as rt:
        rt.design.register("arm_token_1", _Body("arm_token_1", "ArmBody"))
        rt.design.register(
            "bracket_token_1", _Body("bracket_token_1", "BracketBody")
        )

        cad_service = _make_service(mock_desktop_service)
        _seed_snapshot_and_registry(cad_service)

        dispatched: list[bool] = []

        async def guard_call(node_id, tool_name, arguments, journal=None):
            dispatched.append(True)
            return {"status": "should_not_happen"}

        mock_desktop_service.call = guard_call  # type: ignore[assignment]

        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "area",
                    "target": {"kind": "body"},
                    "document_ref": "doc_1",
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.SELECTOR_AMBIGUOUS
        assert dispatched == []


# =========================================================================
# FINDING 2: face_to_face_thickness requires positive proof of a simple
# six-face rectangular-prismatic solid wall (no curved/nonplanar cavity).
# =========================================================================


def _make_rect_prism_body():
    body = _ThicknessBody()
    # Selected opposite rectangular planar wall faces.
    body._faces[0].geometry = _PlaneGeom((0, 0, 0), (0, 0, 1))
    body._faces[1].geometry = _PlaneGeom((0, 0, 5), (0, 0, -1))
    return body


def _register_face_refs(cad_service):
    return {
        "face_a": cad_service.ref_registry.issue(
            document_ref="doc_1",
            kind="face",
            name="f0",
            native_token="wall_face_token_0",
        ).ref,
        "face_b": cad_service.ref_registry.issue(
            document_ref="doc_1",
            kind="face",
            name="f1",
            native_token="wall_face_token_1",
        ).ref,
    }


@pytest.mark.asyncio
async def test_fusion_inspect_thickness_curved_nested_cavity_rejected(
    mock_desktop_service,
):
    """Falsification: a same-body solid with a curved/nonplanar internal cavity
    wall (fails _face_plane) between the selected rectangular pair must NOT claim
    exact thickness. Current 92ce747 skips the _face_plane failure and falsely
    returns an exact value."""
    with InspectRuntime() as rt:
        body = _make_rect_prism_body()
        # A curved (nonplanar) internal wall strictly between the pair:
        # a cylindrical surface spanning z in (0,5), which _face_plane cannot read.
        body._faces[3].geometry = _CylinderGeom(
            origin=(5, 5, 2.5), axis=(0, 0, 1), radius=5.0
        )
        for idx, f in enumerate(body._faces):
            rt.design.register(f.entityToken, f)
        rt.design.register("wall_body_token", body)

        cad_service = _make_service(mock_desktop_service)
        refs = _register_face_refs(cad_service)

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
async def test_fusion_inspect_thickness_exact_rectangular_wall_succeeds(
    mock_desktop_service,
):
    """Control: an exact six-face rectangular-prismatic opposing wall pair still
    returns exact thickness (positive proof of a simple uniform solid wall)."""
    with InspectRuntime() as rt:
        body = _make_rect_prism_body()
        for idx, f in enumerate(body._faces):
            rt.design.register(f.entityToken, f)
        rt.design.register("wall_body_token", body)

        cad_service = _make_service(mock_desktop_service)
        refs = _register_face_refs(cad_service)

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
        assert res.data["unambiguous"] is True


@pytest.mark.asyncio
async def test_fusion_inspect_thickness_extra_face_rejected(mock_desktop_service):
    """Proves a 7-face solid (e.g. a stepped/extra-face wall) fails closed."""
    with InspectRuntime() as rt:
        body = _ThicknessBody()
        body._faces[0].geometry = _PlaneGeom((0, 0, 0), (0, 0, 1))
        body._faces[1].geometry = _PlaneGeom((0, 0, 5), (0, 0, -1))
        # Add an extra face -> 7 total.
        extra = _default_face(6, "wall_face_token_6")
        extra.body = body
        body._faces.append(extra)
        body.faces = _Coll(body._faces)
        for idx, f in enumerate(body._faces):
            rt.design.register(f.entityToken, f)
        rt.design.register("wall_body_token", body)

        cad_service = _make_service(mock_desktop_service)
        refs = _register_face_refs(cad_service)

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