from __future__ import annotations

import asyncio
import urllib.error

import pytest

from agents.windows_fusion_agent import keepalive, submit_result_safely


class FlakyResultBridge:
    def __init__(self) -> None:
        self.attempts = 0

    async def post(self, action, body=None, query=""):
        assert action == "result"
        self.attempts += 1
        if self.attempts < 3:
            raise urllib.error.URLError("temporary")
        return {"accepted": True}


@pytest.mark.asyncio
async def test_result_submission_retries_transient_delivery(monkeypatch):
    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_wait)
    bridge = FlakyResultBridge()
    assert await submit_result_safely(bridge, "cmd-1", {"ok": True}) is True
    assert bridge.attempts == 3


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
