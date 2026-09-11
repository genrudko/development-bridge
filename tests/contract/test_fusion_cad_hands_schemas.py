from __future__ import annotations

import math

import pytest
from pydantic import TypeAdapter, ValidationError

from app.fusion_cad.requests import FusionFeatureRequest, FusionSketchRequest
from app.fusion_cad.schemas import fusion_feature_schema, fusion_sketch_schema


def _action(action_id, action_type, **kwargs):
    return {"id": action_id, "type": action_type, **kwargs}


def _action_ref(action_id, *, element="curve", index=0):
    return {
        "source": "action",
        "action_id": action_id,
        "element": element,
        "index": index,
    }


def test_sketch_schema_is_strict_discriminated_create_and_batch():
    schema = fusion_sketch_schema()
    assert schema["type"] == "object"
    branches = schema["oneOf"]
    assert len(branches) == 2
    operations = {branch["properties"]["operation"]["const"] for branch in branches}
    assert operations == {"create", "batch"}
    for branch in branches:
        assert branch["additionalProperties"] is False
        assert "params" not in branch["properties"]


def test_sketch_create_requires_revision_even_for_dry_run_and_accepts_face_plane():
    adapter = TypeAdapter(FusionSketchRequest)
    req = adapter.validate_python(
        {
            "node_id": "logical-cad",
            "operation": "create",
            "plane": {"face_ref": "ent_face_1"},
            "name": "HandsSketch",
            "expected_revision": "rev_3",
            "dry_run": True,
        }
    )
    assert req.operation == "create"
    assert req.plane.face_ref == "ent_face_1"

    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "node_id": "logical-cad",
                "operation": "create",
                "plane": "xy",
                "dry_run": True,
            }
        )


def test_sketch_batch_accepts_prior_action_refs_and_rejects_duplicate_or_forward_refs():
    adapter = TypeAdapter(FusionSketchRequest)
    base = {
        "node_id": "logical-cad",
        "operation": "batch",
        "sketch": "ent_sketch_1",
        "expected_revision": "rev_3",
    }
    valid_actions = [
        _action("a1", "line", x1=0, y1=0, x2=20, y2=0),
        _action("a2", "line", x1=0, y1=10, x2=20, y2=10),
        _action(
            "d1",
            "dimension",
            kind="distance",
            entity_one=_action_ref("a1"),
            entity_two=_action_ref("a2"),
            value=10,
        ),
    ]
    req = adapter.validate_python({**base, "actions": valid_actions})
    assert req.operation == "batch"
    assert len(req.actions) == 3

    duplicate = [valid_actions[0], {**valid_actions[1], "id": "a1"}]
    with pytest.raises(ValidationError):
        adapter.validate_python({**base, "actions": duplicate})

    forward = [
        _action(
            "d1",
            "dimension",
            kind="distance",
            entity_one=_action_ref("later"),
            entity_two={"source": "entity", "ref": "ent_curve_1"},
            value=10,
        ),
        _action("later", "line", x1=0, y1=0, x2=10, y2=0),
    ]
    with pytest.raises(ValidationError):
        adapter.validate_python({**base, "actions": forward})


def test_sketch_dimension_normalizes_entity_two_contract():
    adapter = TypeAdapter(FusionSketchRequest)
    base = {
        "node_id": "logical-cad",
        "operation": "batch",
        "sketch": "ent_sketch_1",
        "expected_revision": "rev_1",
    }
    line = _action("a1", "line", x1=0, y1=0, x2=10, y2=0)
    circle = _action("c1", "circle", x=0, y=0, diameter=8)

    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                **base,
                "actions": [
                    line,
                    _action(
                        "bad",
                        "dimension",
                        kind="distance",
                        entity_one=_action_ref("a1"),
                        value=5,
                    ),
                ],
            }
        )

    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                **base,
                "actions": [
                    circle,
                    _action(
                        "bad",
                        "dimension",
                        kind="diameter",
                        entity_one=_action_ref("c1"),
                        entity_two={"source": "entity", "ref": "ent_curve_1"},
                        value=8,
                    ),
                ],
            }
        )

    ok = adapter.validate_python(
        {
            **base,
            "actions": [
                circle,
                _action(
                    "diam",
                    "dimension",
                    kind="diameter",
                    entity_one=_action_ref("c1"),
                    value=8,
                ),
            ],
        }
    )
    assert ok.actions[-1].kind == "diameter"


def test_sketch_actions_reject_nonfinite_geometry_and_unknown_fields():
    adapter = TypeAdapter(FusionSketchRequest)
    base = {
        "node_id": "logical-cad",
        "operation": "batch",
        "sketch": "ent_sketch_1",
        "expected_revision": "rev_1",
    }
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValidationError):
            adapter.validate_python(
                {**base, "actions": [_action("a1", "line", x1=bad, y1=0, x2=10, y2=0)]}
            )
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                **base,
                "actions": [
                    _action("a1", "rectangle", width=20, height=10, x=0, y=0, raw_index=5)
                ],
            }
        )


def test_feature_schema_is_strict_create_with_typed_feature_union():
    schema = fusion_feature_schema()
    assert len(schema["oneOf"]) == 1
    create = schema["oneOf"][0]
    assert create["properties"]["operation"]["const"] == "create"
    assert create["additionalProperties"] is False
    assert "params" not in create["properties"]

    adapter = TypeAdapter(FusionFeatureRequest)
    cases = [
        {
            "kind": "extrude",
            "sketch": "ent_sketch_1",
            "distance_mm": 10,
            "profile_index": 0,
            "operation_type": "new_body",
        },
        {
            "kind": "hole",
            "target_face": "ent_face_1",
            "diameter_mm": 4,
            "x_mm": 5,
            "y_mm": 5,
            "through_all": True,
        },
        {
            "kind": "fillet",
            "body": "ent_body_1",
            "edges": ["ent_edge_1"],
            "radius_mm": 1,
        },
        {
            "kind": "chamfer",
            "body": "ent_body_1",
            "edges": ["ent_edge_1"],
            "distance_mm": 1,
        },
    ]
    for feature in cases:
        req = adapter.validate_python(
            {
                "node_id": "logical-cad",
                "operation": "create",
                "expected_revision": "rev_9",
                "dry_run": False,
                "feature": feature,
            }
        )
        assert req.feature.kind == feature["kind"]


def test_feature_request_rejects_missing_revision_bad_cross_kind_fields_and_nonfinite_values():
    adapter = TypeAdapter(FusionFeatureRequest)
    extrude = {
        "kind": "extrude",
        "sketch": "ent_sketch_1",
        "distance_mm": 10,
        "profile_index": 0,
    }
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"node_id": "logical-cad", "operation": "create", "feature": extrude}
        )
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "node_id": "logical-cad",
                "operation": "create",
                "expected_revision": "rev_1",
                "feature": {**extrude, "radius_mm": 2},
            }
        )
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "node_id": "logical-cad",
                "operation": "create",
                "expected_revision": "rev_1",
                "feature": {**extrude, "distance_mm": math.inf},
            }
        )
