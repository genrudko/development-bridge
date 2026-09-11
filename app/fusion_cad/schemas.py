from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter

from app.fusion_cad.requests import (
    FusionFeatureRequest,
    FusionInspectRequest,
    FusionMetadataRequest,
    FusionReadRequest,
    FusionSketchRequest,
    FusionStyleRequest,
    FusionTransactionRequest,
    FusionValidateRequest,
    FusionViewRequest,
)


def _build_discriminated_schema(request_type: Any) -> dict[str, Any]:
    """Build a dereferenced discriminated oneOf JSON schema suitable for MCP tools."""
    raw = TypeAdapter(request_type).json_schema()
    defs: dict[str, Any] = raw.get("$defs", {})
    branches: list[dict[str, Any]] = []

    for ref_item in raw.get("oneOf", []):
        ref_path = ref_item.get("$ref", "")
        ref_name = ref_path.split("/")[-1] if "/" in ref_path else ""
        if ref_name and ref_name in defs:
            branch = dict(defs[ref_name])
            branches.append(branch)
        else:
            branches.append(ref_item)

    schema: dict[str, Any] = {
        "type": "object",
        "oneOf": branches,
    }
    if defs:
        schema["$defs"] = defs
    return schema


def fusion_read_schema() -> dict[str, Any]:
    return _build_discriminated_schema(FusionReadRequest)


def fusion_inspect_schema() -> dict[str, Any]:
    return _build_discriminated_schema(FusionInspectRequest)


def fusion_view_schema() -> dict[str, Any]:
    return _build_discriminated_schema(FusionViewRequest)


def fusion_metadata_schema() -> dict[str, Any]:
    return _build_discriminated_schema(FusionMetadataRequest)


def fusion_style_schema() -> dict[str, Any]:
    return _build_discriminated_schema(FusionStyleRequest)


def fusion_validate_schema() -> dict[str, Any]:
    return _build_discriminated_schema(FusionValidateRequest)


def fusion_transaction_schema() -> dict[str, Any]:
    return _build_discriminated_schema(FusionTransactionRequest)


def fusion_sketch_schema() -> dict[str, Any]:
    return _build_discriminated_schema(FusionSketchRequest)


def fusion_feature_schema() -> dict[str, Any]:
    return _build_discriminated_schema(FusionFeatureRequest)


FUSION_CAD_SCHEMAS: dict[str, dict[str, Any]] = {
    "fusion_read": fusion_read_schema(),
    "fusion_inspect": fusion_inspect_schema(),
    "fusion_view": fusion_view_schema(),
    "fusion_metadata": fusion_metadata_schema(),
    "fusion_style": fusion_style_schema(),
    "fusion_validate": fusion_validate_schema(),
    "fusion_transaction": fusion_transaction_schema(),
    "fusion_sketch": fusion_sketch_schema(),
    "fusion_feature": fusion_feature_schema(),
}
