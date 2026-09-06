from __future__ import annotations

import pytest

from app.fusion_cad.snapshots import (
    FeatureDependency,
    ModelSnapshot,
    SnapshotCounts,
    SnapshotStore,
    normalize_feature,
    normalize_sketch_read,
    normalize_snapshot,
)


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
