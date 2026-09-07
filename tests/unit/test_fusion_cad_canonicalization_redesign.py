from __future__ import annotations

import json
import traceback
from unittest.mock import MagicMock

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.revisions import compute_model_fingerprint
from app.fusion_cad.service import FusionCadService
from app.fusion_cad.snapshots import compute_structural_hash
from app.tools.fusion import fusion_tools

# ---------------------------------------------------------------------------
# 1. Ordered sequence preservation vs unordered entity collections
# ---------------------------------------------------------------------------


def test_transform_matrix_permutation_changes_structural_hash_and_fingerprint():
    """Matrix / transform permutations must produce distinct structural hashes and model fingerprints.

    Generic canonicalizers that sort every list/tuple collapse row/col permutations.
    """
    matrix_a = [
        [1.0, 0.0, 0.0, 10.0],
        [0.0, 1.0, 0.0, 20.0],
        [0.0, 0.0, 1.0, 30.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    # Permute translation coordinates: (20.0, 10.0) instead of (10.0, 20.0)
    matrix_b = [
        [1.0, 0.0, 0.0, 20.0],
        [0.0, 1.0, 0.0, 10.0],
        [0.0, 0.0, 1.0, 30.0],
        [0.0, 0.0, 0.0, 1.0],
    ]

    payload_a = {
        "document_ref": "doc_main",
        "model_revision": "rev_1",
        "occurrences": [
            {
                "name": "Occ1",
                "full_path_name": "Occ1",
                "transform": matrix_a,
                "is_visible": True,
            }
        ],
    }
    payload_b = {
        "document_ref": "doc_main",
        "model_revision": "rev_1",
        "occurrences": [
            {
                "name": "Occ1",
                "full_path_name": "Occ1",
                "transform": matrix_b,
                "is_visible": True,
            }
        ],
    }

    # Task 4 Model fingerprint
    fp_a = compute_model_fingerprint(payload_a)
    fp_b = compute_model_fingerprint(payload_b)
    assert fp_a != fp_b, "Transform permutation must change model fingerprint"

    # Task 6 Structural hash
    hash_a = compute_structural_hash(payload_a)
    hash_b = compute_structural_hash(payload_b)
    assert hash_a != hash_b, "Transform permutation must change structural hash"


def test_point_coordinate_permutation_changes_structural_hash_and_fingerprint():
    """Point / vector coordinate permutations (e.g. [1.0, 2.0, 3.0] vs [3.0, 2.0, 1.0])
    must produce distinct structural hashes and model fingerprints.
    """
    payload_a = {
        "document_ref": "doc_main",
        "model_revision": "rev_1",
        "sketches": [
            {
                "name": "Sketch1",
                "points": [[1.0, 2.0, 3.0]],
            }
        ],
        "bodies": [
            {
                "name": "Body1",
                "center_of_mass": [1.0, 2.0, 3.0],
            }
        ],
    }
    payload_b = {
        "document_ref": "doc_main",
        "model_revision": "rev_1",
        "sketches": [
            {
                "name": "Sketch1",
                "points": [[3.0, 2.0, 1.0]],
            }
        ],
        "bodies": [
            {
                "name": "Body1",
                "center_of_mass": [3.0, 2.0, 1.0],
            }
        ],
    }

    # Task 4 Model fingerprint
    fp_a = compute_model_fingerprint(payload_a)
    fp_b = compute_model_fingerprint(payload_b)
    assert fp_a != fp_b, (
        "Point/vector coordinate permutation must change model fingerprint"
    )

    # Task 6 Structural hash
    hash_a = compute_structural_hash(payload_a)
    hash_b = compute_structural_hash(payload_b)
    assert hash_a != hash_b, (
        "Point/vector coordinate permutation must change structural hash"
    )


def test_component_path_sequence_permutation_changes_structural_hash():
    """Component paths represent ordered hierarchy trees. Permuting path order must change hash."""
    path_a = ["Root", "SubA", "SubB"]
    path_b = ["Root", "SubB", "SubA"]

    payload_a = {
        "document_ref": "doc_main",
        "model_revision": "rev_1",
        "components": [
            {"name": "CompB", "component_path": path_a},
        ],
    }
    payload_b = {
        "document_ref": "doc_main",
        "model_revision": "rev_1",
        "components": [
            {"name": "CompB", "component_path": path_b},
        ],
    }

    hash_a = compute_structural_hash(payload_a)
    hash_b = compute_structural_hash(payload_b)
    assert hash_a != hash_b, "Component path permutation must change structural hash"


def test_explicitly_unordered_entity_collections_reordering_remains_stable():
    """Explicitly unordered entity collections (components, bodies, sketches, parameters)
    must remain invariant to list order permutation in both fingerprint and structural hash.
    """
    c1 = {"name": "AlphaComp", "id": "comp_1"}
    c2 = {"name": "BetaComp", "id": "comp_2"}
    b1 = {"name": "Body1", "component": "AlphaComp", "volume": 100.0}
    b2 = {"name": "Body2", "component": "BetaComp", "volume": 200.0}

    payload_order1 = {
        "document_ref": "doc_main",
        "model_revision": "rev_1",
        "components": [c1, c2],
        "bodies": [b1, b2],
    }
    payload_order2 = {
        "document_ref": "doc_main",
        "model_revision": "rev_1",
        "components": [c2, c1],
        "bodies": [b2, b1],
    }

    assert compute_model_fingerprint(payload_order1) == compute_model_fingerprint(
        payload_order2
    )
    assert compute_structural_hash(payload_order1) == compute_structural_hash(
        payload_order2
    )


# ---------------------------------------------------------------------------
# 2. Duplicate semantic names and ref-keyed mappings multiplicity
# ---------------------------------------------------------------------------


def test_duplicate_semantic_names_preserve_multiplicity_and_value_mutations():
    """When multiple entities share the same semantic name/label, ref-keyed mappings
    must not collapse them into a single entry or overwrite each other.
    Mutations on either duplicate entity must alter the structural hash.
    """
    # Two distinct components both named "Bracket"
    payload_base = {
        "document_ref": "doc_main",
        "model_revision": "rev_1",
        "components": [
            {"name": "Bracket", "ref": "ent_c1"},
            {"name": "Bracket", "ref": "ent_c2"},
        ],
        "visibility": {
            "ent_c1": True,
            "ent_c2": False,
        },
    }

    # Mutate the first duplicate component visibility from True to False
    payload_mut = {
        "document_ref": "doc_main",
        "model_revision": "rev_1",
        "components": [
            {"name": "Bracket", "ref": "ent_c1"},
            {"name": "Bracket", "ref": "ent_c2"},
        ],
        "visibility": {
            "ent_c1": False,
            "ent_c2": False,
        },
    }

    hash_base = compute_structural_hash(payload_base)
    hash_mut = compute_structural_hash(payload_mut)
    assert hash_base != hash_mut, (
        "Mutating value on duplicate semantic name in ref-keyed mapping must change structural hash"
    )


def test_duplicate_semantic_names_remain_stable_across_lifecycle_ref_renames():
    """Duplicate semantic entities must remain invariant when their opaque lifecycle refs rename."""
    payload_l1 = {
        "document_ref": "doc_main",
        "model_revision": "rev_1",
        "components": [
            {"name": "Bracket", "ref": "ent_l1_a", "volume": 10.0},
            {"name": "Bracket", "ref": "ent_l1_b", "volume": 20.0},
        ],
        "visibility": {
            "ent_l1_a": True,
            "ent_l1_b": False,
        },
    }

    payload_l2 = {
        "document_ref": "doc_main",
        "model_revision": "rev_1",
        "components": [
            {"name": "Bracket", "ref": "ent_l2_y", "volume": 20.0},
            {"name": "Bracket", "ref": "ent_l2_x", "volume": 10.0},
        ],
        "visibility": {
            "ent_l2_x": True,
            "ent_l2_y": False,
        },
    }

    assert compute_structural_hash(payload_l1) == compute_structural_hash(payload_l2)


# ---------------------------------------------------------------------------
# 3. Untrusted error boundaries across all 5 paths
# ---------------------------------------------------------------------------

UNPATTERNED_MARKER = "NATIVE_VALUE_X9Y8Z7_NOT_PATTERNED"


def _assert_zero_secret_leakage(exc: Exception, secret: str = UNPATTERNED_MARKER) -> None:
    """Verify that exception contains zero traces of secret/marker in message, details, str, repr,
    or formatted traceback, and has no __cause__ or __context__.
    """
    assert exc.__cause__ is None, f"__cause__ must be None, got {exc.__cause__!r}"
    assert exc.__context__ is None, f"__context__ must be None, got {exc.__context__!r}"

    msg = getattr(exc, "message", str(exc))
    assert secret not in msg, f"Marker leaked in exception message: {msg}"

    details = getattr(exc, "details", {})
    assert secret not in str(details), f"Marker leaked in exception details: {details}"

    exc_str = str(exc)
    assert secret not in exc_str, f"Marker leaked in str(exc): {exc_str}"

    exc_repr = repr(exc)
    assert secret not in exc_repr, f"Marker leaked in repr(exc): {exc_repr}"

    formatted_tb = "".join(traceback.format_exception(exc))
    assert secret not in formatted_tb, (
        f"Marker leaked in formatted traceback: {formatted_tb}"
    )


def test_direct_result_error_boundary_confidentiality():
    """Direct-result failure with arbitrary unpatterned marker in raw error message or details."""
    raw = {
        "status": "failed",
        "error": {
            "code": "FUSION_API_ERROR",
            "message": f"Native API crashed with unpatterned marker: {UNPATTERNED_MARKER}",
            "details": {
                "diagnostic": UNPATTERNED_MARKER,
                "untrusted_info": UNPATTERNED_MARKER,
                "ref": "ent_safe_123",
            },
        },
    }
    with pytest.raises(FusionCadError) as exc_info:
        FusionCadService.decode_domain_result(raw)

    _assert_zero_secret_leakage(exc_info.value)
    assert exc_info.value.code == ErrorCode.FUSION_API_ERROR
    # Safe allowlisted diagnostic must survive
    assert exc_info.value.details.get("ref") == "ent_safe_123"
    # Arbitrary unpatterned fields must not survive
    assert "diagnostic" not in exc_info.value.details
    assert "untrusted_info" not in exc_info.value.details


def test_content_block_error_boundary_confidentiality():
    """Content-block failure with unpatterned marker embedded in JSON text content."""
    raw = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "isError": True,
                        "error": {
                            "code": "REF_STALE",
                            "message": f"Failed with {UNPATTERNED_MARKER}",
                            "details": {
                                "untrusted_field": UNPATTERNED_MARKER,
                                "target": "ent_stale_target",
                            },
                        },
                    }
                ),
            }
        ]
    }
    with pytest.raises(FusionCadError) as exc_info:
        FusionCadService.decode_domain_result(raw)

    _assert_zero_secret_leakage(exc_info.value)
    assert exc_info.value.code == ErrorCode.REF_STALE
    assert exc_info.value.details.get("target") == "ent_stale_target"
    assert "untrusted_field" not in exc_info.value.details


def test_async_terminal_error_boundary_confidentiality():
    """Async-terminal failure payload from desktop node containing unpatterned marker."""
    full = {
        "status": "failed",
        "error": {
            "code": "TRANSACTION_CONFLICT",
            "message": f"Async operation failed: {UNPATTERNED_MARKER}",
            "details": {
                "native_data": UNPATTERNED_MARKER,
                "transaction_id": "tx_safe_456",
                "applied": False,
            },
        },
    }
    err_code, err_msg, err_details = FusionCadService._extract_error_info(full)
    exc = FusionCadError(err_code, err_msg, details=err_details)
    _assert_zero_secret_leakage(exc)
    assert exc.code == ErrorCode.TRANSACTION_CONFLICT
    assert exc.details.get("transaction_id") == "tx_safe_456"
    assert exc.details.get("applied") is False
    assert "native_data" not in exc.details


def test_malformed_result_error_boundary_confidentiality():
    """Malformed non-JSON or non-dict output containing unpatterned marker."""
    # Case 1: non-JSON text content
    raw_text = {
        "content": [
            {
                "type": "text",
                "text": f"Error: crash at {UNPATTERNED_MARKER}",
            }
        ]
    }
    with pytest.raises(FusionCadError) as exc_info:
        FusionCadService.decode_domain_result(raw_text)

    _assert_zero_secret_leakage(exc_info.value)
    assert exc_info.value.code == ErrorCode.FUSION_API_ERROR

    # Case 2: non-dict raw result
    raw_non_dict = f"Not a dict containing {UNPATTERNED_MARKER}"
    with pytest.raises(FusionCadError) as exc_info_nd:
        FusionCadService.decode_domain_result(raw_non_dict)

    _assert_zero_secret_leakage(exc_info_nd.value)
    assert exc_info_nd.value.code == ErrorCode.FUSION_API_ERROR


@pytest.mark.asyncio
async def test_tool_adapter_and_service_validation_error_confidentiality():
    """Tool-adapter and service validation errors with unpatterned marker in input args."""
    # 1. Service request validation
    service = FusionCadService(desktop_nodes=MagicMock())
    invalid_req = {
        "operation": "model_snapshot",
        "node_id": "desk-1",
        "detail": UNPATTERNED_MARKER,
        "untrusted_field": UNPATTERNED_MARKER,
    }
    with pytest.raises(BridgeError) as exc_info_srv:
        service._validate_request_dict(invalid_req, group="read")

    _assert_zero_secret_leakage(exc_info_srv.value)
    assert exc_info_srv.value.code == ErrorCode.INVALID_ARGUMENT
    # Verify validation_errors diagnostic does not echo raw input
    val_errs_srv = exc_info_srv.value.details.get("validation_errors", [])
    assert val_errs_srv, "validation_errors must be present"
    for ve in val_errs_srv:
        assert "input" not in ve, f"Raw input must not be echoed in validation_errors: {ve}"
        assert "ctx" not in ve, f"Context object must not be echoed in validation_errors: {ve}"

    # 2. Tool adapter domain handler validation
    container = MagicMock()
    container.fusion_cad = service
    defs = fusion_tools(container)
    read_tool = next(t for t in defs if t.definition.name == "fusion_read")

    class DummyParams:
        def __init__(self) -> None:
            self.arguments = {"operation": "create", "bad_arg": UNPATTERNED_MARKER}

    class DummyContext:
        request_id = "req_test_123"

    with pytest.raises(BridgeError) as exc_info_tool:
        await read_tool.handler(None, DummyParams(), DummyContext())

    _assert_zero_secret_leakage(exc_info_tool.value)
    assert exc_info_tool.value.code == ErrorCode.INVALID_ARGUMENT
    val_errs_tool = exc_info_tool.value.details.get("validation_errors", [])
    assert val_errs_tool, "validation_errors must be present in tool adapter error"
    for ve in val_errs_tool:
        assert "input" not in ve, f"Raw input must not be echoed in validation_errors: {ve}"
        assert "ctx" not in ve, f"Context object must not be echoed in validation_errors: {ve}"
