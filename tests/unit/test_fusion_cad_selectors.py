from __future__ import annotations

import pytest

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.models import (
    BoundingBox,
    CoordinateFrame,
    CreatedBySelector,
    EntitySelector,
    NamePattern,
    Point3,
    TagSelector,
)
from app.fusion_cad.selectors import (
    SelectorEngine,
    SelectorQueryResult,
)


def _make_sample_entities() -> list[dict]:
    world = CoordinateFrame(space="world")
    return [
        {
            "ref": "ent_body_001",
            "kind": "body",
            "name": "AZURE_FRONT_PANEL",
            "component_path": ("Root", "LEFT"),
            "occurrence": "ent_occ_left",
            "feature_type": "extrude",
            "created_by": {
                "tool": "fusion_style",
                "operation": "text.create",
                "operation_id": "op_001",
            },
            "tags": [{"group": "bridge.cad/v1", "name": "layout", "value": "schedule"}],
            "role": ("decorative_text",),
            "visible": True,
            "appearance": "Steel - Satin",
            "bounding_box": BoundingBox(
                min_point=Point3(x=0.0, y=0.0, z=0.0, frame=world),
                max_point=Point3(x=10.0, y=10.0, z=10.0, frame=world),
                frame=world,
            ),
            "logical_object": "text_header_1",
            "transaction_id": "tx_init_1",
            "recipe": "bracket_recipe_v1",
        },
        {
            "ref": "ent_body_002",
            "kind": "body",
            "name": "AZURE_REAR_PANEL",
            "component_path": ("Root", "RIGHT"),
            "occurrence": "ent_occ_right",
            "feature_type": "revolve",
            "created_by": {
                "tool": "fusion_style",
                "operation": "text.extrude",
                "operation_id": "op_002",
            },
            "tags": [
                {"group": "bridge.cad/v1", "name": "structural", "value": "support"}
            ],
            "role": ("mounting_bracket",),
            "visible": False,
            "appearance": "Aluminum - Anodized",
            "bounding_box": BoundingBox(
                min_point=Point3(x=100.0, y=100.0, z=100.0, frame=world),
                max_point=Point3(x=150.0, y=150.0, z=150.0, frame=world),
                frame=world,
            ),
            "logical_object": "text_footer_1",
            "transaction_id": "tx_init_2",
            "recipe": "bracket_recipe_v2",
        },
        {
            "ref": "ent_face_003",
            "kind": "face",
            "name": "FrontFace",
            "component_path": ("Root", "LEFT"),
            "occurrence": "ent_occ_left",
            "feature_type": "fillet",
            "created_by": {
                "tool": "fusion_mutate",
                "operation": "fillet",
                "operation_id": "op_003",
            },
            "tags": [],
            "role": (),
            "visible": True,
            "appearance": "Steel - Satin",
            "bounding_box": None,
            "logical_object": None,
            "transaction_id": "tx_init_1",
            "recipe": None,
        },
    ]


def test_cardinality_zero_matches_raises_selector_empty() -> None:
    engine = SelectorEngine()
    entities = _make_sample_entities()

    # Query matching nothing
    selector = EntitySelector(kind="sketch")

    with pytest.raises(FusionCadError) as exc_info:
        engine.resolve_one(selector, entities)

    assert exc_info.value.code == ErrorCode.SELECTOR_EMPTY
    assert exc_info.value.details.get("matched_count") == 0


def test_cardinality_multiple_matches_raises_selector_ambiguous() -> None:
    engine = SelectorEngine()
    entities = _make_sample_entities()

    # Query matching 2 bodies
    selector = EntitySelector(kind="body")

    with pytest.raises(FusionCadError) as exc_info:
        engine.resolve_one(selector, entities)

    assert exc_info.value.code == ErrorCode.SELECTOR_AMBIGUOUS
    assert exc_info.value.details.get("matched_count") == 2
    assert "ent_body_001" in exc_info.value.details.get("matched_refs", [])
    assert "ent_body_002" in exc_info.value.details.get("matched_refs", [])


def test_cardinality_single_match_succeeds() -> None:
    engine = SelectorEngine()
    entities = _make_sample_entities()

    # Query matching exactly 1 entity
    selector = EntitySelector(kind="face")
    match = engine.resolve_one(selector, entities)
    assert match["ref"] == "ent_face_003"


def test_deterministic_multi_query_with_matched_count_and_normalized_selector() -> None:
    engine = SelectorEngine()
    entities = _make_sample_entities()

    selector_dict = {
        "kind": "body",
        "name": "^AZURE_",
    }
    result = engine.query(selector_dict, entities)

    assert isinstance(result, SelectorQueryResult)
    assert result.matched_count == 2
    assert result.refs == ("ent_body_001", "ent_body_002")
    assert isinstance(result.normalized_selector, EntitySelector)
    assert result.normalized_selector.kind == ("body",)
    assert isinstance(result.normalized_selector.name, NamePattern)
    assert result.normalized_selector.name.regex == "^AZURE_"


def test_selector_all_fields_filtering() -> None:
    engine = SelectorEngine()
    entities = _make_sample_entities()
    world = CoordinateFrame(space="world")

    # 1. kind
    assert len(engine.filter(EntitySelector(kind="body"), entities)) == 2
    assert len(engine.filter(EntitySelector(kind=("body", "face")), entities)) == 3

    # 2. name / regex
    res_name = engine.filter(EntitySelector(name=NamePattern(regex="FRONT")), entities)
    assert len(res_name) == 1
    assert res_name[0]["ref"] == "ent_body_001"

    # 3. component_path
    res_path = engine.filter(EntitySelector(component_path=("Root", "LEFT")), entities)
    assert len(res_path) == 2

    # 4. occurrence
    res_occ = engine.filter(EntitySelector(occurrence="ent_occ_right"), entities)
    assert len(res_occ) == 1
    assert res_occ[0]["ref"] == "ent_body_002"

    # 5. feature_type
    res_feat = engine.filter(EntitySelector(feature_type="fillet"), entities)
    assert len(res_feat) == 1
    assert res_feat[0]["ref"] == "ent_face_003"

    # 6. created_by
    res_creator = engine.filter(
        EntitySelector(
            created_by=CreatedBySelector(tool="fusion_style", operation="text.create")
        ),
        entities,
    )
    assert len(res_creator) == 1
    assert res_creator[0]["ref"] == "ent_body_001"

    # 7. tag
    res_tag = engine.filter(
        EntitySelector(
            tag=TagSelector(group="bridge.cad/v1", name="layout", value="schedule")
        ),
        entities,
    )
    assert len(res_tag) == 1
    assert res_tag[0]["ref"] == "ent_body_001"

    # 8. role
    res_role = engine.filter(EntitySelector(role="decorative_text"), entities)
    assert len(res_role) == 1
    assert res_role[0]["ref"] == "ent_body_001"

    # 9. visible
    res_vis_true = engine.filter(EntitySelector(visible=True), entities)
    assert len(res_vis_true) == 2
    res_vis_false = engine.filter(EntitySelector(visible=False), entities)
    assert len(res_vis_false) == 1
    assert res_vis_false[0]["ref"] == "ent_body_002"

    # 10. appearance
    res_app = engine.filter(EntitySelector(appearance="Aluminum - Anodized"), entities)
    assert len(res_app) == 1
    assert res_app[0]["ref"] == "ent_body_002"

    # 11. bbox_region
    query_box = BoundingBox(
        min_point=Point3(x=-5.0, y=-5.0, z=-5.0, frame=world),
        max_point=Point3(x=20.0, y=20.0, z=20.0, frame=world),
        frame=world,
    )
    res_bbox = engine.filter(EntitySelector(bbox_region=query_box), entities)
    assert len(res_bbox) == 1
    assert res_bbox[0]["ref"] == "ent_body_001"

    # 12. logical_object
    res_log = engine.filter(EntitySelector(logical_object="text_header_1"), entities)
    assert len(res_log) == 1
    assert res_log[0]["ref"] == "ent_body_001"

    # 13. transaction_id
    res_tx = engine.filter(EntitySelector(transaction_id="tx_init_1"), entities)
    assert len(res_tx) == 2

    # 14. recipe
    res_recipe = engine.filter(EntitySelector(recipe="bracket_recipe_v2"), entities)
    assert len(res_recipe) == 1
    assert res_recipe[0]["ref"] == "ent_body_002"


def test_selector_normalization() -> None:
    engine = SelectorEngine()

    norm = engine.normalize(
        {
            "kind": "body",
            "name": "SampleName",
            "role": "decorative",
            "component_path": ["Root", "Sub"],
        }
    )

    assert norm.kind == ("body",)
    assert isinstance(norm.name, NamePattern)
    assert norm.name.regex == "^SampleName$"
    assert norm.role == ("decorative",)
    assert norm.component_path == ("Root", "Sub")
