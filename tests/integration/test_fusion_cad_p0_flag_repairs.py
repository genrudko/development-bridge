from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.errors import ErrorCode
from app.desktop_nodes.service import DesktopNodeService
from app.fusion_cad.capabilities import CapabilityMatrix
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.models import CadResult, CapabilityRecord
from app.fusion_cad.service import FusionCadService


@pytest.fixture
def desktop() -> DesktopNodeService:
    service = MagicMock(spec=DesktopNodeService)
    service.call = AsyncMock()
    service.submit = AsyncMock()
    return service


def _service(desktop: DesktopNodeService, *capabilities: str) -> FusionCadService:
    service = FusionCadService(desktop)
    service.set_node_capabilities(
        "desk-1",
        CapabilityMatrix.from_records(
            [CapabilityRecord(name=name, state="supported") for name in capabilities]
        ),
    )
    return service


@pytest.mark.asyncio
async def test_text_update_position_rejected_before_dispatch(desktop):
    service = _service(
        desktop, "style.text_update", "revision.external_change_detection"
    )
    service.revision_tracker.observe("doc_1", "fp_1")

    with pytest.raises(FusionCadError) as exc:
        await service.execute(
            {
                "node_id": "desk-1",
                "document_ref": "doc_1",
                "operation": "text_update",
                "text_ref": "text_1",
                "position": {
                    "x": 1,
                    "y": 2,
                    "z": 3,
                    "frame": {"space": "world"},
                },
                "expected_revision": "rev_1",
            },
            group="style",
        )

    assert exc.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    desktop.call.assert_not_awaited()
    desktop.submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_snapshot_flags_filter_categories_and_views_reject_before_dispatch(desktop):
    service = _service(desktop, "design.access")
    desktop.call = AsyncMock(
        return_value={
            "api_version": "fusion.cad/v1",
            "status": "succeeded",
            "summary": "Snapshot",
            "document": {"document_ref": "doc_1", "model_revision": "rev_1"},
            "data": {
                "document_ref": "doc_1",
                "model_revision": "rev_1",
                "bodies": [{"name": "Body"}],
                "sketches": [{"name": "Sketch"}],
                "timeline": [{"name": "Feature", "index": 0}],
                "parameters": {"model_parameters": [{"name": "d1", "value": 1}]},
            },
        }
    )
    desktop.submit = desktop.call

    result = await service.execute(
        {
            "node_id": "desk-1",
            "operation": "model_snapshot",
            "include_bodies": False,
            "include_sketches": False,
            "include_features": False,
            "include_parameters": False,
        },
        group="read",
    )
    assert isinstance(result, CadResult)
    for category in ("bodies", "sketches", "features", "parameters"):
        assert category not in result.data

    desktop.call.reset_mock()
    with pytest.raises(FusionCadError) as exc:
        await service.execute(
            {"node_id": "desk-1", "operation": "model_snapshot", "include_views": True},
            group="read",
        )
    assert exc.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    desktop.call.assert_not_awaited()
    desktop.submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_snapshot_filter_flags_survive_async_checkpoint(desktop):
    service = _service(desktop, "design.access")
    captured = {}

    async def queued_submit(node_id, tool_name, arguments, journal=None):
        captured["journal"] = journal
        return {"operation_id": "op_snapshot", "status": "queued"}

    desktop.submit = AsyncMock(side_effect=queued_submit)
    await service.execute(
        {
            "node_id": "desk-1",
            "operation": "model_snapshot",
            "detail": "full",
            "include_bodies": False,
            "include_sketches": False,
            "include_features": False,
            "include_parameters": False,
        },
        group="read",
    )

    context = captured["journal"]["checkpoint"]["finalization_payload"]
    assert context == {
        "operation": "model_snapshot",
        "detail": "full",
        "include_bodies": False,
        "include_sketches": False,
        "include_features": False,
        "include_parameters": False,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("evidence", "fail_on", "blocked"),
    [
        ({"timeline": {"available": True, "rolled_back": False}}, "WARN", False),
        ({"timeline": {"available": False, "rolled_back": False}}, "WARN", True),
        ({"timeline": {"available": False, "rolled_back": False}}, "RED", False),
        ({"timeline": {"available": True, "rolled_back": True}}, "RED", True),
    ],
)
async def test_validate_fail_on_thresholds(desktop, evidence, fail_on, blocked):
    service = _service(desktop, "design.access")
    desktop.call = AsyncMock(
        return_value={
            "api_version": "fusion.cad/v1",
            "status": "succeeded",
            "summary": "Validation",
            "data": {"document_ref": "doc_1", **evidence},
        }
    )
    desktop.submit = desktop.call
    request = {
        "node_id": "desk-1",
        "operation": "run",
        "profiles": ["parametric_health"],
        "fail_on": fail_on,
    }

    if blocked:
        with pytest.raises(FusionCadError) as exc:
            await service.execute(request, group="validate")
        assert exc.value.code == ErrorCode.VALIDATION_FAILED
        assert exc.value.details["validation"]["verdict"] in {"WARN", "RED"}
    else:
        result = await service.execute(request, group="validate")
        assert isinstance(result, CadResult)


def _staged_preview_service(desktop: DesktopNodeService) -> FusionCadService:
    service = _service(
        desktop, "transaction.preview_replay", "revision.external_change_detection"
    )
    rec = service.revision_tracker.observe("doc_1", "fp_1")
    service.revision_tracker.begin_transaction("tx_1", "doc_1", rec.revision, rec.fingerprint)
    service.transaction_store.begin("tx_1", "doc_1", rec.revision, rec.fingerprint, {})
    service.transaction_store.stage(
        "tx_1",
        {
            "action_type": "text_create",
            "text": "Preview",
            "height_mm": 4,
            "position": {"x": 0, "y": 0, "z": 0, "frame": {"space": "world"}},
        },
    )
    return service


@pytest.mark.asyncio
async def test_preview_screenshot_rejected_before_dispatch(desktop):
    service = _staged_preview_service(desktop)
    before = service.transaction_store.get("tx_1")

    with pytest.raises(FusionCadError) as exc:
        await service.execute(
            {
                "node_id": "desk-1",
                "operation": "preview",
                "transaction_id": "tx_1",
                "include_screenshot": True,
            },
            group="transaction",
        )
    assert exc.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    desktop.submit.assert_not_awaited()
    assert service.transaction_store.get("tx_1") == before


@pytest.mark.asyncio
async def test_preview_output_flags_filter_public_result_and_survive_async_checkpoint(desktop):
    service = _staged_preview_service(desktop)
    captured = {}

    async def queued_submit(node_id, tool_name, arguments, journal=None):
        captured["journal"] = journal
        return {"operation_id": "op_preview", "status": "queued"}

    desktop.submit = AsyncMock(side_effect=queued_submit)
    queued = await service.execute(
        {
            "node_id": "desk-1",
            "operation": "preview",
            "transaction_id": "tx_1",
            "include_diff": False,
            "include_validation": False,
        },
        group="transaction",
    )
    assert queued["status"] == "queued"
    context = captured["journal"]["checkpoint"]["finalization_payload"]
    assert context["include_diff"] is False
    assert context["include_validation"] is False

    finalized = service.finalize_terminal_operation(
        {
            "checkpoint": captured["journal"]["checkpoint"],
            "status": "succeeded",
        },
        {
            "api_version": "fusion.cad/v1",
            "status": "succeeded",
            "summary": "Previewed",
            "document": {"document_ref": "doc_1", "model_revision": "rev_1"},
            "data": {"transaction_id": "tx_1", "fingerprint": "fp_1", "applied": False},
            "diff": {"counts": {"bodies": 1}},
            "validation": {"verdict": "GREEN", "summary": "safe"},
        },
    )
    assert isinstance(finalized, CadResult)
    assert finalized.diff is None
    assert finalized.validation is None
