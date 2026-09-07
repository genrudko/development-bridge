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


@pytest.mark.asyncio
async def test_external_result_exposes_live_relay_snake_case_image_resource(tmp_path):
    service = DesktopNodeService(
        configured(call_timeout_seconds=1, result_artifact_directory=tmp_path),
        public_base_url="https://bridge.example",
        endpoint="/mcp",
    )
    await service.register("desk-1", [{"name": "fusion_mcp_read"}], True)
    call = asyncio.create_task(service.call("desk-1", "fusion_mcp_read", {"queryType": "screenshot"}))
    command = await service.claim("desk-1", 0.2)
    png = b"\x89PNG\r\n\x1a\nlive-relay-image"
    value = {
        "content": [{
            "type": "image",
            "data": base64.b64encode(png).decode("ascii"),
            "mime_type": "image/png",
        }],
        "is_error": False,
        "result_type": "complete",
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

    _, metadata = service.external_result(reference["external_result"])
    assert len(metadata["resources"]) == 1
    resource = metadata["resources"][0]
    assert resource["mime_type"] == "image/png"
    token = resource["uri"].rsplit("/", 1)[-1]
    path, _ = service.resolve_external_export(token)
    assert path.read_bytes() == png


def test_external_result_accepts_documented_base64_data_image_shape(tmp_path):
    service = DesktopNodeService(
        configured(result_artifact_directory=tmp_path),
        public_base_url="https://bridge.example",
        endpoint="/mcp",
    )
    png = b"\x89PNG\r\n\x1a\ndocumented-shape"
    value = {
        "content": [{
            "type": "image",
            "base64Data": base64.b64encode(png).decode("ascii"),
            "mimeType": "image/png",
        }],
        "isError": False,
    }
    result_id = service._store_result_value("desk-1", "command-1", value)

    _, metadata = service.external_result({"result_id": result_id})
    assert len(metadata["resources"]) == 1
    resource = metadata["resources"][0]
    token = resource["uri"].rsplit("/", 1)[-1]
    path, item = service.resolve_external_export(token)
    assert path.read_bytes() == png
    assert item["mime_type"] == "image/png"


def test_extract_binary_resources_does_not_false_positive_on_ordinary_base64():
    from app.desktop_nodes.service import extract_binary_resources, has_binary_data

    # 1. Base64-encoded UTF-8 text with bytes > 127
    utf8_b64 = base64.b64encode("ПЫТОК 😈 привет мир это текстовая строка".encode()).decode("ascii")
    payload_utf8 = {"summary": "read", "details": {"comment": utf8_b64}}
    assert extract_binary_resources(payload_utf8) == []
    assert has_binary_data(payload_utf8) is False

    # 2. Base64 string starting with "Qk" that is ASCII text "BOOM"
    boom_b64 = base64.b64encode(b"BOOM").decode("ascii")  # "Qk9PTQ=="
    payload_boom = {"note": boom_b64}
    assert extract_binary_resources(payload_boom) == []
    assert has_binary_data(payload_boom) is False

    # 3. Base64-encoded plain ASCII text
    ascii_b64 = base64.b64encode(b"Hello world, this is a normal base64 encoded string!").decode("ascii")
    payload_ascii = {"message": ascii_b64}
    assert extract_binary_resources(payload_ascii) == []
    assert has_binary_data(payload_ascii) is False

    # 4. Text data URI
    text_data_uri = "data:text/plain;base64," + base64.b64encode(b"Plain text").decode("ascii")
    payload_data_uri = {"content": text_data_uri}
    assert extract_binary_resources(payload_data_uri) == []
    assert has_binary_data(payload_data_uri) is False


def test_extract_binary_resources_extracts_verified_magic_and_explicit_keys():
    from app.desktop_nodes.service import extract_binary_resources

    png_bytes = b"\x89PNG\r\n\x1a\nfake-png-data"
    png_b64 = base64.b64encode(png_bytes).decode("ascii")

    # In generic field, verified magic is extracted
    res = extract_binary_resources({"image": png_b64})
    assert len(res) == 1
    assert res[0].mime_type == "image/png"
    assert res[0].raw_bytes == png_bytes

    # In explicit binary key, data is extracted
    res_explicit = extract_binary_resources({"thumbnail_b64": base64.b64encode(b"raw-thumb").decode("ascii")})
    assert len(res_explicit) == 1
    assert res_explicit[0].raw_bytes == b"raw-thumb"

    # Data URI with image MIME
    res_uri = extract_binary_resources({"uri": f"data:image/png;base64,{png_b64}"})
    assert len(res_uri) == 1
    assert res_uri[0].mime_type == "image/png"
    assert res_uri[0].raw_bytes == png_bytes


def test_extract_binary_resources_unambiguous_keys_without_magic():
    from app.desktop_nodes.service import extract_binary_resources, has_binary_data

    arbitrary_bytes_1 = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09"
    arbitrary_bytes_2 = b"\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19"
    arbitrary_bytes_3 = b"\x20\x21\x22\x23\x24\x25\x26\x27\x28\x29"

    b64_1 = base64.b64encode(arbitrary_bytes_1).decode("ascii")
    b64_2 = base64.b64encode(arbitrary_bytes_2).decode("ascii")
    b64_3 = base64.b64encode(arbitrary_bytes_3).decode("ascii")

    # 1. blob key
    payload_blob = {"blob": b64_1}
    assert has_binary_data(payload_blob) is True
    res_blob = extract_binary_resources(payload_blob)
    assert len(res_blob) == 1
    assert res_blob[0].raw_bytes == arbitrary_bytes_1
    assert res_blob[0].suggested_name == "blob"
    assert res_blob[0].mime_type == "application/octet-stream"

    # 2. bytes key
    payload_bytes = {"bytes": b64_2}
    assert has_binary_data(payload_bytes) is True
    res_bytes = extract_binary_resources(payload_bytes)
    assert len(res_bytes) == 1
    assert res_bytes[0].raw_bytes == arbitrary_bytes_2
    assert res_bytes[0].suggested_name == "bytes"
    assert res_bytes[0].mime_type == "application/octet-stream"

    # 3. base64 key
    payload_base64 = {"base64": b64_3}
    assert has_binary_data(payload_base64) is True
    res_base64 = extract_binary_resources(payload_base64)
    assert len(res_base64) == 1
    assert res_base64[0].raw_bytes == arbitrary_bytes_3
    assert res_base64[0].suggested_name == "base64"
    assert res_base64[0].mime_type == "application/octet-stream"

    # 4. Suffix keys remain working (*_blob, *_bytes, *_base64)
    payload_suffix = {
        "custom_blob": b64_1,
        "payload_bytes": b64_2,
        "encoded_base64": b64_3,
    }
    assert has_binary_data(payload_suffix) is True
    res_suffix = extract_binary_resources(payload_suffix)
    assert len(res_suffix) == 3

    # 5. Non-binary generic 'data' and semantic strings without magic remain not detected
    generic_non_binary = {
        "data": b64_1,  # arbitrary binary in generic 'data' key without magic/MIME is not recognized as binary
        "message": "semantic text",
        "description": b64_2,
    }
    assert extract_binary_resources(generic_non_binary) == []
    assert has_binary_data(generic_non_binary) is False
