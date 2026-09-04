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
