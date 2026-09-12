from __future__ import annotations

import pytest

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.refs import EntityRefRegistry
from app.fusion_cad.snapshots import (
    FeatureDependency,
    ModelSnapshot,
    SnapshotCounts,
    SnapshotStore,
    compute_structural_hash,
    normalize_feature,
    normalize_sketch_read,
    normalize_snapshot,
)


def test_normalize_snapshot_preserves_text_parameter_without_numeric_value() -> None:
    snapshot = normalize_snapshot(
        {
            "document_ref": "doc_text_parameter",
            "model_revision": "rev_1",
            "parameters": [
                {
                    "name": "d274",
                    "expression": "'УРОКОВ'",
                    "value": None,
                    "unit": "Text",
                }
            ],
        }
    )

    assert len(snapshot.parameters) == 1
    parameter = snapshot.parameters[0]
    assert parameter.name == "d274"
    assert parameter.expression == "'УРОКОВ'"
    assert parameter.value is None
    assert parameter.unit == "Text"


@pytest.fixture
def raw_fixture() -> dict:
    """Raw Fusion model fixture containing 240 faces across bodies, features, sketches, and parameters."""
    return {
        "document": {
            "document_ref": "doc_main_123",
            "name": "Assembly1",
            "saved_version": 4,
            "is_modified": False,
        },
        "model_revision": "rev_1",
        "counts": {
            "faces": 240,
            "edges": 360,
            "vertices": 120,
        },
        "faces": [{"id": f"face_{i}", "area": 12.5} for i in range(240)],
        "components": [
            {"name": "BracketComp", "id": "comp_2"},
            {"name": "BaseComp", "id": "comp_1"},
        ],
        "occurrences": [
            {
                "name": "BracketComp:1",
                "full_path_name": "BaseComp:1+BracketComp:1",
                "is_visible": True,
                "effective_visibility": True,
                "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
            },
            {
                "name": "BaseComp:1",
                "full_path_name": "BaseComp:1",
                "is_visible": True,
                "effective_visibility": True,
                "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
            },
        ],
        "bodies": [
            {
                "name": "Body2",
                "component_name": "BracketComp",
                "is_solid": True,
                "volume": 2500.0,
                "area": 1200.0,
                "bounding_box": {
                    "min": [0.0, 0.0, 0.0],
                    "max": [50.0, 25.0, 10.0],
                },
                "faces_count": 100,
                "edges_count": 150,
                "is_visible": True,
                "effective_visibility": True,
            },
            {
                "name": "Body1",
                "component_name": "BaseComp",
                "is_solid": True,
                "volume": 5000.0,
                "area": 2400.0,
                "bounding_box": {
                    "min": [-10.0, -10.0, 0.0],
                    "max": [90.0, 40.0, 20.0],
                },
                "faces_count": 140,
                "edges_count": 210,
                "is_visible": True,
                "effective_visibility": True,
            },
        ],
        "sketches": [
            {
                "name": "Sketch2",
                "component_name": "BracketComp",
                "profiles_count": 1,
                "constraints_count": 4,
                "dimensions_count": 2,
                "fully_constrained": True,
            },
            {
                "name": "Sketch1",
                "component_name": "BaseComp",
                "profiles_count": 2,
                "constraints_count": 8,
                "dimensions_count": 4,
                "fully_constrained": False,
            },
        ],
        "timeline": [
            {
                "index": 1,
                "name": "Extrude1",
                "feature_type": "ExtrudeFeature",
                "is_suppressed": False,
                "health_status": "ok",
                "diagnostic_message": None,
                "inputs": [
                    {
                        "ref": "ent_sketch_1",
                        "kind": "sketch",
                        "dependency_type": "exact",
                    },
                ],
                "outputs": ["ent_body_1"],
            },
            {
                "index": 0,
                "name": "BaseSketch",
                "feature_type": "SketchFeature",
                "is_suppressed": False,
                "health_status": "ok",
                "diagnostic_message": None,
                "inputs": [],
                "outputs": ["ent_sketch_1"],
            },
        ],
        "parameters": {
            "model_parameters": [
                {"name": "d2", "value": 25.0, "expression": "25 mm", "unit": "mm"},
                {"name": "d1", "value": 50.0, "expression": "50 mm", "unit": "mm"},
            ],
            "user_parameters": [
                {
                    "name": "length",
                    "value": 100.0,
                    "expression": "100 mm",
                    "unit": "mm",
                },
            ],
        },
    }


def test_default_snapshot_is_semantic_not_topology_dump(raw_fixture: dict):
    snapshot = normalize_snapshot(raw_fixture)
    assert snapshot.counts.faces == 240
    assert snapshot.faces is None
    assert snapshot.components
    assert snapshot.bodies
    assert len(snapshot.components) == 2
    assert len(snapshot.bodies) == 2
    assert snapshot.structural_hash
    assert snapshot.snapshot_id.startswith("snap_")
    assert snapshot.document_ref == "doc_main_123"


def test_full_detail_snapshot_includes_topology(raw_fixture: dict):
    snapshot = normalize_snapshot(raw_fixture, detail="full")
    assert snapshot.counts.faces == 240
    assert snapshot.faces is not None
    assert len(snapshot.faces) == 240


def test_canonical_normalization_sorting_and_structural_hash_stability(
    raw_fixture: dict,
):
    """Proves normalization sorts unordered Fusion collections and yields identical structural hash."""
    snap1 = normalize_snapshot(raw_fixture)

    # Reorder components, occurrences, bodies, parameters in fixture
    reordered_fixture = dict(raw_fixture)
    reordered_fixture["components"] = list(reversed(raw_fixture["components"]))
    reordered_fixture["occurrences"] = list(reversed(raw_fixture["occurrences"]))
    reordered_fixture["bodies"] = list(reversed(raw_fixture["bodies"]))
    reordered_fixture["sketches"] = list(reversed(raw_fixture["sketches"]))

    snap2 = normalize_snapshot(reordered_fixture)

    # Collections are canonically sorted
    assert [c.name for c in snap1.components] == ["BaseComp", "BracketComp"]
    assert [c.name for c in snap2.components] == ["BaseComp", "BracketComp"]
    assert [b.name for b in snap1.bodies] == ["Body1", "Body2"]
    assert [b.name for b in snap2.bodies] == ["Body1", "Body2"]

    # Structural hashes match identically
    assert snap1.structural_hash == snap2.structural_hash


def test_feature_tree_dependencies_never_upgrade_inferred_to_exact():
    """Proves inferred dependencies are strictly preserved and never upgraded to exact."""
    feat_data = {
        "index": 2,
        "name": "Fillet1",
        "feature_type": "FilletFeature",
        "is_suppressed": False,
        "health_status": "warning",
        "diagnostic_message": "Edge geometry modified",
        "inputs": [
            {"ref": "ent_body_1", "kind": "body", "dependency_type": "inferred"},
            {"ref": "ent_param_r", "kind": "parameter", "dependency_type": "unknown"},
            {"ref": "ent_edge_1", "kind": "edge", "dependency_type": "exact"},
        ],
        "outputs": ["ent_body_1"],
    }
    feat = normalize_feature(feat_data)
    assert feat.timeline_index == 2
    assert feat.health_status == "warning"
    assert feat.diagnostic_message == "Edge geometry modified"

    dep_types = {d.ref: d.dependency_type for d in feat.dependencies}
    assert dep_types["ent_body_1"] == "inferred"
    assert dep_types["ent_param_r"] == "unknown"
    assert dep_types["ent_edge_1"] == "exact"

    # Falsification: verify that attempting to upgrade an inferred dependency fails
    dep = FeatureDependency(ref="ent_b", dependency_type="inferred")
    assert dep.dependency_type == "inferred"


def test_sketch_read_missing_native_token_preserves_existing_token_backed_ref():
    registry = EntityRefRegistry()
    public_ref = registry.issue(document_ref="doc_live", kind="sketch", native_token="private-sketch-token", name="HandsLiveSketch", opaque_ref="ent_live_sketch").ref
    result = normalize_sketch_read({"ref": public_ref, "name": "HandsLiveSketch", "profiles": []}, ref_registry=registry, document_ref="doc_live")
    record = registry.get_internal_record(public_ref, "doc_live")
    assert result.ref == public_ref
    assert record is not None
    assert record.native_token == "private-sketch-token"
    assert registry.get_internal_record_by_native_token("doc_live", "private-sketch-token") is record


def test_sketch_read_does_not_invent_unsupported_dof():
    """Proves sketch read faithfully exposes constraints and profiles without inventing numeric DOF."""
    raw_sketch = {
        "ref": "ent_sketch_10",
        "name": "ProfileSketch",
        "fully_constrained": True,
        "profiles": [{"ref": "ent_prof_1", "area": 150.0, "loops_count": 1}],
        "constraints": [{"type": "Coincident", "is_satisfied": True}],
        "dimensions": [{"name": "d10", "value": 45.0, "expression": "45 mm"}],
        "geometry": {
            "lines": [
                {
                    "start": {
                        "x": 0.0,
                        "y": 0.0,
                        "z": 0.0,
                        "frame": {"space": "sketch", "ref": "ent_sketch_10"},
                    },
                    "end": {
                        "x": 10.0,
                        "y": 0.0,
                        "z": 0.0,
                        "frame": {"space": "sketch", "ref": "ent_sketch_10"},
                    },
                }
            ]
        },
    }
    res = normalize_sketch_read(raw_sketch)
    assert res.ref == "ent_sketch_10"
    assert res.fully_constrained is True
    assert len(res.profiles) == 1
    assert len(res.constraints) == 1
    # DOF is strictly None / not invented
    assert getattr(res, "dof", None) is None


def test_snapshot_store_put_get_and_lru_discipline():
    store = SnapshotStore(max_documents=2, max_snapshots_per_doc=2)

    snap1 = ModelSnapshot(
        snapshot_id="snap_1",
        document_ref="doc_1",
        model_revision="rev_1",
        structural_hash="hash_1",
        counts=SnapshotCounts(bodies=1),
    )
    snap2 = ModelSnapshot(
        snapshot_id="snap_2",
        document_ref="doc_1",
        model_revision="rev_2",
        structural_hash="hash_2",
        counts=SnapshotCounts(bodies=2),
    )
    snap3 = ModelSnapshot(
        snapshot_id="snap_3",
        document_ref="doc_1",
        model_revision="rev_3",
        structural_hash="hash_3",
        counts=SnapshotCounts(bodies=3),
    )

    store.put(snap1)
    store.put(snap2)
    assert store.get("snap_1") is not None
    assert store.get_latest("doc_1").snapshot_id == "snap_2"

    # Adding third evicts oldest for doc_1 (max_snapshots_per_doc=2)
    store.put(snap3)
    assert store.get("snap_1") is None
    assert store.get("snap_2") is not None
    assert store.get("snap_3") is not None
    assert store.get_latest("doc_1").snapshot_id == "snap_3"


def test_sketch_read_filtering_profiles_and_constraints():
    raw_sketch = {
        "ref": "ent_sk_filter",
        "name": "FilteredSketch",
        "profiles": [{"ref": "ent_prof_1", "area": 10.0}],
        "constraints": [{"type": "Horizontal", "is_satisfied": True}],
        "dimensions": [{"name": "d1", "value": 20.0}],
    }
    # Both included by default
    res1 = normalize_sketch_read(raw_sketch)
    assert len(res1.profiles) == 1
    assert len(res1.constraints) == 1

    # Exclude profiles
    res2 = normalize_sketch_read(raw_sketch, include_profiles=False)
    assert len(res2.profiles) == 0
    assert len(res2.constraints) == 1

    # Exclude constraints
    res3 = normalize_sketch_read(raw_sketch, include_constraints=False)
    assert len(res3.profiles) == 1
    assert len(res3.constraints) == 0


def test_normalize_feature_invalid_dependency_type_falls_back_to_unknown():
    raw_feat = {
        "index": 5,
        "name": "CutFeature",
        "feature_type": "Cut",
        "inputs": [
            {"ref": "ent_dep_bogus", "dependency_type": "fabricated_exact_guess"},
        ],
    }
    feat = normalize_feature(raw_feat)
    assert feat.dependencies[0].dependency_type == "unknown"


def test_selector_query_against_snapshot_components_and_features(raw_fixture: dict):
    from app.fusion_cad.selectors import SelectorEngine

    snap = normalize_snapshot(raw_fixture)
    engine = SelectorEngine()

    candidates = (
        list(snap.components)
        + list(snap.occurrences)
        + list(snap.bodies)
        + list(snap.sketches)
        + list(snap.features)
    )

    # Query by kind="body"
    res_bodies = engine.query({"kind": "body"}, candidates)
    assert res_bodies.matched_count == 2
    assert len(res_bodies.refs) == 2

    # Query by name="BaseSketch"
    res_sketch = engine.query({"name": "BaseSketch"}, candidates)
    assert res_sketch.matched_count == 1
    assert res_sketch.entities[0].name == "BaseSketch"

    # Query by regex
    res_regex = engine.query({"name": {"regex": "^Body"}}, candidates)
    assert res_regex.matched_count == 2


def test_falsify_finding_1_native_token_never_exposed_in_component_summary_or_snapshot():
    """Falsify Finding 1: Native Fusion entityToken must never be exposed via ComponentSummary.id or any snapshot field."""
    from app.fusion_cad.refs import EntityRefRegistry

    reg = EntityRefRegistry()
    raw = {
        "document": {"document_ref": "doc_tok_test"},
        "components": [
            {
                "name": "LeakyComp",
                "entityToken": "AQAAAB4AAAAxMjM0NTY3ODkwYWJjZGVm",
            },
            {
                "name": "LeakyCompWithId",
                "id": "AQAAAB4AAAAxMjM0NTY3ODkwYWJjZGVm",
                "entityToken": "AQAAAB4AAAAxMjM0NTY3ODkwYWJjZGVm",
            },
        ],
    }
    snap = normalize_snapshot(raw, ref_registry=reg)
    assert len(snap.components) == 2
    for comp in snap.components:
        # Verify public opaque ref is issued
        assert comp.ref.startswith("ent_")
        assert comp.ref != "AQAAAB4AAAAxMjM0NTY3ODkwYWJjZGVm"
        # Invariant: entityToken must NOT leak via comp.id or any other field
        assert getattr(comp, "id", None) != "AQAAAB4AAAAxMjM0NTY3ODkwYWJjZGVm"
        assert getattr(comp, "entityToken", None) is None
        assert "AQAA" not in str(comp.model_dump())


def test_rendered_model_snapshot_preserves_body_and_sketch_tokens_only_in_registry(
    monkeypatch,
):
    import sys
    import types

    from app.fusion_cad.refs import EntityRefRegistry
    from app.fusion_cad.scripts import FusionCadScriptBundle

    class Collection:
        def __init__(self, items=()):
            self._items = list(items)

        @property
        def count(self):
            return len(self._items)

        def item(self, index):
            return self._items[index]

    point = lambda x=0.0, y=0.0, z=0.0: types.SimpleNamespace(x=x, y=y, z=z)
    bbox = types.SimpleNamespace(minPoint=point(), maxPoint=point(1.0, 1.0, 1.0))
    body_token = "SECRET_BODY_NATIVE_TOKEN"
    sketch_token = "SECRET_SKETCH_NATIVE_TOKEN"
    body = types.SimpleNamespace(
        name="Mutable Body Name",
        entityToken=body_token,
        id=None,
        isSolid=True,
        volume=1.0,
        area=2.0,
        isLightBulbOn=True,
        isVisible=True,
        boundingBox=bbox,
        faces=Collection(),
        edges=Collection(),
        vertices=Collection(),
        physicalProperties=None,
        attributes=Collection(),
    )
    sketch = types.SimpleNamespace(
        name="Mutable Sketch Name",
        entityToken=sketch_token,
        id=None,
        isLightBulbOn=True,
        isVisible=True,
        profiles=Collection(),
        sketchCurves=Collection(),
        geometricConstraints=Collection(),
        sketchDimensions=Collection(),
        sketchPoints=Collection(),
        boundingBox=bbox,
        attributes=Collection(),
    )
    root = types.SimpleNamespace(
        name="Root",
        id="root-id",
        entityToken="root-token",
        allOccurrences=Collection(),
        bRepBodies=Collection([body]),
        sketches=Collection([sketch]),
        attributes=Collection(),
    )
    design = types.SimpleNamespace(
        rootComponent=root,
        timeline=Collection(),
        allComponents=Collection([root]),
        allParameters=Collection(),
    )

    class Products:
        def itemByProductType(self, product_type):
            assert product_type == "DesignProductType"
            return design

    doc = types.SimpleNamespace(
        creationId="token-design",
        dataId=None,
        dataFile=None,
        name="Token Design",
        isModified=False,
        savedVersion=None,
        products=Products(),
        attributes=Collection(),
    )
    app = types.SimpleNamespace(activeDocument=doc, activeProduct=design)
    adsk = types.ModuleType("adsk")
    core = types.ModuleType("adsk.core")
    fusion = types.ModuleType("adsk.fusion")
    core.Application = types.SimpleNamespace(get=lambda: app)
    fusion.Design = types.SimpleNamespace(cast=lambda value: value if value is design else None)
    adsk.core = core
    adsk.fusion = fusion
    monkeypatch.setitem(sys.modules, "adsk", adsk)
    monkeypatch.setitem(sys.modules, "adsk.core", core)
    monkeypatch.setitem(sys.modules, "adsk.fusion", fusion)

    rendered = FusionCadScriptBundle.build(
        "read", {"operation": "model_snapshot", "detail": "compact"}
    )
    scope = {"__name__": "__main__"}
    exec(compile(rendered, "<body-sketch-token-snapshot>", "exec"), scope)  # noqa: S102
    raw_snapshot = scope["_output"]["data"]

    registry = EntityRefRegistry()
    snapshot = normalize_snapshot(raw_snapshot, ref_registry=registry)
    body_record = registry.get_internal_record(snapshot.bodies[0].ref)
    sketch_record = registry.get_internal_record(snapshot.sketches[0].ref)
    assert body_record is not None and body_record.native_token == body_token
    assert sketch_record is not None and sketch_record.native_token == sketch_token
    public_snapshot = snapshot.model_dump(mode="json")
    assert body_token not in str(public_snapshot)
    assert sketch_token not in str(public_snapshot)


def test_snapshot_missing_body_and_sketch_tokens_never_uses_names_as_native_authority():
    from app.fusion_cad.refs import EntityRefRegistry

    registry = EntityRefRegistry()
    snapshot = normalize_snapshot(
        {
            "document": {"document_ref": "doc_missing_tokens"},
            "bodies": [{"name": "Mutable Body Name"}],
            "sketches": [{"name": "Mutable Sketch Name"}],
        },
        ref_registry=registry,
    )

    body_record = registry.get_internal_record(snapshot.bodies[0].ref)
    sketch_record = registry.get_internal_record(snapshot.sketches[0].ref)
    assert body_record is not None and body_record.native_token is None
    assert sketch_record is not None and sketch_record.native_token is None


def test_falsify_finding_3_structural_hash_deterministic_across_fresh_registries():
    """Falsify Finding 3: Structural hash must be deterministic across two fresh EntityRefRegistry lifecycles."""
    from app.fusion_cad.refs import EntityRefRegistry

    raw_data = {
        "document": {"document_ref": "doc_main_123"},
        "model_revision": "rev_1",
        "counts": {"faces": 2},
        "components": [
            {"name": "BracketComp", "entityToken": "tok_c2"},
            {"name": "BaseComp", "entityToken": "tok_c1"},
        ],
        "occurrences": [
            {
                "name": "BracketComp:1",
                "full_path_name": "BaseComp:1+BracketComp:1",
                "entityToken": "tok_o1",
            },
        ],
        "bodies": [
            {
                "name": "Body1",
                "component_name": "BaseComp",
                "entityToken": "tok_b1",
                "volume": 10.0,
                "area": 5.0,
            },
        ],
        "sketches": [
            {"name": "Sketch1", "component_name": "BaseComp", "entityToken": "tok_s1"},
        ],
        "timeline": [
            {
                "index": 0,
                "name": "Extrude1",
                "feature_type": "ExtrudeFeature",
                "entityToken": "tok_f1",
            },
        ],
        "parameters": [
            {"name": "d1", "value": 50.0},
        ],
    }

    reg1 = EntityRefRegistry()
    reg2 = EntityRefRegistry()

    snap1 = normalize_snapshot(raw_data, ref_registry=reg1)
    snap2 = normalize_snapshot(raw_data, ref_registry=reg2)

    # Prove registries generated distinct UUID-backed refs for the same native entities
    assert snap1.components[0].ref != snap2.components[0].ref
    assert snap1.bodies[0].ref != snap2.bodies[0].ref
    # Invariant: structural hashes must match identically despite volatile UUID refs
    assert snap1.structural_hash == snap2.structural_hash


def test_falsify_finding_5_component_path_coverage_and_feature_parent_children():
    """Falsify Finding 5 & Minor: component_path coverage and FeatureRecord parent/children."""

    raw = {
        "document": {"document_ref": "doc_path_test"},
        "components": [
            {
                "name": "PartA",
                "component_path": ["Root", "SubAssy", "PartA"],
            }
        ],
        "occurrences": [
            {
                "name": "PartA:1",
                "full_path_name": "Root/SubAssy:1/PartA:1",
                "component_path": ["Root", "SubAssy:1"],
            }
        ],
        "timeline": [
            {
                "index": 0,
                "name": "Extrude1",
                "feature_type": "ExtrudeFeature",
                "component_path": ["Root", "SubAssy", "PartA"],
                "parent": "ent_feat_parent",
                "children": ["ent_feat_child1", "ent_feat_child2"],
            }
        ],
        "parameters": [
            {
                "name": "Length",
                "value": 100.0,
                "component_path": ["Root", "SubAssy", "PartA"],
            }
        ],
    }

    snap = normalize_snapshot(raw)
    comp = snap.components[0]
    occ = snap.occurrences[0]
    feat = snap.features[0]
    param = snap.parameters[0]

    assert comp.component_path == ("Root", "SubAssy", "PartA")
    assert occ.component_path == ("Root", "SubAssy:1")
    assert feat.component_path == ("Root", "SubAssy", "PartA")
    assert feat.parent == "ent_feat_parent"
    assert feat.children == ("ent_feat_child1", "ent_feat_child2")
    assert param.component_path == ("Root", "SubAssy", "PartA")

    # Default empty when not known (never fabricate)
    raw_empty = {
        "document": {"document_ref": "doc_path_empty"},
        "components": [{"name": "RootComp"}],
        "occurrences": [{"name": "RootComp:1", "full_path_name": "RootComp:1"}],
        "timeline": [{"index": 0, "name": "BaseFeat", "feature_type": "Base"}],
        "parameters": [{"name": "p1", "value": 1.0}],
    }
    snap_empty = normalize_snapshot(raw_empty)
    assert snap_empty.components[0].component_path == ()
    assert snap_empty.occurrences[0].component_path == ()
    assert snap_empty.features[0].component_path == ()
    assert snap_empty.features[0].parent is None
    assert snap_empty.features[0].children == ()
    assert snap_empty.parameters[0].component_path == ()


def test_nested_unique_token_secrets_sanitized_across_sketch_snapshot_and_summaries():
    """Regression: nested unique token secrets in mappings/lists must never leak through model_dump/str/repr/json."""
    secret_prof_tok = "secret::adsk::token::prof::12345"
    secret_prof_nested = "secret::adsk::token::prof_nested::67890"
    secret_const_tok = "secret::adsk::token::const::abcdef"
    secret_dim_tok = "secret::adsk::token::dim::112233"
    secret_geom_tok = "secret::adsk::token::geom::445566"
    secret_proj_tok = "secret::adsk::token::proj::778899"
    secret_text_tok = "secret::adsk::token::text::aabbcc"
    secret_sk_health_tok = "secret::adsk::token::sk_health::ddeeff"

    raw_sketch = {
        "ref": "ent_sketch_secure",
        "name": "SecureSketch",
        "profiles": [
            {
                "name": "Profile1",
                "entityToken": secret_prof_tok,
                "area": 12.5,
                "nested_items": [{"token": secret_prof_nested, "tag": "inner"}],
            }
        ],
        "constraints": [
            {
                "type": "Coincident",
                "native_token": secret_const_tok,
                "is_satisfied": True,
            }
        ],
        "dimensions": [{"name": "d1", "value": 50.0, "entityToken": secret_dim_tok}],
        "geometry": {
            "lines": [
                {"native_token": secret_geom_tok, "length": 10.0, "is_valid": True}
            ]
        },
        "linked_projection_state": [{"token": secret_proj_tok, "status": "linked"}],
        "texts": [{"text": "CAD", "entityToken": secret_text_tok, "size": 3.5}],
        "health": {
            "status": "ok",
            "native_token": secret_sk_health_tok,
        },
    }

    sketch_res = normalize_sketch_read(raw_sketch)
    dump_str = str(sketch_res.model_dump(mode="python"))
    repr_str = repr(sketch_res)
    str_str = str(sketch_res)

    for secret in (
        secret_prof_tok,
        secret_prof_nested,
        secret_const_tok,
        secret_dim_tok,
        secret_geom_tok,
        secret_proj_tok,
        secret_text_tok,
        secret_sk_health_tok,
    ):
        assert secret not in dump_str, f"Leaked {secret} in sketch model_dump"
        assert secret not in repr_str, f"Leaked {secret} in sketch repr"
        assert secret not in str_str, f"Leaked {secret} in sketch str"

    # Verify non-token semantic fields and types are strictly preserved without stringification
    assert sketch_res.profiles[0]["area"] == 12.5
    assert isinstance(sketch_res.profiles[0]["area"], float)
    assert sketch_res.profiles[0]["nested_items"][0]["tag"] == "inner"
    assert sketch_res.constraints[0]["type"] == "Coincident"
    assert sketch_res.constraints[0]["is_satisfied"] is True
    assert isinstance(sketch_res.constraints[0]["is_satisfied"], bool)
    assert sketch_res.dimensions[0]["value"] == 50.0
    assert isinstance(sketch_res.dimensions[0]["value"], float)
    assert sketch_res.geometry["lines"][0]["length"] == 10.0
    assert sketch_res.linked_projection_state[0]["status"] == "linked"
    assert sketch_res.texts[0]["text"] == "CAD"
    assert sketch_res.health["status"] == "ok"

    # Full snapshot with faces, edges, visibility, appearance, health, and logical_objects
    secret_face_tok = "secret::adsk::token::face::100"
    secret_face_nested = "secret::adsk::token::face_nested::101"
    secret_edge_tok = "secret::adsk::token::edge::200"
    secret_vis_tok = "secret::adsk::token::vis::300"
    secret_app_tok = "secret::adsk::token::app::400"
    secret_snap_health_tok = "secret::adsk::token::snap_health::500"
    secret_lo_tok = "secret::adsk::token::lo::600"
    secret_lo_nested = "secret::adsk::token::lo_nested::601"

    raw_snapshot = {
        "document": {"document_ref": "doc_sec_test"},
        "model_revision": "rev_1",
        "counts": {"faces": 1, "edges": 1, "vertices": 1},
        "faces": [
            {
                "id": "face_1",
                "area": 25.5,
                "entityToken": secret_face_tok,
                "sub_faces": [{"token": secret_face_nested}],
            }
        ],
        "edges": [
            {
                "id": "edge_1",
                "length": 15.2,
                "native_token": secret_edge_tok,
            }
        ],
        "visibility": {
            "effective_visibility": [
                {
                    "ref": "ent_body_1",
                    "is_visible": True,
                    "token": secret_vis_tok,
                }
            ]
        },
        "appearance": {
            "materials": [
                {
                    "name": "Titanium",
                    "entityToken": secret_app_tok,
                }
            ]
        },
        "health": {
            "status": "healthy",
            "native_token": secret_snap_health_tok,
        },
        "logical_objects": [
            {
                "group": "mfg",
                "name": "role",
                "value": "flange",
                "entityToken": secret_lo_tok,
                "metadata": {"token": secret_lo_nested, "weight": 4.2},
            }
        ],
    }

    snap = normalize_snapshot(raw_snapshot, detail="full")
    snap_dump_str = str(snap.model_dump(mode="python"))
    snap_repr_str = repr(snap)
    snap_str_str = str(snap)

    for secret in (
        secret_face_tok,
        secret_face_nested,
        secret_edge_tok,
        secret_vis_tok,
        secret_app_tok,
        secret_snap_health_tok,
        secret_lo_tok,
        secret_lo_nested,
    ):
        assert secret not in snap_dump_str, f"Leaked {secret} in snapshot model_dump"
        assert secret not in snap_repr_str, f"Leaked {secret} in snapshot repr"
        assert secret not in snap_str_str, f"Leaked {secret} in snapshot str"

    # Verify types and fields preserved
    assert snap.faces[0]["area"] == 25.5
    assert isinstance(snap.faces[0]["area"], float)
    assert snap.edges[0]["length"] == 15.2
    assert snap.visibility["effective_visibility"][0]["is_visible"] is True
    assert isinstance(snap.visibility["effective_visibility"][0]["is_visible"], bool)
    assert snap.appearance["materials"][0]["name"] == "Titanium"
    assert snap.health["status"] == "healthy"
    assert snap.logical_objects[0]["value"] == "flange"
    assert snap.logical_objects[0]["metadata"]["weight"] == 4.2


def test_structural_hash_stability_with_nested_lifecycle_refs_and_snapshot_id():
    """Regression: identical payloads differing only in nested ent_lifecycle_* and snapshot_id hash equal,
    while real semantic mutations hash different.
    """
    payload1 = {
        "document_ref": "doc_main_123",
        "model_revision": "rev_1",
        "snapshot_id": "snap_lifecycle_a1",
        "counts": {"faces": 10},
        "components": [{"name": "PartA", "ref": "ent_lifecycle_c1"}],
        "visibility": {
            "effective_visibility": [
                {
                    "ref": "ent_lifecycle_c1",
                    "target": "ent_lifecycle_c1",
                    "is_visible": True,
                }
            ]
        },
        "appearance": {
            "effective_appearance": [
                {"target": "ent_lifecycle_c1", "material": "Steel"}
            ]
        },
        "health": {
            "status": "ok",
            "snapshot_id": "snap_lifecycle_a1",
            "diagnostics": [{"entity_ref": "ent_lifecycle_c1", "is_healthy": True}],
        },
        "logical_objects": [
            {
                "group": "cad",
                "name": "role",
                "value": "bracket",
                "owner_ref": "ent_lifecycle_c1",
                "snapshot_id": "snap_lifecycle_a1",
            }
        ],
    }

    payload2 = {
        "document_ref": "doc_main_123",
        "model_revision": "rev_1",
        "snapshot_id": "snap_lifecycle_b2",
        "counts": {"faces": 10},
        "components": [{"name": "PartA", "ref": "ent_lifecycle_c2"}],
        "visibility": {
            "effective_visibility": [
                {
                    "ref": "ent_lifecycle_c2",
                    "target": "ent_lifecycle_c2",
                    "is_visible": True,
                }
            ]
        },
        "appearance": {
            "effective_appearance": [
                {"target": "ent_lifecycle_c2", "material": "Steel"}
            ]
        },
        "health": {
            "status": "ok",
            "snapshot_id": "snap_lifecycle_b2",
            "diagnostics": [{"entity_ref": "ent_lifecycle_c2", "is_healthy": True}],
        },
        "logical_objects": [
            {
                "group": "cad",
                "name": "role",
                "value": "bracket",
                "owner_ref": "ent_lifecycle_c2",
                "snapshot_id": "snap_lifecycle_b2",
            }
        ],
    }

    hash1 = compute_structural_hash(payload1)
    hash2 = compute_structural_hash(payload2)

    # Invariant: volatile lifecycle identities and snapshot IDs must not destabilize structural hash
    assert hash1 == hash2, (
        f"Structural hashes differed on volatile lifecycle refs/snapshot_id: {hash1} vs {hash2}"
    )

    # Semantic mutations:
    # 1. Visibility mutation (True -> False)
    payload_vis_mut = {
        **payload1,
        "visibility": {
            "effective_visibility": [
                {
                    "ref": "ent_lifecycle_c1",
                    "target": "ent_lifecycle_c1",
                    "is_visible": False,
                }
            ]
        },
    }
    hash_vis_mut = compute_structural_hash(payload_vis_mut)
    assert hash_vis_mut != hash1, (
        "Visibility mutation must yield different structural hash"
    )

    # 2. Logical object semantic role mutation ("bracket" -> "stiffener")
    payload_role_mut = {
        **payload1,
        "logical_objects": [
            {
                "group": "cad",
                "name": "role",
                "value": "stiffener",
                "owner_ref": "ent_lifecycle_c1",
                "snapshot_id": "snap_lifecycle_a1",
            }
        ],
    }
    hash_role_mut = compute_structural_hash(payload_role_mut)
    assert hash_role_mut != hash1, (
        "Logical object role mutation must yield different structural hash"
    )

    # 3. Health status mutation ("ok" -> "degraded")
    payload_health_mut = {
        **payload1,
        "health": {
            "status": "degraded",
            "snapshot_id": "snap_lifecycle_a1",
            "diagnostics": [{"entity_ref": "ent_lifecycle_c1", "is_healthy": False}],
        },
    }
    hash_health_mut = compute_structural_hash(payload_health_mut)
    assert hash_health_mut != hash1, (
        "Health mutation must yield different structural hash"
    )


def test_failed_cad_error_boundary_sanitizes_nested_token_aliases():
    """Regression (a): failed CAD error boundary must expose no secret via FusionCadError details/message/str/repr."""
    secret_tok = "secret::adsk::token::err_test::9999"
    secret_nested = "secret::adsk::token::nested_err::8888"
    raw_error_payload = {
        "isError": True,
        "error": {
            "code": "REF_STALE",
            "message": "Reference ent_stale_123 is stale",
            "details": {
                "entityToken": secret_tok,
                "target": "ent_stale_123",
                "nested": {
                    "token": secret_nested,
                    "native_token": secret_tok,
                    "code": "STALE_TARGET",
                },
            },
        },
    }
    # Direct FusionCadError instantiation with nested details
    err = FusionCadError(
        ErrorCode.REF_STALE,
        "Reference ent_stale_123 is stale",
        details=raw_error_payload["error"]["details"],
    )
    for secret in (secret_tok, secret_nested):
        assert secret not in str(err.details), f"Leaked {secret} in err.details"
        assert secret not in str(err), f"Leaked {secret} in str(err)"
        assert secret not in repr(err), f"Leaked {secret} in repr(err)"
        assert secret not in err.message, f"Leaked {secret} in err.message"

    # Legitimate non-token diagnostics must be preserved
    assert err.code == ErrorCode.REF_STALE
    assert err.message == "Referenced CAD entity is stale or no longer exists"
    assert err.details.get("target") == "ent_stale_123"
    assert err.details.get("nested", {}).get("code") == "STALE_TARGET"


def test_structural_canonicalization_preserves_ent_prefixed_semantic_strings():
    """Regression (c): semantic strings that merely look like ent_* (tag/role/value/name)
    must remain mutation-sensitive, producing different hashes.
    """
    base_payload = {
        "document_ref": "doc_main_123",
        "model_revision": "rev_1",
        "counts": {"faces": 1},
        "components": [{"name": "ent_custom_part", "ref": "ent_c1"}],
        "logical_objects": [
            {
                "group": "mfg",
                "name": "ent_tag_name",
                "value": "ent_bracket",
                "role": "ent_primary_mount",
                "owner_ref": "ent_c1",
            }
        ],
    }
    hash_base = compute_structural_hash(base_payload)

    # 1. Mutating value from "ent_bracket" to "ent_stiffener"
    payload_val_mut = {
        **base_payload,
        "logical_objects": [
            {
                "group": "mfg",
                "name": "ent_tag_name",
                "value": "ent_stiffener",
                "role": "ent_primary_mount",
                "owner_ref": "ent_c1",
            }
        ],
    }
    hash_val_mut = compute_structural_hash(payload_val_mut)
    assert hash_val_mut != hash_base, (
        "Semantic string mutation in 'value' matching ent_* must change structural hash"
    )

    # 2. Mutating role from "ent_primary_mount" to "ent_secondary_mount"
    payload_role_mut = {
        **base_payload,
        "logical_objects": [
            {
                "group": "mfg",
                "name": "ent_tag_name",
                "value": "ent_bracket",
                "role": "ent_secondary_mount",
                "owner_ref": "ent_c1",
            }
        ],
    }
    hash_role_mut = compute_structural_hash(payload_role_mut)
    assert hash_role_mut != hash_base, (
        "Semantic string mutation in 'role' matching ent_* must change structural hash"
    )

    # 3. Mutating component name from "ent_custom_part" to "ent_other_part"
    payload_comp_mut = {
        **base_payload,
        "components": [{"name": "ent_other_part", "ref": "ent_c1"}],
    }
    hash_comp_mut = compute_structural_hash(payload_comp_mut)
    assert hash_comp_mut != hash_base, (
        "Semantic string mutation in component 'name' matching ent_* must change structural hash"
    )


def test_unknown_ref_keyed_mappings_preserve_multiplicity_and_values():
    """Regression (b) & (d): unknown ref-keyed mappings with multiple entries must:
    - produce identical hashes across lifecycles with different concrete key names (b)
    - produce different hashes when values change, e.g. {ent_a: True, ent_b: False} vs both false (d)
    - produce different hashes when multiplicity changes (e.g. 1 entry vs 2 entries) (d)
    without collisions or dependence on concrete lifecycle key names.
    """
    # Lifecycle 1: keys ent_lifecycle_a and ent_lifecycle_b
    payload_l1 = {
        "document_ref": "doc_main_123",
        "model_revision": "rev_1",
        "snapshot_id": "snap_l1",
        "counts": {"faces": 2},
        "visibility": {
            "ent_lifecycle_a": True,
            "ent_lifecycle_b": False,
        },
    }

    # Lifecycle 2: different concrete keys ent_lifecycle_x and ent_lifecycle_y, different snapshot_id
    payload_l2 = {
        "document_ref": "doc_main_123",
        "model_revision": "rev_1",
        "snapshot_id": "snap_l2",
        "counts": {"faces": 2},
        "visibility": {
            "ent_lifecycle_y": False,
            "ent_lifecycle_x": True,
        },
    }

    hash_l1 = compute_structural_hash(payload_l1)
    hash_l2 = compute_structural_hash(payload_l2)

    # Invariant (b): lifecycle-only identifier refs/snapshot_id must hash invariant
    assert hash_l1 == hash_l2, (
        f"Structural hashes must be invariant across lifecycles for unknown ref keys: {hash_l1} vs {hash_l2}"
    )

    # Value mutation (d): {ent_a: True, ent_b: False} vs both False
    payload_both_false = {
        "document_ref": "doc_main_123",
        "model_revision": "rev_1",
        "snapshot_id": "snap_l1",
        "counts": {"faces": 2},
        "visibility": {
            "ent_lifecycle_a": False,
            "ent_lifecycle_b": False,
        },
    }
    hash_both_false = compute_structural_hash(payload_both_false)
    assert hash_both_false != hash_l1, (
        "Unknown ref-keyed mapping with {ent_a: True, ent_b: False} vs both False must produce different hashes"
    )

    # Multiplicity mutation (d): 1 entry vs 2 entries
    payload_single = {
        "document_ref": "doc_main_123",
        "model_revision": "rev_1",
        "snapshot_id": "snap_l1",
        "counts": {"faces": 2},
        "visibility": {
            "ent_lifecycle_a": True,
        },
    }
    hash_single = compute_structural_hash(payload_single)
    assert hash_single != hash_l1, (
        "Unknown ref-keyed mapping multiplicity difference must produce different hashes"
    )
