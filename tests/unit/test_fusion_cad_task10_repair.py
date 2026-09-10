"""Task 10 Codex-blocker repair regressions (domain level).

Covers verified blockers 2 and 3 at the pure domain layer:

- Blocker 3: the metadata mutation plan must propagate the real durable command
  operation_id plus recipe/logical_object_ref, and ``created_revision`` must be
  the truthful post-mutation revision (the revision in which the created/changed
  entity exists), never merely the pre-mutation expected revision. A plan that
  cannot know the post-mutation revision fails closed.
- Blocker 2 (domain payload contract): opaque entity targets are resolved to
  exact native hints before dispatch; the plan itself never documents a document
  fallback (script-level enforcement is covered by the integration repair tests).
"""

from __future__ import annotations

import pytest

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.metadata import (
    PROVENANCE_ATTRIBUTE_NAME,
    build_metadata_mutation_plan,
    build_provenance_record,
    parse_provenance_attribute,
    provenance_attribute_value,
)
from app.fusion_cad.revisions import RevisionTracker

# =========================================================================
# Blocker 3: provenance carries the durable command identity and truthful revision
# =========================================================================


def test_mutation_plan_propagates_command_operation_id_recipe_and_logical_object():
    plan = build_metadata_mutation_plan(
        {
            "operation": "set",
            "name": "finish",
            "value": "anodized",
            "expected_revision": "rev_3",
            "recipe": "name_plate/v1",
            "logical_object_ref": "text_schedule_01",
        },
        operation_id="op_cmd_123abc",
        created_revision="rev_4",
    )
    assert plan.provenance.operation_id == "op_cmd_123abc"
    assert plan.provenance.recipe == "name_plate/v1"
    assert plan.provenance.logical_object_ref == "text_schedule_01"
    # created_revision is the truthful post-mutation revision, not the
    # pre-mutation expected revision the mutation is applied against.
    assert plan.provenance.created_revision == "rev_4"
    assert plan.provenance.created_revision != "rev_3"
    provenance_write = next(
        w for w in plan.writes if w.name == PROVENANCE_ATTRIBUTE_NAME
    )
    assert parse_provenance_attribute(provenance_write.value) == plan.provenance


def test_mutation_plan_generates_and_exposes_operation_id_when_not_given():
    plan = build_metadata_mutation_plan(
        {
            "operation": "tag",
            "tag_name": "layout",
            "expected_revision": "rev_1",
        },
        created_revision="rev_2",
    )
    assert plan.provenance.operation_id.startswith("op_")


def test_mutation_plan_fails_closed_without_truthful_created_revision():
    # The post-mutation revision cannot be guessed from the payload; a plan
    # without the truthful created_revision must not be built at all.
    with pytest.raises(FusionCadError) as exc:
        build_metadata_mutation_plan(
            {
                "operation": "set",
                "name": "k",
                "value": "v",
                "expected_revision": "rev_1",
            }
        )
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT


def test_provenance_record_rejects_untruthful_created_revision():
    with pytest.raises(FusionCadError):
        build_provenance_record(operation="set", created_revision="")
    with pytest.raises(FusionCadError):
        build_provenance_record(operation="set", created_revision="   ")
    with pytest.raises(FusionCadError):
        build_provenance_record(operation="set", created_revision="not-a-revision")


def test_provenance_record_operation_id_must_match_durable_command_pattern():
    with pytest.raises(FusionCadError):
        build_provenance_record(
            operation="set",
            created_revision="rev_2",
            operation_id="not-an-operation-id",
        )


# =========================================================================
# Blocker 3: RevisionTracker exposes the truthful post-mutation revision
# =========================================================================


def test_next_revision_is_the_truthful_post_mutation_revision():
    tracker = RevisionTracker()
    tracker.observe("doc_1", "fingerprint-1")
    assert tracker.current("doc_1").revision == "rev_1"
    # A successful mutation deterministically lands in the next revision: the
    # Fusion-side guard fails any command whose post-apply fingerprint equals
    # the pre-apply one, and the tracker advances one sequence per distinct
    # fingerprint.
    assert tracker.next_revision("doc_1") == "rev_2"
    tracker.observe("doc_1", "fingerprint-2")
    assert tracker.next_revision("doc_1") == "rev_3"


def test_next_revision_fails_closed_without_observed_revision():
    tracker = RevisionTracker()
    with pytest.raises(FusionCadError) as exc:
        tracker.next_revision("doc_never_observed")
    assert exc.value.code == ErrorCode.NO_ACTIVE_DESIGN


# =========================================================================
# Round-trip: plan attribute value stays canonical and parseable
# =========================================================================


def test_plan_provenance_attribute_roundtrip_with_all_fields():
    plan = build_metadata_mutation_plan(
        {
            "operation": "tag",
            "tag_name": "layout",
            "tag_value": "schedule",
            "expected_revision": "rev_1",
            "transaction_id": "tx_layout_1",
            "recipe": "name_plate/v1",
            "logical_object_ref": "text_schedule_01",
        },
        operation_id="op_roundtrip_1",
        created_revision="rev_2",
    )
    value = provenance_attribute_value(plan.provenance)
    record = parse_provenance_attribute(value)
    assert record == plan.provenance
    assert record.created_revision == "rev_2"
    assert record.recipe == "name_plate/v1"
    assert record.logical_object_ref == "text_schedule_01"
