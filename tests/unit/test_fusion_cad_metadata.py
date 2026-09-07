from __future__ import annotations

import json

import pytest

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.metadata import (
    PROVENANCE_ATTRIBUTE_NAME,
    PROVENANCE_CREATOR_TOOL,
    RESERVED_METADATA_GROUP,
    ROLE_ATTRIBUTE_NAME,
    TAG_ATTRIBUTE_PREFIX,
    assert_reserved_metadata_group,
    build_metadata_mutation_plan,
    build_provenance_record,
    canonical_attribute_value,
    entity_metadata_view,
    parse_provenance_attribute,
    provenance_attribute_value,
    try_parse_provenance_attribute,
)
from app.fusion_cad.models import CreatedBySelector, EntitySelector, TagSelector
from app.fusion_cad.selectors import SelectorEngine

# =========================================================================
# Reserved metadata namespace: bridge.cad/v1
# =========================================================================


def test_reserved_metadata_namespace_is_bridge_cad_v1():
    assert RESERVED_METADATA_GROUP == "bridge.cad/v1"
    assert assert_reserved_metadata_group(None) == "bridge.cad/v1"
    assert assert_reserved_metadata_group("bridge.cad/v1") == "bridge.cad/v1"


@pytest.mark.parametrize("foreign_group", ["vendor.custom", "colors", "bridge.cad/v0"])
def test_foreign_attribute_groups_are_rejected_for_reads_and_writes(foreign_group):
    # Bridge reads/writes only its own reserved namespace keys; unrelated
    # Fusion attribute groups are preserved untouched, never surfaced.
    with pytest.raises(FusionCadError) as exc:
        assert_reserved_metadata_group(foreign_group)
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT


# =========================================================================
# Provenance payload
# =========================================================================


def test_provenance_record_contains_design_required_fields():
    record = build_provenance_record(
        operation="tag",
        expected_revision="rev_4",
        transaction_id="tx_layout_1",
        tag_name="layout",
        tag_value="schedule",
        recipe="name_plate/v1",
        logical_object_ref="text_schedule_01",
    )
    assert record.creator_tool == PROVENANCE_CREATOR_TOOL
    assert record.creator_operation == "fusion_metadata:tag"
    assert record.operation_id.startswith("op_")
    assert record.transaction_id == "tx_layout_1"
    assert record.recipe == "name_plate/v1"
    assert record.logical_object_ref == "text_schedule_01"
    # created_revision records the revision the mutation was applied against
    assert record.created_revision == "rev_4"
    assert [(t.name, t.value) for t in record.tags] == [("layout", "schedule")]


def test_provenance_record_accepts_explicit_operation_id():
    record = build_provenance_record(
        operation="set",
        expected_revision="rev_2",
        operation_id="op_explicit_1",
    )
    assert record.operation_id == "op_explicit_1"


def test_provenance_attribute_value_is_canonical_json_and_roundtrips():
    record = build_provenance_record(
        operation="set_role",
        expected_revision="rev_7",
        operation_id="op_role_1",
        role="mounting_bracket",
    )
    value = provenance_attribute_value(record)
    parsed = json.loads(value)
    # Canonical deterministic serialization: sorted keys, compact separators
    assert list(parsed.keys()) == sorted(parsed.keys())
    assert ", " not in value
    assert provenance_attribute_value(record) == value
    assert parse_provenance_attribute(value) == record


def test_malformed_persisted_provenance_fails_closed_without_echoing_value():
    raw = "secret-user-value not-json"
    with pytest.raises(FusionCadError) as exc:
        parse_provenance_attribute(raw)
    assert exc.value.code == ErrorCode.FUSION_API_ERROR
    assert raw not in exc.value.message
    assert raw not in str(exc.value.details)

    with pytest.raises(FusionCadError):
        parse_provenance_attribute('{"unexpected": true}')

    # Selector metadata views must never explode on malformed persisted data
    assert try_parse_provenance_attribute(raw) is None
    assert try_parse_provenance_attribute(None) is None


# =========================================================================
# Metadata mutation plan: one command carries metadata + provenance
# =========================================================================


def test_mutation_plan_always_includes_provenance_write():
    plan = build_metadata_mutation_plan(
        {
            "operation": "set",
            "target": "ent_body_1",
            "name": "finish",
            "value": "anodized",
            "expected_revision": "rev_3",
        }
    )
    names = [w.name for w in plan.writes]
    assert "finish" in names
    assert PROVENANCE_ATTRIBUTE_NAME in names
    provenance_write = next(w for w in plan.writes if w.name == PROVENANCE_ATTRIBUTE_NAME)
    assert parse_provenance_attribute(provenance_write.value) == plan.provenance
    assert plan.provenance.creator_operation == "fusion_metadata:set"
    assert plan.provenance.created_revision == "rev_3"
    assert plan.removals == ()


def test_mutation_plan_tag_untag_set_role_clear_role_and_remove():
    tag_plan = build_metadata_mutation_plan(
        {
            "operation": "tag",
            "tag_name": "layout",
            "tag_value": "schedule",
            "expected_revision": "rev_1",
        }
    )
    assert [(w.name, w.value) for w in tag_plan.writes if w.name != PROVENANCE_ATTRIBUTE_NAME] == [
        (f"{TAG_ATTRIBUTE_PREFIX}layout", "schedule")
    ]
    assert tag_plan.provenance.tags[0].name == "layout"

    untag_plan = build_metadata_mutation_plan(
        {
            "operation": "untag",
            "tag_name": "layout",
            "expected_revision": "rev_2",
        }
    )
    assert [r.name for r in untag_plan.removals] == [f"{TAG_ATTRIBUTE_PREFIX}layout"]
    assert untag_plan.writes[-1].name == PROVENANCE_ATTRIBUTE_NAME

    role_plan = build_metadata_mutation_plan(
        {
            "operation": "set_role",
            "role": "mounting_bracket",
            "expected_revision": "rev_3",
        }
    )
    assert [(w.name, w.value) for w in role_plan.writes if w.name != PROVENANCE_ATTRIBUTE_NAME] == [
        (ROLE_ATTRIBUTE_NAME, "mounting_bracket")
    ]
    assert role_plan.provenance.role == "mounting_bracket"

    # clear_role with an explicit role only removes the matching role value
    clear_filtered = build_metadata_mutation_plan(
        {
            "operation": "clear_role",
            "role": "decorative_text",
            "expected_revision": "rev_4",
        }
    )
    assert [(r.name, r.value) for r in clear_filtered.removals] == [
        (ROLE_ATTRIBUTE_NAME, "decorative_text")
    ]

    clear_any = build_metadata_mutation_plan(
        {"operation": "clear_role", "expected_revision": "rev_5"}
    )
    assert [(r.name, r.value) for r in clear_any.removals] == [(ROLE_ATTRIBUTE_NAME, None)]

    remove_plan = build_metadata_mutation_plan(
        {
            "operation": "remove",
            "name": "finish",
            "expected_revision": "rev_6",
        }
    )
    assert [r.name for r in remove_plan.removals] == ["finish"]
    assert remove_plan.writes[-1].name == PROVENANCE_ATTRIBUTE_NAME


def test_mutation_plan_rejects_foreign_group_and_missing_revision():
    with pytest.raises(FusionCadError) as exc_group:
        build_metadata_mutation_plan(
            {
                "operation": "set",
                "group": "vendor.custom",
                "name": "k",
                "value": "v",
                "expected_revision": "rev_1",
            }
        )
    assert exc_group.value.code == ErrorCode.INVALID_ARGUMENT

    with pytest.raises(FusionCadError) as exc_rev:
        build_metadata_mutation_plan(
            {"operation": "set", "name": "k", "value": "v"}
        )
    assert exc_rev.value.code == ErrorCode.INVALID_ARGUMENT


def test_canonical_attribute_value_serializes_structured_values_deterministically():
    assert canonical_attribute_value("plain") == "plain"
    structured = canonical_attribute_value({"b": 2, "a": [1, 2]})
    assert json.loads(structured) == {"b": 2, "a": [1, 2]}
    assert structured == json.dumps(
        {"b": 2, "a": [1, 2]}, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    with pytest.raises(FusionCadError) as exc:
        canonical_attribute_value(object())
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT


# =========================================================================
# Selector engine reads persisted model attributes (not Bridge memory)
# =========================================================================


def _persisted_attributes_entity() -> dict:
    """Entity carrying ONLY persisted model attribute records (no transient fields)."""
    provenance = build_provenance_record(
        operation="tag",
        expected_revision="rev_2",
        operation_id="op_prov_1",
        transaction_id="tx_prov_1",
        tag_name="layout",
        tag_value="schedule",
        recipe="name_plate/v1",
        logical_object_ref="text_schedule_01",
    )
    return {
        "ref": "ent_body_sched",
        "kind": "body",
        "name": "AZURE_FRONT_PANEL",
        "attributes": [
            {"group": "vendor.custom", "name": "color", "value": "blue"},
            {"group": RESERVED_METADATA_GROUP, "name": ROLE_ATTRIBUTE_NAME, "value": "decorative_text"},
            {
                "group": RESERVED_METADATA_GROUP,
                "name": f"{TAG_ATTRIBUTE_PREFIX}layout",
                "value": "schedule",
            },
            {
                "group": RESERVED_METADATA_GROUP,
                "name": PROVENANCE_ATTRIBUTE_NAME,
                "value": provenance_attribute_value(provenance),
            },
        ],
    }


def test_entity_metadata_view_derives_selector_fields_from_persisted_attributes():
    entity = _persisted_attributes_entity()
    view = entity_metadata_view(entity)
    assert view["role"] == "decorative_text"
    assert {"group": RESERVED_METADATA_GROUP, "name": "layout", "value": "schedule"} in view["tags"]
    assert view["created_by"]["tool"] == PROVENANCE_CREATOR_TOOL
    assert view["created_by"]["operation"] == "fusion_metadata:tag"
    assert view["created_by"]["operation_id"] == "op_prov_1"
    assert view["transaction_id"] == "tx_prov_1"
    assert view["recipe"] == "name_plate/v1"
    assert view["logical_object"] == "text_schedule_01"


def test_entity_metadata_view_ignores_foreign_groups_and_malformed_provenance():
    entity = {
        "ref": "ent_body_x",
        "attributes": [
            {"group": "vendor.custom", "name": ROLE_ATTRIBUTE_NAME, "value": "foreign"},
            {
                "group": RESERVED_METADATA_GROUP,
                "name": PROVENANCE_ATTRIBUTE_NAME,
                "value": "not-json",
            },
        ],
    }
    view = entity_metadata_view(entity)
    assert view["role"] is None
    assert view["tags"] == []
    assert view["created_by"] is None
    assert view["transaction_id"] is None
    assert view["recipe"] is None
    assert view["logical_object"] is None


def test_selectors_match_persisted_model_attributes():
    engine = SelectorEngine()
    entity = _persisted_attributes_entity()
    entities = [entity]

    # tag
    assert engine.filter(
        EntitySelector(tag=TagSelector(group=RESERVED_METADATA_GROUP, name="layout", value="schedule")),
        entities,
    )[0]["ref"] == "ent_body_sched"
    # role
    assert engine.filter(EntitySelector(role="decorative_text"), entities)[0]["ref"] == "ent_body_sched"
    # created_by provenance
    assert engine.filter(
        EntitySelector(created_by=CreatedBySelector(tool=PROVENANCE_CREATOR_TOOL)),
        entities,
    )[0]["ref"] == "ent_body_sched"
    assert engine.filter(
        EntitySelector(
            created_by=CreatedBySelector(
                tool=PROVENANCE_CREATOR_TOOL, operation="fusion_metadata:tag"
            )
        ),
        entities,
    )[0]["ref"] == "ent_body_sched"
    assert engine.filter(
        EntitySelector(
            created_by=CreatedBySelector(
                tool=PROVENANCE_CREATOR_TOOL, operation_id="op_prov_1"
            )
        ),
        entities,
    )[0]["ref"] == "ent_body_sched"
    # transaction_id / recipe / logical_object provenance fields
    assert engine.filter(EntitySelector(transaction_id="tx_prov_1"), entities)[0][
        "ref"
    ] == "ent_body_sched"
    assert engine.filter(EntitySelector(recipe="name_plate/v1"), entities)[0][
        "ref"
    ] == "ent_body_sched"
    assert engine.filter(EntitySelector(logical_object="text_schedule_01"), entities)[0][
        "ref"
    ] == "ent_body_sched"

    # Non-matching persisted values never match
    assert engine.filter(
        EntitySelector(tag=TagSelector(name="layout", value="other")), entities
    ) == []
    assert engine.filter(EntitySelector(transaction_id="tx_other"), entities) == []


def test_selectors_do_not_treat_provenance_or_foreign_attributes_as_tags():
    engine = SelectorEngine()
    entity = _persisted_attributes_entity()
    # provenance is not a tag, foreign group attributes are not Bridge tags
    assert engine.filter(EntitySelector(tag=TagSelector(name=PROVENANCE_ATTRIBUTE_NAME)), [entity]) == []
    assert engine.filter(EntitySelector(tag=TagSelector(name="color")), [entity]) == []


def test_direct_selector_fields_take_precedence_over_persisted_attributes():
    engine = SelectorEngine()
    entity = _persisted_attributes_entity()
    # Direct field disagrees with persisted attribute: direct field wins
    entity["role"] = "structural"
    assert engine.filter(EntitySelector(role="decorative_text"), [entity]) == []
    assert engine.filter(EntitySelector(role="structural"), [entity])[0] is entity
