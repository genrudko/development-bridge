from __future__ import annotations

import traceback
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, ValidationError, model_validator

from app.api.errors import ErrorCode
from app.fusion_cad.errors import (
    FusionCadError,
    format_safe_validation_message,
    get_safe_error_message,
    sanitize_validation_errors,
    trusted_detail,
)
from app.fusion_cad.models import CadResult, ImmutableMapping
from app.fusion_cad.service import FusionCadService

# Fresh arbitrary markers that deliberately do NOT contain words like
# token/secret/native and are NOT registered trusted constants.
MARKER_A = "QUARKZORB_77_alpha_helix"
MARKER_B = "blorp_galaxy_2026_epsilon"
FS_LEAK_PATH = "/opt/bridge/artifacts/leak_9f2c1a.json"


def _assert_no_marker_or_path(exc: Exception) -> None:
    """Assert zero marker/path leakage through message/details/str/repr/traceback."""
    assert exc.__cause__ is None, f"__cause__ must be None, got {exc.__cause__!r}"
    assert exc.__context__ is None, f"__context__ must be None, got {exc.__context__!r}"

    msg = getattr(exc, "message", str(exc))
    details = getattr(exc, "details", {})

    for marker in (
        MARKER_A,
        MARKER_B,
        FS_LEAK_PATH,
        "disk full",
        "artifacts",
        "leak_9f2c1a",
    ):
        assert marker not in msg, f"Marker/path leaked in message: {msg}"
        assert marker not in str(exc), f"Marker/path leaked in str(exc): {exc}"
        assert marker not in repr(exc), f"Marker/path leaked in repr(exc): {exc!r}"
        assert marker not in str(details), (
            f"Marker/path leaked in details: {details}"
        )
        formatted_tb = "".join(traceback.format_exception(exc))
        assert marker not in formatted_tb, (
            f"Marker/path leaked in formatted traceback: {formatted_tb}"
        )


def test_direct_fusion_cad_error_surfaces_only_constant_message_and_trusted_details():
    """RED (finding 1+2): arbitrary short single-line markers and identifier-shaped
    node_id markers must not survive public message/details/str/repr/traceback.
    """
    err = FusionCadError(
        ErrorCode.FUSION_API_ERROR,
        f"Native API crashed with {MARKER_A}",
        details={
            "node_id": MARKER_A,
            "status": "succeeded",
            "ref": "ent_ok_1",
            "untrusted": MARKER_B,
        },
    )

    _assert_no_marker_or_path(err)

    # Public message is a constant trusted message derived from the error code, never raw text.
    assert err.message == get_safe_error_message(ErrorCode.FUSION_API_ERROR)
    # Generic identifier-shape values are default-denied without explicit provenance.
    assert "node_id" not in err.details
    assert "untrusted" not in err.details
    # Strong opaque refs and known constant status survive semantic field handling.
    assert err.details.get("ref") == "ent_ok_1"
    assert err.details.get("status") == "succeeded"


def test_validation_error_never_copies_verbatim_msg_input_or_ctx():
    """RED (finding 3): validator-controlled text must never be copied verbatim
    into public validation errors; expose safe loc/type and constant wording only.
    """

    class _DemoModel(BaseModel):
        node_id: str
        mode: str

        @model_validator(mode="after")
        def _reject(self) -> _DemoModel:
            raise ValueError(f"rejected mode value carrying marker {MARKER_B}")

    with pytest.raises(ValidationError) as exc_info:
        _DemoModel.model_validate({"node_id": "desk-1", "mode": "crash"})
    raw_errors = exc_info.value.errors()

    err = FusionCadError(
        ErrorCode.INVALID_ARGUMENT,
        format_safe_validation_message("Invalid read request payload", raw_errors),
        details={"validation_errors": sanitize_validation_errors(raw_errors)},
    )

    _assert_no_marker_or_path(err)

    val_errs = err.details.get("validation_errors", [])
    assert val_errs, "validation_errors must be present"
    for ve in val_errs:
        # No raw input/ctx/exception objects in public validation diagnostics.
        assert "input" not in ve, f"Raw input must not be echoed: {ve}"
        assert "ctx" not in ve, f"Context must not be echoed: {ve}"
        # Values are constant trusted wording; arbitrary validator text never survives.
        assert MARKER_B not in str(ve.get("msg", "")), f"Validator text leaked: {ve}"
    assert err.__cause__ is None
    assert err.__context__ is None


def test_external_result_storage_failure_never_interpolates_exception_text_or_path():
    """RED (finding 4): external-result storage failures must never interpolate
    low-level exception text or filesystem paths into public errors.
    """
    desktop = MagicMock()
    desktop.store_external_result = MagicMock(
        side_effect=OSError(f"Failed to write {FS_LEAK_PATH}: disk full")
    )
    cad_service = FusionCadService(desktop)

    cad_result = CadResult(
        api_version="fusion.cad/v1",
        status="succeeded",
        summary="binary read result",
        data=ImmutableMapping({"blob": "AQIDBAU="}),
    )

    with pytest.raises(FusionCadError) as exc_info:
        cad_service._finalize_completed_execution(
            cad_result,
            effective_bundle_group="inspect",
            op="describe",
            payload={"operation": "describe"},
            node_id="desk-1",
        )

    err = exc_info.value
    _assert_no_marker_or_path(err)
    assert err.code == ErrorCode.INTERNAL_ERROR
    assert err.message == "Failed to externalize binary result payload"
    assert err.__cause__ is None
    assert err.__context__ is None


def test_trusted_provenance_details_survive_only_with_explicit_marker():
    """GREEN support: dynamic internal metadata survives ONLY through explicit
    trusted provenance (trusted_detail); unknown keys/values fail closed.
    """
    err = FusionCadError(
        ErrorCode.CAPABILITY_UNAVAILABLE,
        details={
            "node_id": trusted_detail("desk-7"),
            "capability": trusted_detail("design.access"),
            "untrusted_id": "desk-7",
            "outcome": "stale",
            "matched_count": 2,
        },
    )
    assert err.details.get("node_id") == "desk-7"
    assert err.details.get("capability") == "design.access"
    assert err.details.get("outcome") == "stale"
    assert err.details.get("matched_count") == 2
    assert "untrusted_id" not in err.details
    assert err.__cause__ is None
    assert err.__context__ is None