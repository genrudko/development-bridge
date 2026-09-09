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


def test_capability_matrix_from_probe_truthful_states():
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

    # Supported contract operations verified on active document
    for cap_name in (
        "entity.token_resolver",
        "design.access",
        "timeline.access",
        "sketch.access",
        "revision.mutation_indicators",
    ):
        rec = matrix.get(cap_name)
        assert rec is not None, f"Capability {cap_name} missing from matrix"
        assert rec.state == "supported", f"Capability {cap_name} state was {rec.state}, expected supported"

    # Finding 2: hasattr/class existence alone must NOT produce supported claims;
    # reports degraded with explicit limitations for camera, selection, preview, attributes, undo/redo, etc.
    for degraded_cap, expected_kw in (
        ("view.camera", "camera runtime context"),
        ("view.viewport_conversion", "active viewport runtime context"),
        ("selection.primitives", "interactive selection collection"),
        ("transaction.preview_hooks", "runtime preview execution"),
        ("metadata.attributes", "active document attribute collection"),
        ("transaction.undo_redo", "undo/redo behavior"),
        ("inspect.measure", "MeasureManager"),
        ("style.sketch_text", "SketchText"),
        ("view.pick", "live feasibility proof"),
        ("transaction.preview_replay", "live feasibility proof"),
        ("revision.external_change_detection", "atomicity"),
    ):
        rec = matrix.get(degraded_cap)
        assert rec is not None, f"Capability {degraded_cap} missing from matrix"
        assert rec.state == "degraded", f"Capability {degraded_cap} state was {rec.state}, expected degraded"
        assert any(expected_kw in lim for lim in rec.limitations), f"Expected keyword '{expected_kw}' in limitations of {degraded_cap}: {rec.limitations}"

    # Capability-gated P2 features are unavailable
    for p2_cap in ("export.dxf", "view.section", "assembly.joints"):
        rec = matrix.get(p2_cap)
        assert rec is not None
        assert rec.state == "unavailable"
        assert "P2" in rec.limitations[0]


def test_falsify_property_and_runtime_facts_never_claim_supported_for_unproven_capabilities():
    probe = {
        "application": "Autodesk Fusion",
        "fusion_version": "2.0.18000",
        "relay_version": "1.0.0",
        "platform": "Windows",
        "probe_facts": {
            "has_app": True,
            "has_active_document": True,
            "has_adsk_fusion": True,
            "has_design_access": True,
            "has_timeline_access": True,
            "has_entity_token_resolver": True,
            "has_sketch_access": True,
            "has_camera": True,
            "has_viewport_conversion": True,
            "has_selection_primitives": True,
            "has_command_preview": True,
            "has_attributes": True,
            "has_undo_redo": True,
            "has_mutation_indicators": True,
            # Property/object presence facts must NOT claim supported without safe non-mutating semantic contract proof
            "camera_runtime_verified": True,
            "has_active_camera": True,
            "has_active_viewport": True,
            "viewport_conversion_verified": True,
            "has_viewport_conversion_context": True,
            "selection_runtime_verified": True,
            "has_active_selections_context": True,
            "has_user_interface": True,
            "preview_hooks_verified": True,
            "attributes_runtime_verified": True,
            "has_attributes_context": True,
            "undo_redo_verified": True,
            "has_undo_redo_context": True,
            "mutation_indicators_verified": True,
            "has_measure_manager": True,
            "has_sketch_text": True,
        },
    }
    matrix = CapabilityMatrix.from_probe(probe)

    # Only verified document/design access capabilities become supported:
    for cap_name in (
        "entity.token_resolver",
        "design.access",
        "timeline.access",
        "sketch.access",
        "revision.mutation_indicators",
    ):
        rec = matrix.get(cap_name)
        assert rec is not None, f"Capability {cap_name} missing from matrix"
        assert rec.state == "supported", f"Capability {cap_name} was {rec.state}, expected supported with direct evidence"

    # Finding 2: Property existence (activeSelections/count, Attributes collection/add/count, camera eye/target/upVector,
    # viewport conversion methods, preview/undo API) is insufficient; must remain degraded with explicit limitations
    for degraded_cap in (
        "view.camera",
        "view.viewport_conversion",
        "selection.primitives",
        "transaction.preview_hooks",
        "metadata.attributes",
        "transaction.undo_redo",
    ):
        rec = matrix.get(degraded_cap)
        assert rec is not None, f"Capability {degraded_cap} missing from matrix"
        assert rec.state == "degraded", f"Capability {degraded_cap} was {rec.state}, expected degraded"
        assert len(rec.limitations) > 0

    # Conservative capabilities remain degraded pending later live feasibility gates / Task 4
    for conservative_cap in (
        "view.pick",
        "transaction.preview_replay",
        "inspect.measure",
        "style.sketch_text",
        "revision.external_change_detection",
    ):
        rec = matrix.get(conservative_cap)
        assert rec is not None
        assert rec.state == "degraded"

    # P2 capabilities remain unavailable
    for p2_cap in ("export.dxf", "view.section", "assembly.joints"):
        rec = matrix.get(p2_cap)
        assert rec is not None
        assert rec.state == "unavailable"


def test_falsify_hasattr_class_existence_never_claims_supported():
    # Only class existence / hasattr facts are provided
    probe = {
        "probe_facts": {
            "has_app": True,
            "has_camera": True,
            "has_viewport_conversion": True,
            "has_selection_primitives": True,
            "has_command_preview": True,
            "has_attributes": True,
            "has_undo_redo": True,
        }
    }
    matrix = CapabilityMatrix.from_probe(probe)

    for cap_name in (
        "view.camera",
        "view.viewport_conversion",
        "selection.primitives",
        "transaction.preview_hooks",
        "metadata.attributes",
        "transaction.undo_redo",
    ):
        rec = matrix.get(cap_name)
        assert rec is not None
        assert rec.state == "degraded", f"Capability {cap_name} must NOT be supported from hasattr alone; got {rec.state}"
        assert len(rec.limitations) > 0


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


def test_falsify_finding_6_duplicate_names_rejected():
    rec1 = CapabilityRecord(name="view.pick", state="degraded")
    rec2 = CapabilityRecord(name="view.pick", state="supported")

    with pytest.raises(ValueError, match="Duplicate capability record name: 'view.pick'"):
        CapabilityMatrix([rec1, rec2])


def test_falsify_finding_6_matrix_is_immutable_and_readonly():
    rec = CapabilityRecord(name="design.access", state="supported")
    matrix = CapabilityMatrix([rec])

    # Cannot set attributes
    with pytest.raises(TypeError, match="CapabilityMatrix is immutable and read-only"):
        matrix.new_attr = "val"  # type: ignore[attr-defined]

    # Cannot delete attributes
    with pytest.raises(TypeError, match="CapabilityMatrix is immutable and read-only"):
        del matrix._identity

    # _records MappingProxyType cannot be mutated
    with pytest.raises(TypeError):
        matrix._records["new_key"] = rec  # type: ignore[index]

    # Matrix mapping operations work read-only
    assert "design.access" in matrix
    assert len(matrix) == 1
    assert matrix["design.access"] == rec
    with pytest.raises(KeyError):
        _ = matrix["missing"]


def test_falsify_finding_5_identity_normalization_and_truthful_facts():
    # 1. probe_facts is normalized into probe_details and extra="forbid" does not reject it
    identity = FusionRuntimeIdentity.model_validate({
        "application": "Autodesk Fusion",
        "fusion_version": "2.0.18000",
        "probe_facts": {"has_app": True, "custom_fact": "val"},
    })
    assert identity.probe_details.get("has_app") is True
    assert identity.probe_details.get("custom_fact") == "val"
    assert identity.relay_version is None  # Truthful None, no fake "1.0.0"
    assert identity.platform is None  # Truthful None, no fake "Windows"

    # 2. Unknown fields still fail validation with extra="forbid"
    with pytest.raises(ValidationError):
        FusionRuntimeIdentity.model_validate({
            "application": "Autodesk Fusion",
            "completely_unknown_field": 123,
        })


def test_falsify_finding_2_probe_failure_yields_unavailable_with_limitations():
    # Probe failed with error
    probe_failed = {
        "adsk_core_probe_error": "No module named 'adsk'",
        "probe_facts": {
            "adsk_core_probe_error": "No module named 'adsk'",
        },
    }
    matrix = CapabilityMatrix.from_probe(probe_failed)
    assert len(matrix.records) == 19

    for rec in matrix.records:
        assert rec.state == "unavailable", f"Expected {rec.name} to be unavailable on probe failure"
        assert any("adsk" in lim for lim in rec.limitations), f"Expected error limitation in {rec.name}"


def test_falsify_finding_3_load_bearing_pick_and_transaction_not_contract_supported():
    # Even if every single possible hasattr flag is injected as True
    matrix = CapabilityMatrix.from_probe({
        "application": "Autodesk Fusion",
        "fusion_version": "2.0.18000",
        "probe_facts": {
            "has_app": True,
            "has_selection_primitives": True,
            "has_viewport_conversion": True,
            "has_command_preview": True,
            "has_undo_redo": True,
            "has_mutation_indicators": True,
            "has_timeline_access": True,
            "has_export_manager": True,
            "has_section_view": True,
            "has_joint_access": True,
            "has_sketch_text": True,
            "has_measure_manager": True,
            "has_design_access": True,
        },
    })
    # Pick must NOT be contract-level supported
    pick = matrix.get("view.pick")
    assert pick is not None
    assert pick.state != "supported"
    assert pick.state == "degraded"

    # Transaction preview_replay must NOT be contract-level supported
    tx = matrix.get("transaction.preview_replay")
    assert tx is not None
    assert tx.state != "supported"
    assert tx.state == "degraded"

    # Measure and SketchText must NOT be contract-level supported from hasattr alone
    assert matrix.get("inspect.measure").state == "degraded"
    assert matrix.get("style.sketch_text").state == "degraded"

    # Revision external change detection must NOT be contract-level supported from hasattr alone
    assert matrix.get("revision.external_change_detection").state == "degraded"

    # P2 capabilities must NOT be contract-level supported from hasattr alone
    assert matrix.get("export.dxf").state == "unavailable"
    assert matrix.get("view.section").state == "unavailable"
    assert matrix.get("assembly.joints").state == "unavailable"


def test_pick_becomes_supported_only_after_runtime_raycast_verification():
    base = {
        "application": "Autodesk Fusion",
        "fusion_version": "2.0.18000",
        "probe_facts": {
            "has_app": True,
            "has_adsk_fusion": True,
            "has_design_access": True,
            "has_viewport_conversion": True,
        },
    }
    degraded = CapabilityMatrix.from_probe(base).get("view.pick")
    assert degraded is not None
    assert degraded.state == "degraded"

    verified = {**base, "probe_facts": {**base["probe_facts"], "pick_runtime_verified": True}}
    supported = CapabilityMatrix.from_probe(verified).get("view.pick")
    assert supported is not None
    assert supported.state == "supported"
    assert supported.implementation == "viewport-raycast"
    assert supported.limitations == ()


def test_read_capability_probe_reuses_verified_real_fusion_design_resolver():
    from app.fusion_cad.scripts import FusionCadScriptBundle

    script = FusionCadScriptBundle().build(
        "read", {"node_id": "desk-1", "operation": "capabilities"}
    )
    start = script.index("def probe_runtime():")
    end = script.index("def run():", start)
    probe = script[start:end]
    assert "design = _fusion_design_from_context(app, doc)" in probe
    assert "products.itemByClass" not in probe
