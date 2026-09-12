from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.api.errors import BridgeError
from app.coordinator import RouteRegistry
from app.tools.bridge_restart import bridge_restart_tools


class FakeCoordinator:
    def __init__(self):
        self.armed = []
        self.bindings = {}
        self.resilient_calls = 0

    def validate_channel(self, value):
        assert value == "eod-tooling"
        return value

    async def arm(self, message, *, channel_id, delay_seconds, conflict):
        self.armed.append({"message": message, "channel_id": channel_id, "delay_seconds": delay_seconds, "conflict": conflict})
        return {"state": "pending"}

    async def arm_resilient(self, message, *, channel_id, delay_seconds, conflict):
        self.resilient_calls += 1
        self.armed.append({"message": message, "channel_id": channel_id, "delay_seconds": delay_seconds, "conflict": conflict, "resilient": True})
        return {"state": "pending", "continuation_id": "cont_restart_test", "model_ack_required": True, "max_delivery_attempts": 3}

    def session_binding(self, session_id):
        return self.bindings.get(session_id)


class FakeRestart:
    def __init__(self):
        self.calls = 0

    async def schedule(self, *, checkpoint=None):
        self.calls += 1
        if checkpoint is not None:
            await checkpoint()
        return {"restart_scheduled": True}


@pytest.mark.asyncio
async def test_explicit_restart_channel_overrides_default_route():
    coordinator = FakeCoordinator()
    container = SimpleNamespace(
        route_registry=SimpleNamespace(
            resolve=lambda route_id=None: {"route_id": "ad5x", "channel_id": "telegram-ad5x-g6"},
            wake_route_for_channel=lambda channel_id: None,
        ),
        coordinator=coordinator,
        bridge_restart=FakeRestart(),
    )
    tool = bridge_restart_tools(container)[0]
    result = await tool.handler(None, SimpleNamespace(arguments={"channel_id": "eod-tooling"}), SimpleNamespace(request_id="request-1"))
    payload = json.loads(result.content[0].text)
    assert coordinator.armed[0]["channel_id"] == "eod-tooling"
    assert payload["data"]["continuation"] == {
        "channel_id": "eod-tooling",
        "state": "pending",
        "continuation_id": "cont_restart_test",
        "model_ack_required": True,
        "max_delivery_attempts": 3,
    }


@pytest.mark.asyncio
async def test_restart_without_binding_does_not_wake_default_route():
    coordinator = FakeCoordinator()
    coordinator.validate_channel = lambda value: value
    container = SimpleNamespace(
        route_registry=SimpleNamespace(
            resolve=lambda route_id=None: {"route_id": "ad5x", "channel_id": "telegram-ad5x-g6"},
            wake_route_for_channel=lambda channel_id: None,
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
        route_registry=SimpleNamespace(
            resolve=lambda route_id=None: route,
            is_bound=lambda value: True,
        ),
        coordinator=coordinator,
        bridge_restart=FakeRestart(),
    )
    ctx = SimpleNamespace(session=SimpleNamespace(_connection=SimpleNamespace(session_id="session-1")))
    tool = bridge_restart_tools(container)[0]
    with pytest.raises(BridgeError) as exc:
        await tool.handler(ctx, SimpleNamespace(arguments={}), SimpleNamespace(request_id="request-3"))
    assert "stale route generation" in str(exc.value)
    assert coordinator.armed == []


@pytest.mark.asyncio
async def test_restart_rejects_explicit_unbound_route(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "ad5x",
        "https://chatgpt.com/g/g-p-infra/c/conv-current",
        "telegram-ad5x-g0",
    )
    registry.unbind("ad5x", expected_generation=0)
    coordinator = FakeCoordinator()
    container = SimpleNamespace(
        route_registry=registry,
        coordinator=coordinator,
        bridge_restart=FakeRestart(),
    )
    tool = bridge_restart_tools(container)[0]

    with pytest.raises(BridgeError, match="unbound"):
        await tool.handler(
            None,
            SimpleNamespace(arguments={"route_id": "ad5x"}),
            SimpleNamespace(request_id="request-unbound"),
        )
    assert coordinator.armed == []


@pytest.mark.asyncio
async def test_restart_rejects_registered_pending_route_channel(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "ad5x",
        "https://chatgpt.com/g/g-p-infra/c/conv-current",
        "telegram-ad5x-g0",
    )
    pending = registry.prepare_rollover("ad5x")
    coordinator = FakeCoordinator()
    coordinator.validate_channel = lambda value: value
    restart = FakeRestart()
    container = SimpleNamespace(
        route_registry=registry,
        coordinator=coordinator,
        bridge_restart=restart,
    )
    tool = bridge_restart_tools(container)[0]

    with pytest.raises(BridgeError, match="pending route-generation"):
        await tool.handler(
            None,
            SimpleNamespace(arguments={"channel_id": pending["channel_id"]}),
            SimpleNamespace(request_id="request-pending"),
        )
    assert coordinator.armed == []
    assert restart.calls == 0


@pytest.mark.asyncio
async def test_restart_arms_bound_route_under_route_lock(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "ad5x",
        "https://chatgpt.com/g/g-p-infra/c/conv-current",
        "telegram-ad5x-g0",
    )
    route_lock = registry.route_lock("ad5x")
    coordinator = FakeCoordinator()
    lock_observations = []

    async def observe_lock(message, *, channel_id, delay_seconds, conflict):
        lock_observations.append(route_lock.locked())
        return await FakeCoordinator.arm_resilient(
            coordinator,
            message,
            channel_id=channel_id,
            delay_seconds=delay_seconds,
            conflict=conflict,
        )

    coordinator.arm_resilient = observe_lock
    container = SimpleNamespace(
        route_registry=registry,
        coordinator=coordinator,
        bridge_restart=FakeRestart(),
    )
    tool = bridge_restart_tools(container)[0]

    result = await tool.handler(
        None,
        SimpleNamespace(arguments={"route_id": "ad5x"}),
        SimpleNamespace(request_id="request-locked"),
    )

    assert json.loads(result.content[0].text)["data"]["restart_scheduled"] is True
    assert lock_observations == [True]


@pytest.mark.asyncio
async def test_restart_uses_resilient_continuation_for_direct_post_restart_delivery():
    coordinator = FakeCoordinator()
    registry = RouteRegistry()
    registry.bootstrap("fusioncad", "https://chatgpt.com/g/g-p-project/c/conv", "telegram-fusioncad-g0")
    container = SimpleNamespace(route_registry=registry, coordinator=coordinator, bridge_restart=FakeRestart())
    tool = bridge_restart_tools(container)[0]

    result = await tool.handler(
        None,
        SimpleNamespace(arguments={"route_id": "fusioncad"}),
        SimpleNamespace(request_id="request-resilient-restart"),
    )
    payload = json.loads(result.content[0].text)["data"]

    assert coordinator.resilient_calls == 1
    assert coordinator.armed[0]["resilient"] is True
    assert payload["continuation"]["continuation_id"] == "cont_restart_test"
    assert payload["continuation"]["model_ack_required"] is True


@pytest.mark.asyncio
async def test_restart_rejects_active_source_route_while_rollover_pending(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap("ad5x", "https://chatgpt.com/g/g-p-infra/c/conv-current", "telegram-ad5x-g0")
    registry.prepare_rollover("ad5x")
    coordinator = FakeCoordinator()
    container = SimpleNamespace(route_registry=registry, coordinator=coordinator, bridge_restart=FakeRestart())
    tool = bridge_restart_tools(container)[0]
    with pytest.raises(BridgeError, match="rollover"):
        await tool.handler(None, SimpleNamespace(arguments={"route_id": "ad5x"}), SimpleNamespace(request_id="request-rollover-freeze"))
    assert coordinator.armed == []
    assert container.bridge_restart.calls == 1
