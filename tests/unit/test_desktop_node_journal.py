from __future__ import annotations

import asyncio

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.desktop_nodes import DesktopNodeService
from app.settings import DesktopNodeSettings


def configured(tmp_path, **updates):
    return DesktopNodeSettings.model_validate({
        "token": "secret",
        "journal_path": tmp_path / "fusion-operations.jsonl",
        "call_timeout_seconds": 0.02,
        **updates,
    })


@pytest.mark.asyncio
async def test_claimed_mutation_timeout_becomes_uncertain(tmp_path):
    service = DesktopNodeService(configured(tmp_path))
    await service.register("desk-1", [{"name": "fusion_mcp_execute"}], True)
    call = asyncio.create_task(service.call(
        "desk-1",
        "fusion_mcp_execute",
        {"featureType": "script"},
        {
            "operation_id": "op-cut-wall-01",
            "summary": "Cut wall pattern",
            "mutation": True,
            "checkpoint": {"expected_features": ["Ajour_Long_Wall"]},
        },
    ))
    command = await service.claim("desk-1", 0.2)
    assert command is not None
    assert command["operation_id"] == "op-cut-wall-01"

    with pytest.raises(BridgeError) as raised:
        await call
    assert raised.value.code is ErrorCode.DESKTOP_NODE_TIMEOUT
    assert raised.value.retryable is False
    assert raised.value.details == {"operation_id": "op-cut-wall-01", "status": "uncertain"}

    status = service.status("desk-1")
    assert status["pending_commands"] == 0
    assert status["last_operation"]["status"] == "uncertain"
    assert status["last_operation"]["checkpoint"] == {"expected_features": ["Ajour_Long_Wall"]}
    assert [item["operation_id"] for item in status["uncertain_operations"]] == ["op-cut-wall-01"]


@pytest.mark.asyncio
async def test_late_result_resolves_uncertain_operation(tmp_path):
    service = DesktopNodeService(configured(tmp_path))
    await service.register("desk-1", [{"name": "fusion_mcp_execute"}], True)
    call = asyncio.create_task(service.call(
        "desk-1",
        "fusion_mcp_execute",
        {},
        {"operation_id": "op-late-01", "mutation": True},
    ))
    command = await service.claim("desk-1", 0.2)
    assert command is not None
    with pytest.raises(BridgeError):
        await call

    await service.submit_result(
        "desk-1", command["command_id"], {"content": [{"type": "text", "text": "done"}], "isError": False}
    )
    status = service.status("desk-1")
    assert status["last_operation"]["status"] == "late_succeeded"
    assert status["last_operation"]["result_sha256"]
    assert status["uncertain_operations"] == []


@pytest.mark.asyncio
async def test_late_result_reconciles_after_bridge_restart(tmp_path):
    settings = configured(tmp_path)
    first = DesktopNodeService(settings)
    await first.register("desk-1", [{"name": "fusion_mcp_execute"}], True)
    call = asyncio.create_task(first.call(
        "desk-1",
        "fusion_mcp_execute",
        {},
        {"operation_id": "op-restart-01", "summary": "Long CAD mutation", "mutation": True},
    ))
    command = await first.claim("desk-1", 0.2)
    assert command is not None
    with pytest.raises(BridgeError):
        await call
    assert first.status("desk-1")["last_operation"]["status"] == "uncertain"

    restarted = DesktopNodeService(settings)
    await restarted.register("desk-1", [{"name": "fusion_mcp_execute"}], True)
    assert restarted.status("desk-1")["last_operation"]["status"] == "uncertain"

    await restarted.submit_result(
        "desk-1", command["command_id"], {"content": [], "isError": False}
    )
    status = restarted.status("desk-1")
    assert status["last_operation"]["operation_id"] == "op-restart-01"
    assert status["last_operation"]["status"] == "late_succeeded"
    assert status["uncertain_operations"] == []


@pytest.mark.asyncio
async def test_duplicate_operation_id_is_rejected(tmp_path):
    service = DesktopNodeService(configured(tmp_path, call_timeout_seconds=1))
    await service.register("desk-1", [{"name": "fusion_mcp_read"}], True)
    first = asyncio.create_task(service.call(
        "desk-1", "fusion_mcp_read", {}, {"operation_id": "op-same", "mutation": False}
    ))
    command = await service.claim("desk-1", 0.2)
    assert command is not None
    await service.submit_result("desk-1", command["command_id"], {"ok": True})
    assert await first == {"ok": True}

    with pytest.raises(BridgeError) as duplicate:
        await service.call("desk-1", "fusion_mcp_read", {}, {"operation_id": "op-same", "mutation": False})
    assert duplicate.value.code is ErrorCode.INVALID_ARGUMENT

@pytest.mark.asyncio
async def test_bridge_restart_marks_claimed_mutation_uncertain_before_result(tmp_path):
    settings = configured(tmp_path, call_timeout_seconds=1)
    first = DesktopNodeService(settings)
    await first.register("desk-1", [{"name": "fusion_mcp_execute"}], True)
    call = asyncio.create_task(first.call(
        "desk-1",
        "fusion_mcp_execute",
        {},
        {"operation_id": "op-live-restart-01", "mutation": True},
    ))
    command = await first.claim("desk-1", 0.2)
    assert command is not None

    restarted = DesktopNodeService(settings)
    await restarted.register("desk-1", [{"name": "fusion_mcp_execute"}], True)
    status = restarted.status("desk-1")
    assert status["last_operation"]["status"] == "uncertain"
    assert status["last_operation"]["recovery_reason"] == "bridge_restarted_after_claim"

    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call
    await restarted.submit_result("desk-1", command["command_id"], {"isError": False, "content": []})
    assert restarted.status("desk-1")["last_operation"]["status"] == "late_succeeded"


@pytest.mark.asyncio
async def test_bridge_restart_marks_unclaimed_queue_orphaned(tmp_path):
    settings = configured(tmp_path, call_timeout_seconds=1)
    first = DesktopNodeService(settings)
    await first.register("desk-1", [{"name": "fusion_mcp_execute"}], True)
    call = asyncio.create_task(first.call(
        "desk-1",
        "fusion_mcp_execute",
        {},
        {"operation_id": "op-queued-restart-01", "mutation": True},
    ))
    await asyncio.sleep(0)

    restarted = DesktopNodeService(settings)
    await restarted.register("desk-1", [{"name": "fusion_mcp_execute"}], True)
    status = restarted.status("desk-1")
    assert status["last_operation"]["status"] == "orphaned"
    assert status["last_operation"]["recovery_reason"] == "bridge_restarted_before_claim"
    assert status["uncertain_operations"] == []
    with pytest.raises(BridgeError) as orphaned_result:
        restarted.operation_result("desk-1", "op-queued-restart-01")
    assert orphaned_result.value.code is ErrorCode.INVALID_ARGUMENT
    assert orphaned_result.value.retryable is False

    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call


@pytest.mark.asyncio
async def test_async_submit_status_and_result_roundtrip(tmp_path):
    service = DesktopNodeService(configured(
        tmp_path,
        call_timeout_seconds=1,
        result_artifact_directory=tmp_path / "results",
    ))
    await service.register("desk-1", [{"name": "fusion_mcp_execute"}], True)

    submitted = await service.submit(
        "desk-1",
        "fusion_mcp_execute",
        {"script": "print('длинная операция')"},
        {"operation_id": "op-async-01", "mutation": True},
    )
    assert submitted["operation_id"] == "op-async-01"
    assert submitted["status"] == "queued"

    command = await service.claim("desk-1", 0.2)
    assert command is not None
    assert service.operation_status("desk-1", "op-async-01")["status"] == "running"

    result = {
        "content": [{"type": "text", "text": "готово"}],
        "isError": False,
    }
    await service.submit_result("desk-1", command["command_id"], result)

    status = service.operation_status("desk-1", "op-async-01")
    assert status["status"] == "succeeded"
    assert status["result_sha256"]
    assert service.operation_result("desk-1", "op-async-01")[0] == result


@pytest.mark.asyncio
async def test_async_submit_survives_synchronous_call_timeout(tmp_path):
    service = DesktopNodeService(configured(
        tmp_path,
        call_timeout_seconds=0.01,
        result_artifact_directory=tmp_path / "results",
    ))
    await service.register("desk-1", [{"name": "fusion_mcp_execute"}], True)
    submitted = await service.submit(
        "desk-1", "fusion_mcp_execute", {},
        {"operation_id": "op-long-running-01", "mutation": True},
    )
    assert submitted == {"operation_id": "op-long-running-01", "status": "queued"}
    command = await service.claim("desk-1", 0.2)
    assert command is not None

    await asyncio.sleep(0.03)
    assert service.operation_status("desk-1", "op-long-running-01")["status"] == "running"

    await service.submit_result(
        "desk-1", command["command_id"],
        {"content": [{"type": "text", "text": "done"}], "isError": False},
    )
    assert service.operation_status("desk-1", "op-long-running-01")["status"] == "succeeded"


@pytest.mark.asyncio
async def test_completed_async_operation_status_and_result_survive_bridge_restart(tmp_path):
    settings = configured(
        tmp_path,
        call_timeout_seconds=0.01,
        result_artifact_directory=tmp_path / "results",
    )
    first = DesktopNodeService(settings)
    await first.register("desk-1", [{"name": "fusion_mcp_execute"}], True)
    await first.submit(
        "desk-1", "fusion_mcp_execute", {},
        {"operation_id": "op-durable-result-01", "mutation": True},
    )
    command = await first.claim("desk-1", 0.2)
    assert command is not None
    result = {
        "content": [{"type": "text", "text": "результат пережил рестарт"}],
        "isError": False,
    }
    await first.submit_result("desk-1", command["command_id"], result)
    assert first.operation_status("desk-1", "op-durable-result-01")["status"] == "succeeded"

    restarted = DesktopNodeService(settings)
    assert restarted.operation_status("desk-1", "op-durable-result-01")["status"] == "succeeded"
    assert restarted.operation_result("desk-1", "op-durable-result-01")[0] == result
