

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from app.container import build_container
from app.coordinator.routes import RouteRegistry
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry


def test_route_for_channel_resolves_active_and_pending_generation(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    route = registry.bootstrap(
        "ad5x",
        "https://chatgpt.com/c/00000000-0000-0000-0000-000000000001",
        "telegram-ad5x-g0",
        "AD5X",
    )
    active = registry.route_for_channel(route["channel_id"])
    assert active["route_id"] == "ad5x"
    assert active["route_state"] == "active"

    pending = registry.prepare_rollover("ad5x")
    candidate = registry.route_for_channel(pending["channel_id"])
    assert candidate["route_id"] == "ad5x"
    assert candidate["route_state"] == "pending"
    assert candidate["generation"] == pending["target_generation"]


def test_coordinator_route_context_update_returns_updated_payload(tmp_path: Path):
    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge", "https://chatgpt.com/g/g-p-infra/c/conv-bridge",
        "telegram-bridge-g0", "Development Bridge Infra",
    )
    registry = build_tool_registry(container)
    tool = registry.get("coordinator_route_context_update")
    result = asyncio.run(tool.handler(
        SimpleNamespace(session=SimpleNamespace(_connection=SimpleNamespace(session_id="test-session"))),
        SimpleNamespace(arguments={"route_id": "bridge", "content": "checkpoint"}),
        SimpleNamespace(request_id="req-context-update"),
    ))
    data = json.loads(result.content[0].text)["data"]
    assert data["route_id"] == "bridge"
    assert data["content"] == "checkpoint"
    assert data["revision"] == 1


def test_coordinator_route_context_get_returns_content_without_bootstrap_duplication(tmp_path: Path):
    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge", "https://chatgpt.com/g/g-p-infra/c/conv-bridge",
        "telegram-bridge-g0", "Development Bridge Infra",
    )
    registry = build_tool_registry(container)
    content = "Canonical checkpoint\nNext bounded task"

    update = registry.get("coordinator_route_context_update")
    asyncio.run(update.handler(
        SimpleNamespace(session=SimpleNamespace(_connection=SimpleNamespace(session_id="test-session"))),
        SimpleNamespace(arguments={"route_id": "bridge", "content": content}),
        SimpleNamespace(request_id="req-context-update"),
    ))

    get_tool = registry.get("coordinator_route_context_get")
    result = asyncio.run(get_tool.handler(
        SimpleNamespace(session=SimpleNamespace(_connection=SimpleNamespace(session_id="test-session"))),
        SimpleNamespace(arguments={"route_id": "bridge"}),
        SimpleNamespace(request_id="req-context-get"),
    ))
    data = json.loads(result.content[0].text)["data"]

    assert data["context"]["content"] == content
    assert data["context"]["revision"] == 1
    assert data["bootstrap_message"] == (
        "Canonical Route Context loaded for route bridge. "
        "Current state is available in context.content, revision 1."
    )
    assert content not in data["bootstrap_message"]


def test_coordinator_route_list_returns_bounded_metadata_without_mutating_state(tmp_path: Path):
    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge", "https://chatgpt.com/g/g-p-infra/c/conv-bridge",
        "telegram-bridge-g0", "Development Bridge Infra",
    )
    container.route_registry.bootstrap(
        "ad5xwork", "https://chatgpt.com/g/g-p-ad5x/c/conv-ad5x",
        "telegram-ad5xwork-g0", "AD5X Work",
    )
    container.route_registry.select_default("bridge")
    container.route_registry.request("bridge")
    snapshot_before = container.route_registry.snapshot()

    registry = build_tool_registry(container)
    tool = registry.get("coordinator_route_list")
    assert tool is not None

    ctx = SimpleNamespace(session=SimpleNamespace(_connection=SimpleNamespace(session_id="test-session")))
    result = asyncio.run(tool.handler(
        ctx,
        SimpleNamespace(arguments={}),
        SimpleNamespace(request_id="req-route-list"),
    ))
    data = json.loads(result.content[0].text)["data"]
    assert "routes" in data
    routes = {item["route_id"]: item for item in data["routes"]}
    assert set(routes.keys()) == {"bridge", "ad5xwork"}
    assert routes["bridge"]["title"] == "Development Bridge Infra"
    assert routes["bridge"]["project_id"] == "g-p-infra"
    assert routes["bridge"]["channel_id"] == "telegram-bridge-g0"
    assert routes["bridge"]["generation"] == 0
    assert routes["bridge"]["default"] is True

    assert routes["ad5xwork"]["title"] == "AD5X Work"
    assert routes["ad5xwork"]["project_id"] == "g-p-ad5x"
    assert routes["ad5xwork"]["channel_id"] == "telegram-ad5xwork-g0"
    assert routes["ad5xwork"]["generation"] == 0
    assert routes["ad5xwork"]["default"] is False

    # Check that requested_route, default_route, and snapshot remain unchanged
    snapshot_after = container.route_registry.snapshot()
    assert snapshot_after == snapshot_before

    # Check session binding was not created/changed
    assert container.coordinator.session_binding("test-session") is None
