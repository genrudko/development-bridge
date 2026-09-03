from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
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
    assert status["result_delivery_degraded"] is False
    assert status["result_outbox_count"] == 0
    assert status["last_result_delivery"] is not None
    assert status["last_claim"] is not None


@pytest.mark.asyncio
async def test_external_upload_validates_and_accepts_verified_result(tmp_path):
    service = DesktopNodeService(configured(call_timeout_seconds=1, result_artifact_directory=tmp_path))
    await service.register("desk-1", [{"name": "read"}], True, {"result_delivery_degraded": True, "result_outbox_count": 1})
    call = asyncio.create_task(service.call("desk-1", "read", {}))
    command = await service.claim("desk-1", .2)
    raw = json.dumps({"content": [{"type": "text", "text": "full"}]}).encode()
    upload = service.begin_result_upload("desk-1", command["command_id"], len(raw), hashlib.sha256(raw).hexdigest())
    with pytest.raises(BridgeError, match="offset"):
        service.append_result_upload("desk-1", upload["upload_id"], 1, base64.b64encode(raw).decode())
    with pytest.raises(BridgeError, match="chunk size"):
        service.append_result_upload("desk-1", upload["upload_id"], 0, base64.b64encode(raw + b"x").decode())
    service.append_result_upload("desk-1", upload["upload_id"], 0, base64.b64encode(raw).decode())
    completed = service.finalize_result_upload("desk-1", upload["upload_id"])
    await service.submit_result("desk-1", command["command_id"], completed)
    assert (await call)["external_result"]["size_bytes"] == len(raw)
    assert service.status("desk-1")["result_outbox_count"] == 1

    pending = asyncio.create_task(service.call("desk-1", "read", {}))
    second = await service.claim("desk-1", .2)
    bad = service.begin_result_upload("desk-1", second["command_id"], len(raw), "0" * 64)
    service.append_result_upload("desk-1", bad["upload_id"], 0, base64.b64encode(raw).decode())
    with pytest.raises(BridgeError, match="SHA-256 mismatch"):
        service.finalize_result_upload("desk-1", bad["upload_id"])
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending


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


@pytest.mark.asyncio
async def test_external_result_exposes_image_as_separate_resource(tmp_path):
    service = DesktopNodeService(
        configured(call_timeout_seconds=1, result_artifact_directory=tmp_path),
        public_base_url="https://bridge.example",
        endpoint="/mcp",
    )
    await service.register("desk-1", [{"name": "screenshot"}], True)
    call = asyncio.create_task(service.call("desk-1", "screenshot", {}))
    command = await service.claim("desk-1", 0.2)
    png = b"\x89PNG\r\n\x1a\nimage-bytes"
    value = {
        "content": [{
            "type": "image",
            "data": base64.b64encode(png).decode("ascii"),
            "mimeType": "image/png",
        }],
        "isError": False,
    }
    raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
    upload = service.begin_result_upload(
        "desk-1", command["command_id"], len(raw), hashlib.sha256(raw).hexdigest()
    )
    service.append_result_upload(
        "desk-1", upload["upload_id"], 0, base64.b64encode(raw).decode("ascii")
    )
    completed = service.finalize_result_upload("desk-1", upload["upload_id"])
    await service.submit_result("desk-1", command["command_id"], completed)
    reference = await call

    full, metadata = service.external_result(reference["external_result"])
    assert full == value
    assert len(metadata["resources"]) == 1
    resource = metadata["resources"][0]
    assert resource["mime_type"] == "image/png"
    assert resource["file_name"].endswith(".png")
    token = resource["uri"].rsplit("/", 1)[-1]
    path, item = service.resolve_external_export(token)
    assert path.read_bytes() == png
    assert item["mime_type"] == "image/png"


def test_expired_recovered_result_removes_orphaned_image_files(tmp_path):
    service = DesktopNodeService(configured(
        result_artifact_directory=tmp_path,
        result_artifact_ttl_seconds=60,
    ))
    result_id = "abcdefghijklmnop"
    result_path = tmp_path / f"{result_id}.json"
    image_path = tmp_path / f"{result_id}-image-0.png"
    result_path.write_text('{"content":[]}', encoding="utf-8")
    image_path.write_bytes(b"old-image")
    old = time.time() - 120
    os.utime(result_path, (old, old))
    os.utime(image_path, (old, old))

    with pytest.raises(BridgeError, match="unavailable"):
        service.external_result({"result_id": result_id})
    assert not result_path.exists()
    assert not image_path.exists()
