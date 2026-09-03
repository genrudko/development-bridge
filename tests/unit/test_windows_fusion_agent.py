from __future__ import annotations

import asyncio
import base64
import json
import urllib.error

import pytest

from agents.windows_fusion_agent import (
    INLINE_RESULT_BYTES,
    RESULT_CHUNK_BYTES,
    ResultOutbox,
    _PersistentHTTPSChannel,
    flush_outbox,
    keepalive,
    submit_result_safely,
)


class FlakyResultBridge:
    def __init__(self) -> None:
        self.attempts = 0

    async def post(self, action, body=None, query=""):
        assert action == "result"
        self.attempts += 1
        if self.attempts < 6:
            raise urllib.error.URLError("temporary")
        return {"accepted": True}


@pytest.mark.asyncio
async def test_result_submission_retries_transient_delivery(monkeypatch):
    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_wait)
    bridge = FlakyResultBridge()
    assert await submit_result_safely(bridge, "cmd-1", {"ok": True}) is True
    assert bridge.attempts == 6


@pytest.mark.asyncio
async def test_exhausted_delivery_is_bounded_and_outboxed(tmp_path, monkeypatch):
    async def no_wait(_seconds): return None
    monkeypatch.setattr(asyncio, "sleep", no_wait)
    class OfflineBridge:
        attempts = 0
        async def post(self, action, body=None, query=""):
            self.attempts += 1
            raise urllib.error.URLError("offline")
    bridge = OfflineBridge()
    outbox = ResultOutbox(tmp_path / "outbox")
    assert await submit_result_safely(bridge, "cmd-saved", {"ok": True}, outbox=outbox, max_attempts=3) is False
    assert bridge.attempts == 3
    assert outbox.entries() == [("cmd-saved", {"ok": True})]


@pytest.mark.asyncio
async def test_large_result_uploads_safe_chunks_then_small_reference(tmp_path):
    calls, uploaded = [], bytearray()
    class UploadBridge:
        async def post(self, action, body=None, query=""):
            calls.append((action, body))
            if action == "result-upload-start": return {"upload_id": "u", "offset": 0}
            if action == "result-upload-chunk":
                chunk = base64.b64decode(body["data"])
                assert len(chunk) <= RESULT_CHUNK_BYTES
                uploaded.extend(chunk)
                return {"offset": len(uploaded)}
            if action == "result-upload-finalize":
                return {"external_result": {"result_id": "r", "size_bytes": len(uploaded), "sha256": "a" * 64}}
            return {"accepted": True}
    result = {"content": [{"type": "text", "text": "x" * INLINE_RESULT_BYTES}]}
    assert await submit_result_safely(UploadBridge(), "cmd-big", result, outbox=ResultOutbox(tmp_path / "outbox"))
    assert json.loads(uploaded) == result
    assert calls[-1][0] == "result" and "content" not in json.dumps(calls[-1][1])


@pytest.mark.asyncio
async def test_small_inline_image_is_externalized_before_result_delivery(tmp_path):
    calls, uploaded = [], bytearray()

    class UploadBridge:
        async def post(self, action, body=None, query=""):
            calls.append((action, body))
            if action == "result-upload-start":
                return {"upload_id": "u-small-image", "offset": 0}
            if action == "result-upload-chunk":
                chunk = base64.b64decode(body["data"])
                uploaded.extend(chunk)
                return {"offset": len(uploaded)}
            if action == "result-upload-finalize":
                return {"external_result": {"result_id": "r-small-image", "size_bytes": len(uploaded), "sha256": "b" * 64}}
            return {"accepted": True}

    result = {
        "content": [{"type": "image", "data": base64.b64encode(b"tiny-image").decode("ascii"), "mimeType": "image/png"}],
        "isError": False,
    }
    assert len(json.dumps(result).encode()) < INLINE_RESULT_BYTES
    assert await submit_result_safely(UploadBridge(), "cmd-small-image", result, outbox=ResultOutbox(tmp_path / "outbox"))
    assert json.loads(uploaded) == result
    assert calls[-1][0] == "result"
    assert "content" not in json.dumps(calls[-1][1])


@pytest.mark.asyncio
async def test_outbox_flush_precedes_next_claim(tmp_path):
    outbox = ResultOutbox(tmp_path / "outbox")
    outbox.save("old", {"ok": True})
    actions = []
    class Bridge:
        async def post(self, action, body=None, query=""):
            actions.append(action)
            return {"accepted": True}
    telemetry = {}
    assert await flush_outbox(Bridge(), outbox, [], telemetry)
    actions.append("claim")
    assert actions == ["result", "claim"]
    assert telemetry == {"result_outbox_count": 0, "result_delivery_degraded": False}


@pytest.mark.asyncio
async def test_late_stale_result_is_discarded_without_error():
    class StaleBridge:
        async def post(self, action, body=None, query=""):
            raise urllib.error.HTTPError("http://bridge", 409, "stale", {}, None)

    assert await submit_result_safely(StaleBridge(), "cmd-old", {"ok": True}) is False


@pytest.mark.asyncio
async def test_keepalive_reregisters_after_bridge_restart():
    registered = asyncio.Event()

    class RestartedBridge:
        async def post(self, action, body=None, query=""):
            if action == "heartbeat":
                raise urllib.error.HTTPError("http://bridge", 404, "missing", {}, None)
            if action == "register":
                assert body == {"fusion_available": True, "tools": [{"name": "fusion_mcp_read"}]}
                registered.set()
                return {}
            raise AssertionError(action)

    task = asyncio.create_task(keepalive(RestartedBridge(), [{"name": "fusion_mcp_read"}], 0.001))
    try:
        await asyncio.wait_for(registered.wait(), 0.2)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

@pytest.mark.asyncio
async def test_result_delivery_reregisters_node_after_bridge_restart(monkeypatch):
    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_wait)

    class RestartBridge:
        def __init__(self):
            self.actions = []
            self.result_attempts = 0

        async def post(self, action, body=None, query=""):
            self.actions.append(action)
            if action == "result":
                self.result_attempts += 1
                if self.result_attempts == 1:
                    raise urllib.error.HTTPError("http://bridge", 404, "node missing", {}, None)
                return {"accepted": True}
            if action == "register":
                assert body == {"fusion_available": True, "tools": [{"name": "fusion_mcp_read"}]}
                return {}
            raise AssertionError(action)

    bridge = RestartBridge()
    assert await submit_result_safely(
        bridge, "cmd-restart", {"ok": True}, [{"name": "fusion_mcp_read"}]
    ) is True
    assert bridge.actions == ["result", "register", "result"]


@pytest.mark.asyncio
async def test_keepalive_marks_fusion_unavailable_and_requests_reconnect(monkeypatch):
    seen = asyncio.Event()
    reconnect = asyncio.Event()

    async def no_fusion(_url):
        return False

    monkeypatch.setattr("agents.windows_fusion_agent.fusion_endpoint_available", no_fusion)

    class Bridge:
        async def post(self, action, body=None, query=""):
            assert action == "heartbeat"
            assert body == {"fusion_available": False}
            seen.set()
            return {}

    task = asyncio.create_task(
        keepalive(Bridge(), [{"name": "fusion_mcp_read"}], 0.001, "http://127.0.0.1:27182/mcp", reconnect)
    )
    try:
        await asyncio.wait_for(seen.wait(), 0.2)
        assert reconnect.is_set()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


def test_result_outbox_preserves_cyrillic_utf8(tmp_path):
    outbox = ResultOutbox(tmp_path / "outbox")
    result = {
        "content": [{"type": "text", "text": "Понедельник — расписание №1"}],
        "isError": False,
    }
    path = outbox.save("cmd-unicode", result)

    assert outbox.entries() == [("cmd-unicode", result)]
    raw = path.read_text(encoding="utf-8")
    assert "Понедельник" in raw
    assert "Ð" not in raw


def test_persistent_https_channel_preserves_cyrillic_json_both_directions():
    reply = {"command": {"arguments": {"script": "text = 'Понедельник — №1'"}}}

    class Response:
        status = 200
        reason = "OK"
        headers = None

        def read(self):
            return json.dumps(reply, ensure_ascii=False).encode("utf-8")

    class Connection:
        def __init__(self):
            self.body = None

        def request(self, method, path, body=None, headers=None):
            assert method == "POST"
            self.body = body

        def getresponse(self):
            return Response()

        def close(self):
            return None

    channel = _PersistentHTTPSChannel("https://bridge.example/mcp", "secret")
    connection = Connection()
    channel._connection = connection
    outbound = {"caption": "Привет, мир — №1"}

    result = channel.post("/claim", outbound)

    assert json.loads(connection.body.decode("utf-8")) == outbound
    assert result == reply
    assert result["command"]["arguments"]["script"] == "text = 'Понедельник — №1'"
