from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.api.errors import BridgeError
from app.tools.bridge_restart import bridge_restart_tools


class FakeCoordinator:
    def __init__(self):
        self.armed = []
        self.bindings = {}

    def validate_channel(self, value):
        assert value == "eod-tooling"
        return value

    async def arm(self, message, *, channel_id, delay_seconds, conflict):
        self.armed.append({"message": message, "channel_id": channel_id, "delay_seconds": delay_seconds, "conflict": conflict})
        return {"state": "pending"}

    def session_binding(self, session_id):
        return self.bindings.get(session_id)


class FakeRestart:
    async def schedule(self, *, checkpoint=None):
        if checkpoint is not None:
            await checkpoint()
        return {"restart_scheduled": True}


@pytest.mark.asyncio
async def test_explicit_restart_channel_overrides_default_route():
    coordinator = FakeCoordinator()
    container = SimpleNamespace(
        route_registry=SimpleNamespace(
            resolve=lambda route_id=None: {"route_id": "ad5x", "channel_id": "telegram-ad5x-g6"},
            route_for_channel=lambda channel_id: None,
        ),
        coordinator=coordinator,
        bridge_restart=FakeRestart(),
    )
    tool = bridge_restart_tools(container)[0]
    result = await tool.handler(None, SimpleNamespace(arguments={"channel_id": "eod-tooling"}), SimpleNamespace(request_id="request-1"))
    payload = json.loads(result.content[0].text)
    assert coordinator.armed[0]["channel_id"] == "eod-tooling"
    assert payload["data"]["continuation"] == {"channel_id": "eod-tooling", "state": "pending"}


@pytest.mark.asyncio
async def test_restart_without_binding_does_not_wake_default_route():
    coordinator = FakeCoordinator()
    coordinator.validate_channel = lambda value: value
    container = SimpleNamespace(
        route_registry=SimpleNamespace(
            resolve=lambda route_id=None: {"route_id": "ad5x", "channel_id": "telegram-ad5x-g6"},
            route_for_channel=lambda channel_id: None,
        ),
        coordinator=coordinator,
        bridge_restart=FakeRestart(),
    )
    tool = bridge_restart_tools(container)[0]
    result = await tool.handler(None, SimpleNamespace(arguments={}), SimpleNamespace(request_id="request-2"))
    payload = json.loads(result.content[0].text)
    assert coordinator.armed == []
    assert payload["data"]["continuation_suppressed"] == "no_session_or_explicit_destination"


@pytest.mark.asyncio
async def test_restart_rejects_stale_session_generation_instead_of_waking_successor():
    coordinator = FakeCoordinator()
    coordinator.validate_channel = lambda value: value
    coordinator.bindings["session-1"] = {
        "route_id": "ad5x", "channel_id": "telegram-ad5x-g5", "generation": 5,
    }
    route = {"route_id": "ad5x", "channel_id": "telegram-ad5x-g6", "generation": 6}
    container = SimpleNamespace(
        route_registry=SimpleNamespace(resolve=lambda route_id=None: route, route_for_channel=lambda channel_id: None),
        coordinator=coordinator,
        bridge_restart=FakeRestart(),
    )
    ctx = SimpleNamespace(session=SimpleNamespace(_connection=SimpleNamespace(session_id="session-1")))
    tool = bridge_restart_tools(container)[0]
    with pytest.raises(BridgeError) as exc:
        await tool.handler(ctx, SimpleNamespace(arguments={}), SimpleNamespace(request_id="request-3"))
    assert "stale route generation" in str(exc.value)
    assert coordinator.armed == []
