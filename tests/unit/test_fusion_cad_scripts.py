from __future__ import annotations

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.fusion_cad.models import ImmutableMapping
from app.fusion_cad.requests import ModelSnapshotRequest
from app.fusion_cad.scripts import FusionCadScriptBundle


def test_bundle_embeds_utf8_payload_as_json_not_python_source():
    bundle = FusionCadScriptBundle()
    script = bundle.build("read", {"operation": "echo", "text": "ПЫТОК 😈"})
    compile(script, "<fusion-cad>", "exec")
    assert "ПЫТОК 😈" in script
    assert "fusion.cad/v1" in script


def test_bundle_rejects_raw_string_and_non_serializable():
    bundle = FusionCadScriptBundle()
    with pytest.raises(BridgeError) as exc:
        bundle.build("read", "import os; os.system('rm -rf /')")  # type: ignore[arg-type]
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT

    with pytest.raises(BridgeError) as exc:
        bundle.build("read", {"bad": object()})
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT


def test_bundle_rejects_invalid_group():
    bundle = FusionCadScriptBundle()
    with pytest.raises(BridgeError) as exc:
        bundle.build("../../secret", {"operation": "test"})
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT

    with pytest.raises(BridgeError) as exc:
        bundle.build("invalid-group!", {"operation": "test"})
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT


def test_bundle_accepts_pydantic_model():
    bundle = FusionCadScriptBundle()
    req = ModelSnapshotRequest(node_id="desk-1", operation="model_snapshot")
    script = bundle.build("read", req)
    compile(script, "<fusion-cad>", "exec")
    assert "model_snapshot" in script
    assert "desk-1" in script


def test_bundle_accepts_immutable_mapping():
    bundle = FusionCadScriptBundle()
    mapping = ImmutableMapping({"operation": "echo", "nested": {"key": "val"}})
    script = bundle.build("read", mapping)
    compile(script, "<fusion-cad>", "exec")
    assert "nested" in script


def test_bundle_classmethod_call():
    script = FusionCadScriptBundle.build(
        "read",
        {"operation": "echo", "text": "classmethod test"},
    )
    compile(script, "<fusion-cad>", "exec")
    assert "classmethod test" in script
