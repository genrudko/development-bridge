from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.errors import BridgeError, ErrorCode
from app.fusion_cad.capabilities import CapabilityMatrix, FusionRuntimeIdentity
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.models import CapabilityRecord


def test_fusion_runtime_identity_immutable_and_strict():
    identity = FusionRuntimeIdentity(
        application="Autodesk Fusion",
        fusion_version="2.0.18000",
        relay_version="1.0.0",
        platform="Windows",
        api_version="fusion.cad/v1",
        implementation="fusion-desktop-mcp",
    )
    assert identity.application == "Autodesk Fusion"
    assert identity.fusion_version == "2.0.18000"
    assert identity.api_version == "fusion.cad/v1"

    with pytest.raises(ValidationError):
        FusionRuntimeIdentity(
            application="Autodesk Fusion",
            unknown_field="invalid",  # type: ignore[call-arg]
        )


def test_unavailable_capability_fails_with_capability_unavailable():
    record = CapabilityRecord(
        name="view.pick",
        state="unavailable",
        implementation=None,
        limitations=("Visual pick not available on this headless runtime",),
    )
    matrix = CapabilityMatrix.from_records([record])

    with pytest.raises(BridgeError) as exc_info:
        matrix.require("view.pick")

    assert exc_info.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    assert isinstance(exc_info.value, FusionCadError)
    assert exc_info.value.retryable is False
    assert exc_info.value.details.get("capability") == "view.pick"


def test_unknown_capability_fails_with_capability_unavailable():
    matrix = CapabilityMatrix.from_records([])
    with pytest.raises(BridgeError) as exc_info:
        matrix.require("nonexistent.feature")
    assert exc_info.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    assert exc_info.value.retryable is False


def test_degraded_capability_requires_explicit_opt_in():
    record = CapabilityRecord(
        name="view.pick",
        state="degraded",
        implementation="viewport-raycast",
        limitations=("Raycast geometry intersection without native preselection",),
    )
    matrix = CapabilityMatrix.from_records([record])

    # Default require (allow_degraded=False) must fail with CAPABILITY_DEGRADED
    with pytest.raises(BridgeError) as exc_info:
        matrix.require("view.pick")

    assert exc_info.value.code == ErrorCode.CAPABILITY_DEGRADED
    assert isinstance(exc_info.value, FusionCadError)
    assert exc_info.value.retryable is False
    assert exc_info.value.details.get("capability") == "view.pick"
    assert "limitations" in exc_info.value.details

    # Explicit opt-in succeeds and returns the record
    result = matrix.require("view.pick", allow_degraded=True)
    assert result.name == "view.pick"
    assert result.state == "degraded"
    assert result.implementation == "viewport-raycast"


def test_supported_capability_succeeds():
    record = CapabilityRecord(
        name="view.pick",
        state="supported",
        implementation="native-preselect",
        fusion_version="2.0.18000",
        limitations=(),
    )
    matrix = CapabilityMatrix.from_records([record])

    result = matrix.require("view.pick")
    assert result.name == "view.pick"
    assert result.state == "supported"
    assert result.implementation == "native-preselect"


def test_matrix_records_deterministically_sorted():
    r1 = CapabilityRecord(name="view.pick", state="supported")
    r2 = CapabilityRecord(name="export.dxf", state="unavailable")
    r3 = CapabilityRecord(name="design.access", state="supported")
    matrix = CapabilityMatrix.from_records([r1, r2, r3])

    names = [r.name for r in matrix.records]
    assert names == ["design.access", "export.dxf", "view.pick"]


def test_capability_matrix_from_probe_supported():
    probe = {
        "application": "Autodesk Fusion",
        "fusion_version": "2.0.18000",
        "relay_version": "1.0.0",
        "platform": "Windows",
        "probe_facts": {
            "has_app": True,
            "has_measure_manager": True,
            "has_selection_primitives": True,
            "has_active_document": True,
            "has_mutation_indicators": True,
            "has_attributes": True,
            "has_adsk_fusion": True,
            "has_design_access": True,
            "has_timeline_access": True,
            "has_entity_token_resolver": True,
            "has_sketch_access": True,
            "has_sketch_text": True,
            "has_export_manager": True,
            "has_joint_access": True,
            "has_camera": True,
            "has_viewport_conversion": True,
            "has_command_preview": True,
            "has_undo_redo": True,
        },
    }
    matrix = CapabilityMatrix.from_probe(probe)
    assert matrix.identity is not None
    assert matrix.identity.fusion_version == "2.0.18000"

    for cap_name in (
        "entity.token_resolver",
        "design.access",
        "timeline.access",
        "sketch.access",
        "inspect.measure",
        "view.camera",
        "view.viewport_conversion",
        "view.pick",
        "selection.primitives",
        "transaction.preview_hooks",
        "transaction.preview_replay",
        "metadata.attributes",
        "style.sketch_text",
        "transaction.undo_redo",
        "revision.mutation_indicators",
        "revision.external_change_detection",
        "export.dxf",
        "assembly.joints",
    ):
        rec = matrix.get(cap_name)
        assert rec is not None, f"Capability {cap_name} missing from matrix"
        assert rec.state == "supported", f"Capability {cap_name} state was {rec.state}, expected supported"


def test_capability_matrix_from_probe_degraded_and_unavailable():
    probe = {
        "application": "Autodesk Fusion",
        "fusion_version": "2.0.12000",
        "relay_version": "1.0.0",
        "platform": "Windows",
        "probe_facts": {
            "has_app": True,
            "has_measure_manager": True,
            "has_selection_primitives": False,
            "has_active_document": True,
            "has_mutation_indicators": True,
            "has_attributes": True,
            "has_adsk_fusion": True,
            "has_design_access": True,
            "has_timeline_access": False,
            "has_entity_token_resolver": False,
            "has_sketch_access": True,
            "has_sketch_text": True,
            "has_export_manager": False,
            "has_joint_access": False,
            "has_camera": True,
            "has_viewport_conversion": True,
            "has_command_preview": False,
            "has_undo_redo": True,
        },
    }
    matrix = CapabilityMatrix.from_probe(probe)

    # entity token resolver is unavailable
    token_resolver = matrix.get("entity.token_resolver")
    assert token_resolver is not None
    assert token_resolver.state == "unavailable"

    # view.pick is degraded because viewport conversion exists but no selection primitives
    pick = matrix.get("view.pick")
    assert pick is not None
    assert pick.state == "degraded"
    assert pick.implementation == "viewport-raycast"
    assert len(pick.limitations) > 0

    # transaction.preview_replay is degraded because command preview is missing but undo/redo exists
    tx = matrix.get("transaction.preview_replay")
    assert tx is not None
    assert tx.state == "degraded"
    assert len(tx.limitations) > 0

    # export.dxf is unavailable
    dxf = matrix.get("export.dxf")
    assert dxf is not None
    assert dxf.state == "unavailable"
