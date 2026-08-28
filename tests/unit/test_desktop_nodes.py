from __future__ import annotations

import asyncio
import time
import pytest

from app.api.errors import BridgeError, ErrorCode
from app.desktop_nodes import DesktopNodeService
from app.settings import DesktopNodeSettings


def configured(**updates):
    return DesktopNodeSettings.model_validate({"token": "secret", **updates})


@pytest.mark.asyncio
async def test_service_roundtrip_discovery_and_tool_result():
    service = DesktopNodeService(configured(call_timeout_seconds=1))
    await service.register("desk-1", [{"name": "make_box", "inputSchema": {"type": "object"}}], True)
    call = asyncio.create_task(service.call("desk-1", "make_box", {"width": 4}))
    command = await service.claim("desk-1", .2)
    assert command is not None
    assert command["tool_name"] == "make_box"
    await service.submit_result("desk-1", command["command_id"], {"content": [{"type": "image", "data": "abc", "mimeType": "image/png"}], "isError": False})
    assert (await call)["content"][0]["type"] == "image"
    assert service.tools("desk-1")["tools"][0]["name"] == "make_box"
    status = service.status("desk-1")
    assert abs(status["last_seen"] - time.time()) < 2
    assert status["age_seconds"] >= 0
    assert status["pending_commands"] == 0
    assert status["claimed_commands"] == 0


@pytest.mark.asyncio
async def test_service_timeout_offline_and_size_bounds():
    service = DesktopNodeService(configured(call_timeout_seconds=.01, offline_after_seconds=2, max_arguments_bytes=1024, max_result_bytes=4096))
    await service.register("desk-1", [{"name": "tool"}], True)
    with pytest.raises(BridgeError) as timeout:
        await service.call("desk-1", "tool", {})
    assert timeout.value.code is ErrorCode.DESKTOP_NODE_TIMEOUT
    service._nodes["desk-1"].last_seen -= 3
    with pytest.raises(BridgeError) as offline:
        await service.call("desk-1", "tool", {})
    assert offline.value.code is ErrorCode.DESKTOP_NODE_OFFLINE
    service._nodes["desk-1"].last_seen = service._now()
    with pytest.raises(BridgeError, match="arguments"):
        await service.call("desk-1", "tool", {"blob": "x" * 2000})


def test_service_fails_closed_without_token():
    service = DesktopNodeService(DesktopNodeSettings())
    with pytest.raises(BridgeError) as raised:
        service.status("desk-1")
    assert raised.value.code is ErrorCode.DESKTOP_NODE_NOT_CONFIGURED


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["register", "heartbeat"])
@pytest.mark.parametrize("invalid_tools", [{"name": "other"}, ["other"], [{"name": ""}], [{"name": "x" * 201}], [{"name": "other", "bad": object()}]])
async def test_invalid_tools_do_not_corrupt_registered_node(operation, invalid_tools):
    service = DesktopNodeService(configured())
    await service.register("desk-1", [{"name": "original"}], True)
    before = service._nodes["desk-1"].last_seen
    with pytest.raises(BridgeError) as raised:
        if operation == "register":
            await service.register("desk-1", invalid_tools, False)
        else:
            await service.heartbeat("desk-1", invalid_tools, False)
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT
    assert service.tools("desk-1")["tools"] == [{"name": "original"}]
    assert service.status("desk-1")["fusion_available"] is True
    assert service._nodes["desk-1"].last_seen == before


@pytest.mark.asyncio
async def test_invalid_registration_and_result_are_rejected_before_state_change():
    service = DesktopNodeService(configured(call_timeout_seconds=1))
    with pytest.raises(BridgeError) as invalid_id:
        await service.register("bad/id", [{"name": "tool"}], True)
    assert invalid_id.value.code is ErrorCode.INVALID_ARGUMENT
    assert service._nodes == {}
    await service.register("desk-1", [{"name": "tool"}], True)
    call = asyncio.create_task(service.call("desk-1", "tool", {}))
    command = await service.claim("desk-1", 0.2)
    with pytest.raises(BridgeError) as invalid_result:
        await service.submit_result("desk-1", command["command_id"], ["not", "an", "object"])
    assert invalid_result.value.code is ErrorCode.INVALID_ARGUMENT
    await service.submit_result("desk-1", command["command_id"], {"ok": True})
    assert await call == {"ok": True}


@pytest.mark.asyncio
async def test_cancelled_call_releases_pending_capacity_and_queue_entry():
    service = DesktopNodeService(configured(call_timeout_seconds=1, max_pending_commands=1))
    await service.register("desk-1", [{"name": "tool"}], True)
    cancelled = asyncio.create_task(service.call("desk-1", "tool", {}))
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    node = service._nodes["desk-1"]
    assert not node.queue
    assert not node.commands
    replacement = asyncio.create_task(service.call("desk-1", "tool", {}))
    command = await service.claim("desk-1", 0.2)
    await service.submit_result("desk-1", command["command_id"], {"ok": True})
    assert await replacement == {"ok": True}
