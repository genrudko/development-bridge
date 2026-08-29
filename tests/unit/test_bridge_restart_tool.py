from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.tools.bridge_restart import bridge_restart_tools


class FakeCoordinator:
    def __init__(self):
        self.armed = []

    def validate_channel(self, value):
        assert value == "eod-tooling"
        return value

    async def arm(self, message, *, channel_id, delay_seconds, conflict):
        self.armed.append({"message": message, "channel_id": channel_id, "delay_seconds": delay_seconds, "conflict": conflict})
        return {"state": "pending"}


class FakeRestart:
    async def schedule(self, *, checkpoint=None):
        if checkpoint is not None:
            await checkpoint()
        return {"restart_scheduled": True}


@pytest.mark.asyncio
async def test_explicit_restart_channel_overrides_default_route():
    coordinator = FakeCoordinator()
    container = SimpleNamespace(
        route_registry=SimpleNamespace(resolve=lambda: {"route_id": "ad5x", "channel_id": "telegram-ad5x-g6"}),
        coordinator=coordinator,
        bridge_restart=FakeRestart(),
    )
    tool = bridge_restart_tools(container)[0]
    result = await tool.handler(None, SimpleNamespace(arguments={"channel_id": "eod-tooling"}), SimpleNamespace(request_id="request-1"))
    payload = json.loads(result.content[0].text)
    assert coordinator.armed[0]["channel_id"] == "eod-tooling"
    assert payload["data"]["continuation"] == {"channel_id": "eod-tooling", "state": "pending"}


@pytest.mark.asyncio
async def test_restart_without_override_preserves_default_route_behavior():
    coordinator = FakeCoordinator()
    coordinator.validate_channel = lambda value: value
    container = SimpleNamespace(
        route_registry=SimpleNamespace(resolve=lambda: {"route_id": "ad5x", "channel_id": "telegram-ad5x-g6"}),
        coordinator=coordinator,
        bridge_restart=FakeRestart(),
    )
    tool = bridge_restart_tools(container)[0]
    result = await tool.handler(None, SimpleNamespace(arguments={}), SimpleNamespace(request_id="request-2"))
    payload = json.loads(result.content[0].text)
    assert coordinator.armed[0]["channel_id"] == "telegram-ad5x-g6"
    assert payload["data"]["continuation"] == {"route_id": "ad5x", "channel_id": "telegram-ad5x-g6", "state": "pending"}
