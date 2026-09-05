from __future__ import annotations

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.revisions import (
    RevisionRecord,
    RevisionTracker,
    canonicalize_fingerprint_payload,
    compute_model_fingerprint,
)


def test_canonicalize_fingerprint_payload_structure():
    raw = {"parameters": [{"name": "p1", "value": 5.0, "expression": "5 mm"}], "document_ref": "doc_1"}
    canonical = canonicalize_fingerprint_payload(raw)
    assert "document" in canonical
    assert canonical["document"]["document_ref"] == "doc_1"
    assert "parameters" in canonical


def test_manual_fingerprint_change_advances_revision():
    tracker = RevisionTracker()
    first = tracker.observe("doc_1", "hash-A")
    assert isinstance(first, RevisionRecord)
    second = tracker.observe("doc_1", "hash-B")
    assert second.sequence == first.sequence + 1
    assert first.revision == "rev_1"
    assert second.revision == "rev_2"
    assert second.model_revision == "rev_2"


def test_stale_expected_revision_blocks_before_executor_call():
    tracker = RevisionTracker()
    tracker.observe("doc_1", "hash-A")
    tracker.observe("doc_1", "hash-B")
    with pytest.raises(BridgeError) as exc:
        tracker.assert_expected("doc_1", "rev_1")
    assert exc.value.code == ErrorCode.REVISION_CONFLICT
    assert isinstance(exc.value, FusionCadError)
    assert exc.value.details.get("expected_revision") == "rev_1"
    assert exc.value.details.get("current_revision") == "rev_2"


def test_same_fingerprint_is_stable():
    tracker = RevisionTracker()
    first = tracker.observe("doc_1", "hash-A")
    second = tracker.observe("doc_1", "hash-A")
    assert first is second
    assert second.sequence == 1
    assert second.revision == "rev_1"


def test_current_returns_active_or_specified_document():
    tracker = RevisionTracker()
    assert tracker.current() is None
    assert tracker.current("doc_1") is None

    rec1 = tracker.observe("doc_1", "hash-1")
    assert tracker.current() == rec1
    assert tracker.current("doc_1") == rec1

    rec2 = tracker.observe("doc_2", "hash-2")
    assert tracker.current() == rec2
    assert tracker.current("doc_2") == rec2
    assert tracker.current("doc_1") == rec1


def test_assert_expected_matches_and_fails_appropriately():
    tracker = RevisionTracker()
    tracker.observe("doc_1", "hash-1")

    # Matching revision succeeds and returns record
    rec = tracker.assert_expected("doc_1", "rev_1")
    assert rec.revision == "rev_1"

    # Mismatched revision fails
    with pytest.raises(FusionCadError) as exc_mismatch:
        tracker.assert_expected("doc_1", "rev_999")
    assert exc_mismatch.value.code == ErrorCode.REVISION_CONFLICT

    # Unobserved document fails with REVISION_CONFLICT
    with pytest.raises(FusionCadError) as exc_unobserved:
        tracker.assert_expected("doc_unknown", "rev_1")
    assert exc_unobserved.value.code == ErrorCode.REVISION_CONFLICT

    # None expected_revision requires revision by default
    with pytest.raises(FusionCadError) as exc_none:
        tracker.assert_expected("doc_1", None)
    assert exc_none.value.code == ErrorCode.REVISION_CONFLICT

    # Empty document_ref is invalid
    with pytest.raises(FusionCadError) as exc_empty:
        tracker.assert_expected("", "rev_1")
    assert exc_empty.value.code == ErrorCode.INVALID_ARGUMENT


def test_falsification_deterministic_canonicalization_and_ordering():
    # Construct two payloads with keys, timeline items, parameters, and bodies in different order
    payload_a = {
        "parameters": [
            {"name": "length", "expression": "100 mm", "value": 100.0, "unit": "mm"},
            {"name": "width", "expression": "50 mm", "value": 50.0, "unit": "mm"},
        ],
        "document": {
            "document_ref": "doc_1",
            "name": "Box",
            "is_modified": False,
            "saved_version": 1,
        },
        "timeline": [
            {"index": 2, "id": "feat_extrude", "name": "Extrude1", "is_suppressed": False},
            {"index": 1, "id": "feat_sketch", "name": "Sketch1", "is_suppressed": False},
        ],
        "attributes": {
            "version": "1.0",
            "author": "agent",
        },
        "bodies": [
            {"name": "Body2", "volume": 12.345678, "area": 5.0, "faces_count": 6, "edges_count": 12},
            {"name": "Body1", "volume": 10.0, "area": 4.0, "faces_count": 6, "edges_count": 12},
        ],
        "visibility": {"Body1": True, "Body2": False},
    }

    payload_b = {
        "visibility": {"Body2": False, "Body1": True},
        "attributes": [
            {"group": "bridge.cad/v1", "name": "author", "value": "agent"},
            {"group": "bridge.cad/v1", "name": "version", "value": "1.0"},
        ],
        "bodies": [
            {"name": "Body1", "volume": 10.0, "area": 4.0, "faces_count": 6, "edges_count": 12},
            {"name": "Body2", "volume": 12.345678, "area": 5.0, "faces_count": 6, "edges_count": 12},
        ],
        "timeline": [
            {"index": 1, "id": "feat_sketch", "name": "Sketch1", "is_suppressed": False},
            {"index": 2, "id": "feat_extrude", "name": "Extrude1", "is_suppressed": False},
        ],
        "document": {
            "name": "Box",
            "saved_version": 1,
            "is_modified": False,
            "document_ref": "doc_1",
        },
        "parameters": [
            {"name": "width", "expression": "50 mm", "value": 50.0, "unit": "mm"},
            {"name": "length", "expression": "100 mm", "value": 100.0, "unit": "mm"},
        ],
    }

    hash_a = compute_model_fingerprint(payload_a)
    hash_b = compute_model_fingerprint(payload_b)
    assert hash_a == hash_b
    assert len(hash_a) == 64


def test_falsification_semantic_mutation_alters_fingerprint():
    base_payload = {
        "document": {"document_ref": "doc_1", "name": "Part", "is_modified": False},
        "timeline": [{"index": 1, "id": "feat_1", "name": "Sketch", "is_suppressed": False}],
        "parameters": [{"name": "radius", "expression": "10 mm", "value": 10.0, "unit": "mm"}],
        "bodies": [{"name": "Body1", "volume": 50.0, "is_visible": True}],
        "attributes": {"role": "base"},
    }
    base_hash = compute_model_fingerprint(base_payload)

    # 1. Timeline suppression change
    mutated_timeline = dict(base_payload)
    mutated_timeline["timeline"] = [{"index": 1, "id": "feat_1", "name": "Sketch", "is_suppressed": True}]
    assert compute_model_fingerprint(mutated_timeline) != base_hash

    # 2. Parameter change
    mutated_param = dict(base_payload)
    mutated_param["parameters"] = [{"name": "radius", "expression": "15 mm", "value": 15.0, "unit": "mm"}]
    assert compute_model_fingerprint(mutated_param) != base_hash

    # 3. Geometry change (volume)
    mutated_geom = dict(base_payload)
    mutated_geom["bodies"] = [{"name": "Body1", "volume": 50.5, "is_visible": True}]
    assert compute_model_fingerprint(mutated_geom) != base_hash

    # 4. Bridge attribute change
    mutated_attr = dict(base_payload)
    mutated_attr["attributes"] = {"role": "flange"}
    assert compute_model_fingerprint(mutated_attr) != base_hash

    # 5. Document modified marker
    mutated_doc = dict(base_payload)
    mutated_doc["document"] = {"document_ref": "doc_1", "name": "Part", "is_modified": True}
    assert compute_model_fingerprint(mutated_doc) != base_hash


def test_falsification_float_rounding_stability():
    # Floating point values with micro-precision differences within 6 decimals round stably
    p1 = {"parameters": [{"name": "d1", "value": 10.12345600001, "expression": "10.123456 mm"}]}
    p2 = {"parameters": [{"name": "d1", "value": 10.12345600004, "expression": "10.123456 mm"}]}
    assert compute_model_fingerprint(p1) == compute_model_fingerprint(p2)

    # Negative zero normalizes to positive zero
    p_neg_zero = {"parameters": [{"name": "d1", "value": -0.0, "expression": "0 mm"}]}
    p_pos_zero = {"parameters": [{"name": "d1", "value": 0.0, "expression": "0 mm"}]}
    assert compute_model_fingerprint(p_neg_zero) == compute_model_fingerprint(p_pos_zero)


def test_falsification_document_switch_close_reopen_lifecycle():
    tracker = RevisionTracker()

    # Observe doc_1
    rec1_v1 = tracker.observe("doc_1", "hash-doc1-v1")
    assert rec1_v1.revision == "rev_1"
    assert tracker.active_document_ref == "doc_1"

    # Switch to doc_2
    rec2_v1 = tracker.observe("doc_2", "hash-doc2-v1")
    assert rec2_v1.revision == "rev_1"
    assert tracker.active_document_ref == "doc_2"
    assert tracker.current() == rec2_v1
    assert tracker.current("doc_1") == rec1_v1

    # Switch back to doc_1 without changes -> stable
    rec1_check = tracker.observe("doc_1", "hash-doc1-v1")
    assert rec1_check.sequence == 1
    assert rec1_check.revision == "rev_1"
    assert tracker.active_document_ref == "doc_1"

    # Close doc_1
    tracker.close_document("doc_1")
    assert tracker.active_document_ref is None

    # Reopen doc_1 unchanged -> same revision rev_1
    rec1_reopen_same = tracker.observe("doc_1", "hash-doc1-v1")
    assert rec1_reopen_same.sequence == 1
    assert rec1_reopen_same.revision == "rev_1"

    # External change happens to doc_1 while reopened
    rec1_v2 = tracker.observe("doc_1", "hash-doc1-v2")
    assert rec1_v2.sequence == 2
    assert rec1_v2.revision == "rev_2"

    # doc_2 was unaffected by changes to doc_1
    assert tracker.current("doc_2").sequence == 1
    assert tracker.current("doc_2").revision == "rev_1"


def test_get_fingerprint_history_and_lookup():
    tracker = RevisionTracker()
    tracker.observe("doc_1", "hash-A")
    tracker.observe("doc_1", "hash-B")
    tracker.observe("doc_1", "hash-C")

    assert tracker.get_fingerprint("doc_1") == "hash-C"
    assert tracker.get_fingerprint("doc_1", "rev_1") == "hash-A"
    assert tracker.get_fingerprint("doc_1", "rev_2") == "hash-B"
    assert tracker.get_fingerprint("doc_1", "rev_3") == "hash-C"
    assert tracker.get_fingerprint("doc_1", "rev_99") is None
    assert tracker.get_fingerprint("doc_unknown") is None


def test_reset_behavior():
    tracker = RevisionTracker()
    tracker.observe("doc_1", "hash-1")
    tracker.observe("doc_2", "hash-2")

    # Reset single document
    tracker.reset("doc_1")
    assert tracker.current("doc_1") is None
    assert tracker.current("doc_2") is not None

    # Reset all
    tracker.reset()
    assert tracker.current() is None
    assert tracker.current("doc_2") is None


def test_exact_prefix_handling_does_not_corrupt_names():
    # If lstrip("doc_") was used, "doc_document1" would become "doc_ument1"
    # Exact prefix removal preserves the underlying name "document1"
    raw1 = {"document": {"document_ref": "doc_document1"}}
    canon1 = canonicalize_fingerprint_payload(raw1)
    assert canon1["document"]["document_ref"] == "doc_document1"

    raw2 = {"document_ref": "document1"}
    canon2 = canonicalize_fingerprint_payload(raw2)
    assert canon2["document"]["document_ref"] == "doc_document1"


def test_effective_visibility_changes_fingerprint():
    base = {
        "document_ref": "doc_1",
        "bodies": [{"name": "Body1", "is_visible": True, "effective_visibility": True}],
    }
    hidden_parent = {
        "document_ref": "doc_1",
        "bodies": [{"name": "Body1", "is_visible": True, "effective_visibility": False}],
    }
    fp1 = compute_model_fingerprint(base)
    fp2 = compute_model_fingerprint(hidden_parent)
    assert fp1 != fp2


def test_sketch_constraints_and_dimensions_change_fingerprint():
    sketch_plain = {
        "document_ref": "doc_1",
        "sketches": [{"name": "Sketch1", "constraints": [], "dimensions": []}],
    }
    sketch_constrained = {
        "document_ref": "doc_1",
        "sketches": [{
            "name": "Sketch1",
            "constraints": [{"type": "ParallelConstraint", "is_deletable": True}],
            "dimensions": [],
        }],
    }
    sketch_dimensioned = {
        "document_ref": "doc_1",
        "sketches": [{
            "name": "Sketch1",
            "constraints": [],
            "dimensions": [{"name": "d1", "value": 25.4, "expression": "1 in"}],
        }],
    }

    fp_plain = compute_model_fingerprint(sketch_plain)
    fp_cons = compute_model_fingerprint(sketch_constrained)
    fp_dim = compute_model_fingerprint(sketch_dimensioned)

    assert fp_plain != fp_cons
    assert fp_plain != fp_dim
    assert fp_cons != fp_dim


def test_falsify_attribute_owner_relocation_changes_fingerprint():
    """Proves that relocating Bridge attributes between different mutation-sensitive owners changes fingerprint."""
    owners = [
        ("document", "doc_1"),
        ("component", "comp_root"),
        ("occurrence", "root:occ_1"),
        ("body", "comp_root:Body1"),
        ("body", "comp_root:Body2"),
        ("sketch", "comp_root:Sketch1"),
        ("timeline", "feat_extrude_1"),
        ("feature", "feat_extrude_1"),
    ]
    fingerprints = set()

    for owner_type, owner_id in owners:
        payload = {
            "document_ref": "doc_1",
            "attributes": [
                {
                    "owner_type": owner_type,
                    "owner_id": owner_id,
                    "group": "bridge.cad/v1",
                    "name": "tag",
                    "value": "v1",
                }
            ],
        }
        fp = compute_model_fingerprint(payload)
        fingerprints.add(fp)

    # Every owner location must produce a distinct fingerprint
    assert len(fingerprints) == len(owners)


def test_falsify_begin_transaction_fails_closed_on_empty_fingerprint_or_unobserved_doc():
    """Proves begin_transaction fails closed on empty fingerprint, empty string, or unobserved document."""
    tracker = RevisionTracker()

    # Case A: unobserved document and no revision provided fails closed (no rev_1 fallback)
    with pytest.raises(FusionCadError) as exc_unobs:
        tracker.begin_transaction("tx_1", "doc_unobserved", baseline_fingerprint="some-fp")
    assert exc_unobs.value.code == ErrorCode.NO_ACTIVE_DESIGN

    # Case B: observed document but empty string fingerprint fails closed (no empty fingerprint)
    tracker.observe("doc_1", "valid-seed-fp")
    with pytest.raises(FusionCadError) as exc_empty_fp:
        tracker.begin_transaction("tx_1", "doc_1", baseline_revision="rev_1", baseline_fingerprint="")
    assert exc_empty_fp.value.code == ErrorCode.INVALID_ARGUMENT
    assert "cannot be empty" in exc_empty_fp.value.message

    # Case C: whitespace-only fingerprint fails closed
    with pytest.raises(FusionCadError) as exc_ws:
        tracker.begin_transaction("tx_1", "doc_1", baseline_revision="rev_1", baseline_fingerprint="   ")
    assert exc_ws.value.code == ErrorCode.INVALID_ARGUMENT

    # Case D: None fingerprint when document has no current fingerprint fails closed
    tracker_empty = RevisionTracker()
    with pytest.raises(FusionCadError) as exc_no_fp:
        tracker_empty.begin_transaction("tx_1", "doc_empty", baseline_revision="rev_1", baseline_fingerprint=None)
    assert exc_no_fp.value.code == ErrorCode.INVALID_ARGUMENT

    # Case E: Valid observed document and non-empty fingerprint succeeds
    bl = tracker.begin_transaction("tx_valid", "doc_1")
    assert bl["transaction_id"] == "tx_valid"
    assert bl["baseline_revision"] == "rev_1"
    assert bl["baseline_fingerprint"] == "valid-seed-fp"


def test_falsify_moving_sketch_geometry_at_equal_counts_changes_fingerprint():
    """Proves moving sketch geometry (curves or points) changes fingerprint even when counts and constraints are unchanged."""
    sketch_base = {
        "document_ref": "doc_1",
        "sketches": [
            {
                "name": "Sketch1",
                "component": "Root",
                "profiles_count": 1,
                "curves_count": 4,
                "constraints_count": 1,
                "constraints": [{"type": "HorizontalConstraint", "is_deletable": True}],
                "dimensions_count": 1,
                "dimensions": [{"name": "d1", "value": 10.0, "expression": "10 mm"}],
                "curves": [
                    {"type": "SketchLine", "length": 10.0, "start_point": [0.0, 0.0, 0.0], "end_point": [10.0, 0.0, 0.0]},
                    {"type": "SketchLine", "length": 10.0, "start_point": [10.0, 0.0, 0.0], "end_point": [10.0, 10.0, 0.0]},
                    {"type": "SketchLine", "length": 10.0, "start_point": [10.0, 10.0, 0.0], "end_point": [0.0, 10.0, 0.0]},
                    {"type": "SketchLine", "length": 10.0, "start_point": [0.0, 10.0, 0.0], "end_point": [0.0, 0.0, 0.0]},
                ],
                "points": [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 10.0, 0.0], [0.0, 10.0, 0.0]],
                "bounding_box": {"min": [0.0, 0.0, 0.0], "max": [10.0, 10.0, 0.0]},
            }
        ],
    }

    # Shifted geometry: exact same counts (profiles_count=1, curves_count=4, constraints_count=1, dimensions_count=1)
    sketch_moved = {
        "document_ref": "doc_1",
        "sketches": [
            {
                "name": "Sketch1",
                "component": "Root",
                "profiles_count": 1,
                "curves_count": 4,
                "constraints_count": 1,
                "constraints": [{"type": "HorizontalConstraint", "is_deletable": True}],
                "dimensions_count": 1,
                "dimensions": [{"name": "d1", "value": 10.0, "expression": "10 mm"}],
                "curves": [
                    {"type": "SketchLine", "length": 10.0, "start_point": [5.0, 0.0, 0.0], "end_point": [15.0, 0.0, 0.0]},
                    {"type": "SketchLine", "length": 10.0, "start_point": [15.0, 0.0, 0.0], "end_point": [15.0, 10.0, 0.0]},
                    {"type": "SketchLine", "length": 10.0, "start_point": [15.0, 10.0, 0.0], "end_point": [5.0, 10.0, 0.0]},
                    {"type": "SketchLine", "length": 10.0, "start_point": [5.0, 10.0, 0.0], "end_point": [5.0, 0.0, 0.0]},
                ],
                "points": [[5.0, 0.0, 0.0], [15.0, 0.0, 0.0], [15.0, 10.0, 0.0], [5.0, 10.0, 0.0]],
                "bounding_box": {"min": [5.0, 0.0, 0.0], "max": [15.0, 10.0, 0.0]},
            }
        ],
    }

    fp_base = compute_model_fingerprint(sketch_base)
    fp_moved = compute_model_fingerprint(sketch_moved)
    assert fp_base != fp_moved, "Moved sketch geometry with identical counts must produce distinct fingerprint"


def test_falsify_materially_different_body_geometry_with_same_coarse_aggregates_changes_fingerprint():
    """Proves materially different body geometry with identical coarse counts/area/volume/bbox produces distinct fingerprints."""
    base_body = {
        "document_ref": "doc_1",
        "bodies": [
            {
                "name": "Body1",
                "component": "Root",
                "is_solid": True,
                "is_visible": True,
                "volume": 100.0,
                "area": 50.0,
                "faces_count": 6,
                "edges_count": 12,
                "bounding_box": {"min": [0.0, 0.0, 0.0], "max": [10.0, 10.0, 10.0]},
                "center_of_mass": [5.0, 5.0, 4.0],
                "vertices": [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 10.0, 0.0], [0.0, 10.0, 0.0]],
                "faces": [
                    {"centroid": [5.0, 5.0, 0.0], "area": 100.0, "surface_type": "PlaneSurface"},
                    {"centroid": [5.0, 5.0, 10.0], "area": 100.0, "surface_type": "PlaneSurface"},
                ],
            }
        ],
    }

    # Materially different body geometry: exact same volume (100.0), area (50.0), faces_count (6), edges_count (12), bbox
    # but distinct center of mass, face centroids, and vertices
    different_body = {
        "document_ref": "doc_1",
        "bodies": [
            {
                "name": "Body1",
                "component": "Root",
                "is_solid": True,
                "is_visible": True,
                "volume": 100.0,
                "area": 50.0,
                "faces_count": 6,
                "edges_count": 12,
                "bounding_box": {"min": [0.0, 0.0, 0.0], "max": [10.0, 10.0, 10.0]},
                "center_of_mass": [5.0, 5.0, 6.0],
                "vertices": [[0.0, 0.0, 1.0], [10.0, 0.0, 1.0], [10.0, 10.0, 1.0], [0.0, 10.0, 1.0]],
                "faces": [
                    {"centroid": [5.0, 5.0, 1.0], "area": 100.0, "surface_type": "PlaneSurface"},
                    {"centroid": [5.0, 5.0, 9.0], "area": 100.0, "surface_type": "PlaneSurface"},
                ],
            }
        ],
    }

    fp_base = compute_model_fingerprint(base_body)
    fp_diff = compute_model_fingerprint(different_body)
    assert fp_base != fp_diff, "Bodies with identical volume/area/bbox/counts but different internal geometry must have distinct fingerprints"


def test_falsify_attribute_owner_empty_id_or_whitespace_fails_closed():
    """Proves attribute collections with empty or whitespace owner_id fail closed."""
    # Empty string owner_id
    with pytest.raises(FusionCadError) as exc_empty:
        compute_model_fingerprint({
            "document_ref": "doc_1",
            "attributes": [{"owner_type": "body", "owner_id": "", "group": "bridge.cad/v1", "name": "tag", "value": "v"}],
        })
    assert exc_empty.value.code == ErrorCode.INVALID_ARGUMENT
    assert "lacks stable owner_id" in exc_empty.value.message

    # Whitespace-only owner_id
    with pytest.raises(FusionCadError) as exc_ws:
        compute_model_fingerprint({
            "document_ref": "doc_1",
            "attributes": [{"owner_type": "body", "owner_id": "   ", "group": "bridge.cad/v1", "name": "tag", "value": "v"}],
        })
    assert exc_ws.value.code == ErrorCode.INVALID_ARGUMENT
    assert "lacks stable owner_id" in exc_ws.value.message

    # Face and edge empty owner_id
    for owner_t in ("face", "edge", "sketch_curve", "sketch_point"):
        with pytest.raises(FusionCadError) as exc_owner:
            compute_model_fingerprint({
                "document_ref": "doc_1",
                "attributes": [{"owner_type": owner_t, "owner_id": " ", "group": "bridge.cad/v1", "name": "tag", "value": "v"}],
            })
        assert exc_owner.value.code == ErrorCode.INVALID_ARGUMENT


def test_falsify_attribute_relocation_across_all_eleven_mutation_sensitive_owners():
    """Proves relocating identical attributes across all 11 owners produces distinct fingerprints."""
    owners = [
        ("document", "doc_1"),
        ("component", "comp_root"),
        ("occurrence", "root:occ_1"),
        ("body", "comp_root:Body1"),
        ("face", "comp_root:Body1:face_0"),
        ("edge", "comp_root:Body1:edge_0"),
        ("sketch", "comp_root:Sketch1"),
        ("sketch_curve", "comp_root:Sketch1:curve_0"),
        ("sketch_point", "comp_root:Sketch1:point_0"),
        ("timeline", "feat_extrude_1"),
        ("feature", "feat_extrude_1"),
    ]
    fingerprints = set()

    for owner_type, owner_id in owners:
        payload = {
            "document_ref": "doc_1",
            "attributes": [
                {
                    "owner_type": owner_type,
                    "owner_id": owner_id,
                    "group": "bridge.cad/v1",
                    "name": "status",
                    "value": "locked",
                }
            ],
        }
        fp = compute_model_fingerprint(payload)
        fingerprints.add(fp)

    assert len(fingerprints) == len(owners), f"Expected 11 distinct fingerprints for 11 owner types, got {len(fingerprints)}"


def test_falsify_face_and_edge_internal_geometry_changes_preserve_coarse_aggregates():
    """Proves altering face centroids, surface types, or edge lengths/curves alters fingerprint even when counts/volume/area/bbox are unchanged."""
    base_body = {
        "document_ref": "doc_1",
        "bodies": [
            {
                "name": "Body1",
                "component": "Root",
                "is_solid": True,
                "is_visible": True,
                "volume": 1000.0,
                "area": 600.0,
                "faces_count": 2,
                "edges_count": 2,
                "bounding_box": {"min": [0.0, 0.0, 0.0], "max": [10.0, 10.0, 10.0]},
                "faces": [
                    {"centroid": [5.0, 5.0, 0.0], "area": 300.0, "surface_type": "PlaneSurface"},
                    {"centroid": [5.0, 5.0, 10.0], "area": 300.0, "surface_type": "PlaneSurface"},
                ],
                "edges": [
                    {"length": 10.0, "curve_type": "Line3D"},
                    {"length": 10.0, "curve_type": "Line3D"},
                ],
            }
        ],
    }
    fp_base = compute_model_fingerprint(base_body)

    # 1. Face centroid shift while volume, area, bbox, counts remain identical
    shifted_faces = {
        "document_ref": "doc_1",
        "bodies": [
            {
                "name": "Body1",
                "component": "Root",
                "is_solid": True,
                "is_visible": True,
                "volume": 1000.0,
                "area": 600.0,
                "faces_count": 2,
                "edges_count": 2,
                "bounding_box": {"min": [0.0, 0.0, 0.0], "max": [10.0, 10.0, 10.0]},
                "faces": [
                    {"centroid": [4.0, 5.0, 0.0], "area": 300.0, "surface_type": "PlaneSurface"},
                    {"centroid": [6.0, 5.0, 10.0], "area": 300.0, "surface_type": "PlaneSurface"},
                ],
                "edges": [
                    {"length": 10.0, "curve_type": "Line3D"},
                    {"length": 10.0, "curve_type": "Line3D"},
                ],
            }
        ],
    }
    assert compute_model_fingerprint(shifted_faces) != fp_base

    # 2. Surface type change while volume, area, bbox, counts remain identical
    surface_type_change = {
        "document_ref": "doc_1",
        "bodies": [
            {
                "name": "Body1",
                "component": "Root",
                "is_solid": True,
                "is_visible": True,
                "volume": 1000.0,
                "area": 600.0,
                "faces_count": 2,
                "edges_count": 2,
                "bounding_box": {"min": [0.0, 0.0, 0.0], "max": [10.0, 10.0, 10.0]},
                "faces": [
                    {"centroid": [5.0, 5.0, 0.0], "area": 300.0, "surface_type": "CylinderSurface"},
                    {"centroid": [5.0, 5.0, 10.0], "area": 300.0, "surface_type": "PlaneSurface"},
                ],
                "edges": [
                    {"length": 10.0, "curve_type": "Line3D"},
                    {"length": 10.0, "curve_type": "Line3D"},
                ],
            }
        ],
    }
    assert compute_model_fingerprint(surface_type_change) != fp_base

    # 3. Edge curve type change while volume, area, bbox, counts remain identical
    edge_type_change = {
        "document_ref": "doc_1",
        "bodies": [
            {
                "name": "Body1",
                "component": "Root",
                "is_solid": True,
                "is_visible": True,
                "volume": 1000.0,
                "area": 600.0,
                "faces_count": 2,
                "edges_count": 2,
                "bounding_box": {"min": [0.0, 0.0, 0.0], "max": [10.0, 10.0, 10.0]},
                "faces": [
                    {"centroid": [5.0, 5.0, 0.0], "area": 300.0, "surface_type": "PlaneSurface"},
                    {"centroid": [5.0, 5.0, 10.0], "area": 300.0, "surface_type": "PlaneSurface"},
                ],
                "edges": [
                    {"length": 10.0, "curve_type": "Circle3D"},
                    {"length": 10.0, "curve_type": "Line3D"},
                ],
            }
        ],
    }
    assert compute_model_fingerprint(edge_type_change) != fp_base


def test_falsify_mock_model_state_rejected_by_rendered_production_script():
    """Proves common.py.txt does not recognize mock_model_state and fails closed without active Fusion context."""
    from app.fusion_cad.scripts import FusionCadScriptBundle
    bundle = FusionCadScriptBundle()
    script = bundle.build("read", {
        "operation": "model_snapshot",
        "mock_model_state": {
            "document": {"document_ref": "doc_forged"},
            "bodies": [],
        },
    })
    scope = {"__name__": "__main__"}
    exec(compile(script, "<rendered-test-script>", "exec"), scope)  # noqa: S102
    out = scope["_output"]
    # Because mock_model_state is removed from common.py.txt, it MUST NOT return synthetic doc_forged!
    # Instead it attempts real Application.get() and fails with NO_ACTIVE_DESIGN or FUSION_API_ERROR
    assert out["status"] == "failed"
    assert out["error"]["code"] in ("NO_ACTIVE_DESIGN", "FUSION_API_ERROR")
    assert out.get("data", {}).get("document_ref") != "doc_forged"


def test_falsify_face_edge_and_sketch_topology_and_parameter_signatures():
    """Proves that face/edge/sketch curve topology and parameters distinguish states preserving coarse aggregates."""
    import json

    base_state = {
        "document_ref": "doc_1",
        "bodies": [
            {
                "name": "Body1",
                "component": "Root",
                "is_solid": True,
                "is_visible": True,
                "volume": 1000.0,
                "area": 600.0,
                "faces_count": 1,
                "edges_count": 1,
                "bounding_box": {"min": [0.0, 0.0, 0.0], "max": [10.0, 10.0, 10.0]},
                "faces": [
                    {
                        "centroid": [5.0, 5.0, 0.0],
                        "area": 300.0,
                        "surface_type": "PlaneSurface",
                        "normal": [0.0, 0.0, 1.0],
                        "loops_count": 1,
                        "loops": [{"is_outer": True, "edges_count": 4}],
                        "edges_count": 4,
                        "vertices_count": 4,
                        "is_param_reversed": False,
                        "bounding_box": {"min": [0.0, 0.0, 0.0], "max": [10.0, 10.0, 0.0]},
                    }
                ],
                "edges": [
                    {
                        "length": 10.0,
                        "curve_type": "Line3D",
                        "faces_count": 2,
                        "start_vertex": [0.0, 0.0, 0.0],
                        "end_vertex": [10.0, 0.0, 0.0],
                        "is_degenerate": False,
                        "is_param_reversed": False,
                        "bounding_box": {"min": [0.0, 0.0, 0.0], "max": [10.0, 0.0, 0.0]},
                    }
                ],
            }
        ],
        "sketches": [
            {
                "name": "Sketch1",
                "component": "Root",
                "is_visible": True,
                "curves_count": 1,
                "curves": [
                    {
                        "type": "SketchLine",
                        "length": 10.0,
                        "start_point": [0.0, 0.0, 0.0],
                        "end_point": [10.0, 0.0, 0.0],
                        "start_sketch_point": [0.0, 0.0, 0.0],
                        "end_sketch_point": [10.0, 0.0, 0.0],
                        "is_construction": False,
                        "is_fixed": False,
                        "bounding_box": {"min": [0.0, 0.0, 0.0], "max": [10.0, 0.0, 0.0]},
                    }
                ],
            }
        ],
    }
    fp_base = compute_model_fingerprint(base_state)

    # 1. Inverted face normal
    inverted_normal = json.loads(json.dumps(base_state))
    inverted_normal["bodies"][0]["faces"][0]["normal"] = [0.0, 0.0, -1.0]
    assert compute_model_fingerprint(inverted_normal) != fp_base

    # 2. Face loop topology (e.g. inner hole added)
    hole_loop = json.loads(json.dumps(base_state))
    hole_loop["bodies"][0]["faces"][0]["loops_count"] = 2
    hole_loop["bodies"][0]["faces"][0]["loops"].append({"is_outer": False, "edges_count": 4})
    assert compute_model_fingerprint(hole_loop) != fp_base

    # 3. Face is_param_reversed toggle
    param_reversed = json.loads(json.dumps(base_state))
    param_reversed["bodies"][0]["faces"][0]["is_param_reversed"] = True
    assert compute_model_fingerprint(param_reversed) != fp_base

    # 4. Face bounding box change
    face_bbox_change = json.loads(json.dumps(base_state))
    face_bbox_change["bodies"][0]["faces"][0]["bounding_box"]["max"] = [10.0, 10.0, 1.0]
    assert compute_model_fingerprint(face_bbox_change) != fp_base

    # 5. Edge vertex connectivity change
    edge_vert_change = json.loads(json.dumps(base_state))
    edge_vert_change["bodies"][0]["edges"][0]["start_vertex"] = [0.0, 1.0, 0.0]
    assert compute_model_fingerprint(edge_vert_change) != fp_base

    # 6. Edge faces_count change (e.g. boundary edge vs manifold edge)
    edge_faces_change = json.loads(json.dumps(base_state))
    edge_faces_change["bodies"][0]["edges"][0]["faces_count"] = 1
    assert compute_model_fingerprint(edge_faces_change) != fp_base

    # 7. Edge bounding box change
    edge_bbox_change = json.loads(json.dumps(base_state))
    edge_bbox_change["bodies"][0]["edges"][0]["bounding_box"]["max"] = [10.0, 1.0, 0.0]
    assert compute_model_fingerprint(edge_bbox_change) != fp_base

    # 8. Sketch curve sketch point connectivity change
    sketch_pt_change = json.loads(json.dumps(base_state))
    sketch_pt_change["sketches"][0]["curves"][0]["start_sketch_point"] = [0.0, 2.0, 0.0]
    assert compute_model_fingerprint(sketch_pt_change) != fp_base

    # 9. Sketch curve is_construction toggle
    sketch_construction = json.loads(json.dumps(base_state))
    sketch_construction["sketches"][0]["curves"][0]["is_construction"] = True
    assert compute_model_fingerprint(sketch_construction) != fp_base

    # 10. Sketch curve is_fixed toggle
    sketch_fixed = json.loads(json.dumps(base_state))
    sketch_fixed["sketches"][0]["curves"][0]["is_fixed"] = True
    assert compute_model_fingerprint(sketch_fixed) != fp_base
