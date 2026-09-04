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

    # Rejects inapplicable / extra fields
    with pytest.raises(ValidationError):
        adapter.validate_python({**valid_payload, "extra_unexpected_field": 123})


def test_request_union_validation_text_create() -> None:
    adapter = TypeAdapter(FusionStyleRequest)
    valid_payload = {
        "node_id": "node_1",
        "operation": "text_create",
        "text": "AZURE_123",
        "font": "Arial",
        "height_mm": 5.0,
        "position": [0.0, 0.0, 0.0],
        "expected_revision": "rev_1",
    }
    req = adapter.validate_python(valid_payload)
    assert isinstance(req, TextCreateRequest)
    assert req.text == "AZURE_123"

    # Rejects invalid operation in style
    with pytest.raises(ValidationError):
        adapter.validate_python({**valid_payload, "operation": "unknown_op"})


def test_request_union_validation_read_snapshot() -> None:
    adapter = TypeAdapter(FusionReadRequest)
    req = adapter.validate_python({
        "node_id": "node_1",
        "operation": "model_snapshot",
        "include_bodies": True,
    })
    assert req.operation == "model_snapshot"


def test_request_union_validation_transaction() -> None:
    adapter = TypeAdapter(FusionTransactionRequest)
    req = adapter.validate_python({
        "node_id": "node_1",
        "operation": "begin",
    })
    assert req.operation == "begin"

    req_commit = adapter.validate_python({
        "node_id": "node_1",
        "operation": "commit",
        "transaction_id": "tx_123",
        "expected_revision": "rev_10",
    })
    assert req_commit.operation == "commit"
