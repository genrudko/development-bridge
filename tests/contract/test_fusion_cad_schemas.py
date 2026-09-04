from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from app.fusion_cad.requests import (
    FusionReadRequest,
    FusionStyleRequest,
    FusionTransactionRequest,
    FusionViewRequest,
    PickRequest,
    TextCreateRequest,
)
from app.fusion_cad.schemas import (
    fusion_inspect_schema,
    fusion_metadata_schema,
    fusion_read_schema,
    fusion_style_schema,
    fusion_transaction_schema,
    fusion_validate_schema,
    fusion_view_schema,
)


def _assert_strict_discriminated_schema(schema: dict[str, Any], expected_operations: set[str]) -> None:
    assert "oneOf" in schema, "Schema must use discriminated oneOf branches"
    branches = schema["oneOf"]
    found_operations: set[str] = set()

    for branch in branches:
        assert branch.get("type") == "object", f"Branch must be object: {branch}"
        assert branch.get("additionalProperties") is False, f"Branch must forbid additionalProperties: {branch}"
        props = branch.get("properties", {})
        assert "operation" in props, f"Branch must have operation property: {branch}"
        op_prop = props["operation"]
        op_const = op_prop.get("const") or (op_prop.get("enum")[0] if op_prop.get("enum") else None)
        assert op_const is not None, f"Branch must define const/enum operation: {branch}"
        found_operations.add(op_const)

        # Invariant: No unrestricted generic params object exists
        assert "params" not in props, f"Unrestricted params object forbidden in branch: {op_const}"

    missing = expected_operations - found_operations
    assert not missing, f"Missing required operations in schema: {missing}"
    extra = found_operations - expected_operations
    assert not extra, f"Unexpected extra operations in schema: {extra}"


def test_view_schema_is_discriminated_and_forbids_unknown_fields() -> None:
    schema = fusion_view_schema()
    assert "oneOf" in schema
    pick = next(branch for branch in schema["oneOf"] if branch["properties"]["operation"].get("const") == "pick" or branch["properties"]["operation"].get("enum") == ["pick"])
    assert pick["additionalProperties"] is False

    expected_view_ops = {
        "camera_read",
        "camera_set",
        "fit",
        "zoom_entity",
        "orient_to_face",
        "standard_view",
        "screenshot",
        "pick",
    }
    _assert_strict_discriminated_schema(schema, expected_view_ops)


def test_read_schema_is_strict_and_complete() -> None:
    schema = fusion_read_schema()
    expected_read_ops = {
        "model_snapshot",
        "entity",
        "feature_tree",
        "sketch",
        "parameters",
        "visibility",
        "selection",
        "query",
        "capabilities",
    }
    _assert_strict_discriminated_schema(schema, expected_read_ops)


def test_inspect_schema_is_strict_and_complete() -> None:
    schema = fusion_inspect_schema()
    expected_inspect_ops = {
        "describe",
        "bounding_box",
        "oriented_bbox",
        "centroid",
        "area",
        "perimeter",
        "volume",
        "distance",
        "minimum_distance",
        "angle",
        "parallel",
        "perpendicular",
        "coplanar",
        "concentric",
        "face_to_face_thickness",
    }
    _assert_strict_discriminated_schema(schema, expected_inspect_ops)


def test_metadata_schema_is_strict_and_complete() -> None:
    schema = fusion_metadata_schema()
    expected_metadata_ops = {
        "get",
        "set",
        "remove",
        "query",
        "tag",
        "untag",
        "set_role",
        "clear_role",
        "provenance",
    }
    _assert_strict_discriminated_schema(schema, expected_metadata_ops)


def test_style_schema_is_strict_and_complete() -> None:
    schema = fusion_style_schema()
    expected_style_ops = {
        "text_create",
        "text_read",
        "text_update",
        "text_delete",
        "text_extrude",
        "text_cut",
        "show",
        "hide",
        "set",
        "show_only",
        "isolate",
        "restore",
    }
    _assert_strict_discriminated_schema(schema, expected_style_ops)


def test_validate_schema_is_strict_and_complete() -> None:
    schema = fusion_validate_schema()
    expected_validate_ops = {"run"}
    _assert_strict_discriminated_schema(schema, expected_validate_ops)


def test_transaction_schema_is_strict_and_complete() -> None:
    schema = fusion_transaction_schema()
    expected_tx_ops = {
        "begin",
        "stage",
        "preview",
        "commit",
        "rollback",
        "abort",
        "status",
    }
    _assert_strict_discriminated_schema(schema, expected_tx_ops)


def test_request_union_validation_pick() -> None:
    adapter = TypeAdapter(FusionViewRequest)
    valid_payload = {
        "node_id": "node_1",
        "operation": "pick",
        "view_ref": "view_100",
        "x": 0.5,
        "y": 0.5,
        "coordinate_space": "normalized",
        "filters": ["face", "edge"],
    }
    req = adapter.validate_python(valid_payload)
    assert isinstance(req, PickRequest)
    assert req.operation == "pick"
    assert req.x == 0.5
    assert req.filters == ("face", "edge")

    # Rejects inapplicable / extra fields
    with pytest.raises(ValidationError):
        adapter.validate_python({**valid_payload, "extra_unexpected_field": 123})

    # Rejects invalid view_ref format
    with pytest.raises(ValidationError):
        adapter.validate_python({**valid_payload, "view_ref": "invalid_view"})


def test_request_union_validation_camera_set_framed_inputs() -> None:
    adapter = TypeAdapter(FusionViewRequest)
    valid_payload = {
        "node_id": "node_1",
        "operation": "camera_set",
        "eye": {"x": 100.0, "y": 200.0, "z": 300.0, "frame": {"space": "world"}},
        "target": {"x": 0.0, "y": 0.0, "z": 0.0, "frame": {"space": "world"}},
        "up": {"x": 0.0, "y": 0.0, "z": 1.0, "frame": {"space": "world"}},
        "fov": 45.0,
    }
    req = adapter.validate_python(valid_payload)
    assert req.operation == "camera_set"
    assert req.eye is not None and req.eye.x == 100.0
    assert req.eye.frame.space == "world"
    assert req.up is not None and req.up.z == 1.0

    # Finding 2: Rejects camera_set eye without explicit CoordinateFrame
    with pytest.raises(ValidationError):
        adapter.validate_python({
            "node_id": "node_1",
            "operation": "camera_set",
            "eye": {"x": 100.0, "y": 200.0, "z": 300.0},
        })

    # Rejects unframed raw list for eye
    with pytest.raises(ValidationError):
        adapter.validate_python({**valid_payload, "eye": [100.0, 200.0, 300.0]})


def test_request_union_validation_inspect_geometry_framed_inputs() -> None:
    from app.fusion_cad.requests import FusionInspectRequest

    adapter_req = TypeAdapter(FusionInspectRequest)

    # Valid bounding_box request with explicit frame
    req_bbox = adapter_req.validate_python({
        "node_id": "node_1",
        "operation": "bounding_box",
        "target": "ent_body_1",
        "frame": {"space": "world"},
    })
    assert req_bbox.operation == "bounding_box"

    # Finding 2: Rejects bounding_box request without explicit frame
    with pytest.raises(ValidationError):
        adapter_req.validate_python({
            "node_id": "node_1",
            "operation": "bounding_box",
            "target": "ent_body_1",
        })

    # Valid centroid request with explicit frame
    req_centroid = adapter_req.validate_python({
        "node_id": "node_1",
        "operation": "centroid",
        "target": "ent_body_1",
        "frame": {"space": "component", "ref": "ent_comp_1"},
    })
    assert req_centroid.operation == "centroid"

    # Finding 2: Rejects centroid request without explicit frame
    with pytest.raises(ValidationError):
        adapter_req.validate_python({
            "node_id": "node_1",
            "operation": "centroid",
            "target": "ent_body_1",
        })


def test_request_union_validation_text_create_framed_inputs() -> None:
    adapter = TypeAdapter(FusionStyleRequest)
    valid_payload = {
        "node_id": "node_1",
        "operation": "text_create",
        "text": "AZURE_123",
        "font": "Arial",
        "height_mm": 5.0,
        "position": {"x": 0.0, "y": 0.0, "z": 0.0, "frame": {"space": "world"}},
        "expected_revision": "rev_1",
    }
    req = adapter.validate_python(valid_payload)
    assert isinstance(req, TextCreateRequest)
    assert req.text == "AZURE_123"
    assert req.position.x == 0.0
    assert req.position.frame.space == "world"

    # Finding 2: Rejects text_create when position is missing explicit frame
    with pytest.raises(ValidationError):
        adapter.validate_python({
            "node_id": "node_1",
            "operation": "text_create",
            "text": "AZURE_123",
            "height_mm": 5.0,
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        })

    # Finding 2: Rejects text_create when position itself is omitted
    with pytest.raises(ValidationError):
        adapter.validate_python({
            "node_id": "node_1",
            "operation": "text_create",
            "text": "AZURE_123",
            "height_mm": 5.0,
        })

    # Rejects invalid raw list for position
    with pytest.raises(ValidationError):
        adapter.validate_python({**valid_payload, "position": [0.0, 0.0, 0.0]})

    # Rejects invalid operation in style
    with pytest.raises(ValidationError):
        adapter.validate_python({**valid_payload, "operation": "unknown_op"})

    # Rejects invalid revision format
    with pytest.raises(ValidationError):
        adapter.validate_python({**valid_payload, "expected_revision": "not_a_rev"})


def test_request_union_validation_read_snapshot() -> None:
    adapter = TypeAdapter(FusionReadRequest)
    req = adapter.validate_python({
        "node_id": "node_1",
        "operation": "model_snapshot",
        "include_bodies": True,
    })
    assert req.operation == "model_snapshot"


def test_request_union_validation_transaction_stage_strict_action() -> None:
    adapter = TypeAdapter(FusionTransactionRequest)
    req = adapter.validate_python({
        "node_id": "node_1",
        "operation": "begin",
    })
    assert req.operation == "begin"

    # Stage valid typed text_create action with explicit framed position
    req_stage = adapter.validate_python({
        "node_id": "node_1",
        "operation": "stage",
        "transaction_id": "tx_123",
        "action": {
            "action_type": "text_create",
            "text": "SCHEDULE",
            "height_mm": 10.0,
            "position": {"x": 0.0, "y": 0.0, "z": 0.0, "frame": {"space": "world"}},
        },
    })
    assert req_stage.operation == "stage"
    assert req_stage.action.action_type == "text_create"

    # Finding 2: Rejects stage text_create without framed position
    with pytest.raises(ValidationError):
        adapter.validate_python({
            "node_id": "node_1",
            "operation": "stage",
            "transaction_id": "tx_123",
            "action": {
                "action_type": "text_create",
                "text": "SCHEDULE",
                "height_mm": 10.0,
            },
        })

    # Stage valid typed metadata action
    req_stage_meta = adapter.validate_python({
        "node_id": "node_1",
        "operation": "stage",
        "transaction_id": "tx_123",
        "action": {
            "action_type": "metadata_set_role",
            "target": "ent_panel_1",
            "role": "main_panel",
        },
    })
    assert req_stage_meta.operation == "stage"
    assert req_stage_meta.action.action_type == "metadata_set_role"

    # Finding 3: Discriminated visibility actions strictness
    # 1) Restore accepts no target and no visible
    req_restore = adapter.validate_python({
        "node_id": "node_1",
        "operation": "stage",
        "transaction_id": "tx_123",
        "action": {"action_type": "visibility_restore"},
    })
    assert req_restore.action.action_type == "visibility_restore"

    req_restore_unprefixed = adapter.validate_python({
        "node_id": "node_1",
        "operation": "stage",
        "transaction_id": "tx_123",
        "action": {"action_type": "restore"},
    })
    assert req_restore_unprefixed.action.action_type == "restore"

    with pytest.raises(ValidationError):
        adapter.validate_python({
            "node_id": "node_1",
            "operation": "stage",
            "transaction_id": "tx_123",
            "action": {"action_type": "restore", "target": "ent_body_1"},
        })

    with pytest.raises(ValidationError):
        adapter.validate_python({
            "node_id": "node_1",
            "operation": "stage",
            "transaction_id": "tx_123",
            "action": {"action_type": "restore", "visible": True},
        })

    # 2) Set requires target + visible
    req_set = adapter.validate_python({
        "node_id": "node_1",
        "operation": "stage",
        "transaction_id": "tx_123",
        "action": {"action_type": "visibility_set", "target": "ent_body_1", "visible": False},
    })
    assert req_set.action.action_type == "visibility_set"

    req_set_unprefixed = adapter.validate_python({
        "node_id": "node_1",
        "operation": "stage",
        "transaction_id": "tx_123",
        "action": {"action_type": "set", "target": "ent_body_1", "visible": True},
    })
    assert req_set_unprefixed.action.action_type == "set"

    with pytest.raises(ValidationError):
        adapter.validate_python({
            "node_id": "node_1",
            "operation": "stage",
            "transaction_id": "tx_123",
            "action": {"action_type": "visibility_set", "target": "ent_body_1"},
        })

    with pytest.raises(ValidationError):
        adapter.validate_python({
            "node_id": "node_1",
            "operation": "stage",
            "transaction_id": "tx_123",
            "action": {"action_type": "set", "visible": True},
        })

    # 3) Show / Hide / Show_only / Isolate require target and forbid visible
    for act in ["visibility_show", "show", "visibility_hide", "hide", "visibility_show_only", "show_only", "visibility_isolate", "isolate"]:
        req_vis = adapter.validate_python({
            "node_id": "node_1",
            "operation": "stage",
            "transaction_id": "tx_123",
            "action": {"action_type": act, "target": "ent_body_1"},
        })
        assert req_vis.action.action_type == act

        # Forbid visible
        with pytest.raises(ValidationError):
            adapter.validate_python({
                "node_id": "node_1",
                "operation": "stage",
                "transaction_id": "tx_123",
                "action": {"action_type": act, "target": "ent_body_1", "visible": True},
            })

        # Require target
        with pytest.raises(ValidationError):
            adapter.validate_python({
                "node_id": "node_1",
                "operation": "stage",
                "transaction_id": "tx_123",
                "action": {"action_type": act},
            })

    # Reject arbitrary unrestricted free-form / raw_python action
    with pytest.raises(ValidationError):
        adapter.validate_python({
            "node_id": "node_1",
            "operation": "stage",
            "transaction_id": "tx_123",
            "action": {
                "raw_python": "import os; os.system('echo exploit')",
            },
        })

    with pytest.raises(ValidationError):
        adapter.validate_python({
            "node_id": "node_1",
            "operation": "stage",
            "transaction_id": "tx_123",
            "action": {
                "action_type": "unknown_mutation",
                "arbitrary_payload": 123,
            },
        })

    req_commit = adapter.validate_python({
        "node_id": "node_1",
        "operation": "commit",
        "transaction_id": "tx_123",
        "expected_revision": "rev_10",
    })
    assert req_commit.operation == "commit"
