from __future__ import annotations

import pytest

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.models import CadResult, ImmutableMapping
from app.fusion_cad.revisions import RevisionTracker
from app.fusion_cad.service import FusionCadService


def _result(data: dict) -> CadResult:
    return CadResult(summary="adapter result", data=ImmutableMapping(data))


def _lineage(ref: str = "text_expected_01", *, current: bool = True) -> dict:
    return {
        "logical_ref": ref,
        "generation": 2,
        "is_current": current,
        "sketch": "ent_sketch_01",
        "sketch_text_id": "ent_sketch_text_01",
        "feature": "ent_feature_01",
        "outputs": ["ent_body_01"],
        "text": "РАСПИСАНИЕ ПЫТОК 😈",
        "font_requested": "Arial",
        "font_used": "Arial",
        "fallback_reason": None,
        "height_mm": 6.0,
    }


def _provenance() -> dict:
    return {
        "creator_tool": "bridge.fusion-cad-agent",
        "creator_operation": "fusion_style:text_update",
        "operation_id": "op_task11_01",
        "transaction_id": "tx_task11_01",
        "logical_object_ref": "text_expected_01",
        "created_revision": "rev_2",
        "tags": [],
    }


@pytest.mark.parametrize(
    "operation", ["text_update", "text_read", "text_extrude", "text_cut"]
)
def test_task11_lineage_must_match_requested_ref_and_be_current(operation):
    service = object.__new__(FusionCadService)
    payload = {"text_ref": "text_expected_01", "logical_object_ref": "text_expected_01"}
    data = {"lineage": _lineage("text_foreign_01", current=False)}
    if operation != "text_read":
        data.update(
            provenance=_provenance(),
            persisted_provenance=_provenance(),
            same_operation_provenance=True,
        )
    with pytest.raises(FusionCadError) as exc:
        service._finalize_style_execution(_result(data), op=operation, payload=payload)
    assert exc.value.code == ErrorCode.FUSION_API_ERROR


def test_task11_update_requires_explicit_single_current_replacement_evidence():
    service = object.__new__(FusionCadService)
    data = {
        "lineage": _lineage(),
        "provenance": _provenance(),
        "persisted_provenance": _provenance(),
        "same_operation_provenance": True,
    }
    with pytest.raises(FusionCadError) as exc:
        service._finalize_style_execution(
            _result(data),
            op="text_update",
            payload={
                "text_ref": "text_expected_01",
                "logical_object_ref": "text_expected_01",
                "provenance": _provenance(),
            },
        )
    assert exc.value.code == ErrorCode.FUSION_API_ERROR


def test_task11_provenance_must_exactly_match_service_prepared_persisted_record():
    service = object.__new__(FusionCadService)
    forged = _provenance() | {"operation_id": "op_forged_02"}
    data = {
        "lineage": _lineage(),
        "provenance": forged,
        "persisted_provenance": forged,
        "same_operation_provenance": True,
        "replacement_evidence": {
            "logical_ref": "text_expected_01",
            "previous_generation": 1,
            "current_generation": 2,
            "previous_generation_is_current": False,
            "current_generation_count": 1,
            "replacement_or_rebind_verified": True,
            "unrelated_legacy_preserved": True,
        },
    }
    with pytest.raises(FusionCadError) as exc:
        service._finalize_style_execution(
            _result(data),
            op="text_update",
            payload={
                "text_ref": "text_expected_01",
                "logical_object_ref": "text_expected_01",
                "provenance": _provenance(),
            },
        )
    assert exc.value.code == ErrorCode.FUSION_API_ERROR


@pytest.mark.parametrize(
    "operation", ["show", "hide", "set", "show_only", "isolate", "restore"]
)
def test_task11_visibility_rejects_empty_adapter_semantics(operation):
    service = object.__new__(FusionCadService)
    payload = {} if operation == "restore" else {"target": "ent_body_01"}
    if operation == "set":
        payload["visible"] = True
    with pytest.raises(FusionCadError) as exc:
        service._finalize_style_execution(_result({}), op=operation, payload=payload)
    assert exc.value.code in {
        ErrorCode.FUSION_API_ERROR,
        ErrorCode.CAPABILITY_UNAVAILABLE,
    }


def test_task11_public_result_is_operation_allowlisted():
    service = object.__new__(FusionCadService)
    evidence = {
        "operation": "show",
        "target_ref": "ent_body_01",
        "requested_visible": True,
        "local_visible": True,
        "parent_visible": True,
        "effective_visible": True,
    }
    result = service._finalize_style_execution(
        _result(
            {
                "visibility": evidence,
                "native_id": "native::secret",
                "path": "/private/model.f3d",
                "adapter_hint": {"foreign": object()},
            }
        ),
        op="show",
        payload={"target": "ent_body_01"},
    )
    assert dict(result.data) == {"visibility": evidence}


def test_task11_prepare_reuses_provenance_only_one_command_plan():
    service = object.__new__(FusionCadService)
    service._revision_tracker = RevisionTracker()
    service._revision_tracker.observe("doc_1", "fingerprint-1")
    payload = {
        "text_ref": "text_expected_01",
        "document_ref": "doc_1",
        "expected_revision": "rev_1",
        "transaction_id": "tx_task11_01",
    }
    service._prepare_style_payload(payload, "text_update", "op_task11_01")
    assert payload["metadata_removals"] == []
    assert len(payload["metadata_writes"]) == 1
    assert payload["metadata_writes"][0]["name"] == "provenance"
    assert payload["provenance"] == _provenance()


def test_task11_show_only_publishes_only_verified_scoped_fields():
    service = object.__new__(FusionCadService)
    result = service._finalize_style_execution(
        _result(
            {
                "visibility": {
                    "operation": "show_only",
                    "target_ref": "ent_body_01",
                    "requested_visible": True,
                    "local_visible": True,
                    "parent_visible": True,
                    "effective_visible": True,
                },
                "scope_evidence": {
                    "scope": "own_mutation",
                    "operation": "show_only",
                    "target_ref": "ent_body_01",
                    "captured": [
                        {
                            "ref": "ent_body_02",
                            "local_visible": True,
                            "native_id": "secret",
                        }
                    ],
                    "changed_refs": ["ent_body_02"],
                    "foreign": "/secret/path",
                },
            }
        ),
        op="show_only",
        payload={"target": "ent_body_01"},
    )
    assert "foreign" not in result.data["scope_evidence"]
    assert "native_id" not in result.data["scope_evidence"]["captured"][0]


def test_task11_restore_requires_exact_matching_scoped_state():
    service = object.__new__(FusionCadService)
    data = {
        "visibility": {
            "operation": "restore",
            "state_ref": "visibility_state_01",
            "local_visible": True,
            "parent_visible": True,
            "effective_visible": True,
        },
        "scope_evidence": {
            "scope": "own_mutation",
            "operation": "isolate",
            "state_ref": "visibility_state_01",
            "captured": [{"ref": "ent_body_02", "local_visible": True}],
            "restored": [{"ref": "ent_body_02", "local_visible": False}],
            "changed_refs": ["ent_body_02"],
        },
        "restoration_verified": True,
    }
    with pytest.raises(FusionCadError) as exc:
        service._finalize_style_execution(_result(data), op="restore", payload={})
    assert exc.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
