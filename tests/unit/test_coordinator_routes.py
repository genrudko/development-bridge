

import asyncio
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.container import build_container
from app.coordinator.routes import RouteRegistry
from app.settings import BridgeSettings
from app.telegram_supervisor import TelegramSupervisorService
from app.tools.coordinator import COORDINATOR_UI_URI
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


def _assert_model_surfaces_exclude(result, forbidden: tuple[str, ...]) -> None:
    model_text = result.content[0].text
    structured = json.dumps(result.structured_content, sort_keys=True)
    for value in forbidden:
        assert value not in model_text
        assert value not in structured


def test_coordinator_route_context_get_hides_physical_route_identity(tmp_path: Path):
    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-sensitive-project/c/conv-sensitive-context",
        "telegram-bridge-g0",
        "Development Bridge Infra",
    )
    tool = build_tool_registry(container).get("coordinator_route_context_get")

    result = asyncio.run(tool.handler(
        None,
        SimpleNamespace(arguments={"route_id": "bridge"}),
        SimpleNamespace(request_id="req-context-safe"),
    ))

    _assert_model_surfaces_exclude(
        result,
        ("https://chatgpt.com", "g-p-sensitive-project", "conv-sensitive-context"),
    )


def test_coordinator_route_rollover_prepare_hides_physical_identity_and_token(tmp_path: Path):
    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-sensitive-project/c/conv-sensitive-rollover",
        "telegram-bridge-g0",
        "Development Bridge Infra",
    )
    tool = build_tool_registry(container).get("coordinator_route_rollover_prepare")

    result = asyncio.run(tool.handler(
        None,
        SimpleNamespace(arguments={"route_id": "bridge"}),
        SimpleNamespace(request_id="req-rollover-safe"),
    ))
    pending = container.route_registry.pending_rollover("bridge")

    assert pending is not None
    assert result.structured_content["channel_id"] == "telegram-bridge-g0"
    _assert_model_surfaces_exclude(
        result,
        (
            "https://chatgpt.com",
            "g-p-sensitive-project",
            "conv-sensitive-rollover",
            pending["token"],
        ),
    )


def test_coordinator_route_rollover_prepare_rejects_unbound_route_before_prepare(
    tmp_path: Path,
):
    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-sensitive-project/c/conv-unbound",
        "telegram-bridge-g0",
    )
    container.route_registry.unbind("bridge", expected_generation=0)
    called = []
    original_prepare = container.route_registry.prepare_rollover

    def prepare(route_id):
        called.append(route_id)
        return original_prepare(route_id)

    container.route_registry.prepare_rollover = prepare
    tool = build_tool_registry(container).get("coordinator_route_rollover_prepare")

    with pytest.raises(BridgeError) as raised:
        asyncio.run(tool.handler(
            None,
            SimpleNamespace(arguments={"route_id": "bridge"}),
            SimpleNamespace(request_id="req-rollover-unbound"),
        ))

    assert raised.value.code == ErrorCode.POLICY_VIOLATION
    assert raised.value.details["error_code"] == "ROUTE_UNBOUND"
    assert called == []


def test_telegram_supervisor_status_projects_only_safe_logical_routes(tmp_path: Path):
    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-sensitive-project/c/conv-sensitive-supervisor",
        "telegram-bridge-g0",
        "Development Bridge Infra",
    )
    raw = container.route_registry.snapshot()
    raw["routes"]["bridge"]["control_token"] = "private-route-control-token"
    container.route_registry._save(raw)
    supervisor = TelegramSupervisorService(
        enabled=False,
        api_id=None,
        api_hash=None,
        session_path=None,
        chat_id=None,
        topic_id=None,
        channel_id="telegram-supervisor",
        coordinator=container.coordinator,
        route_registry=container.route_registry,
    )
    container = dataclasses.replace(container, telegram_supervisor=supervisor)
    tool = build_tool_registry(container).get("telegram_supervisor_status")

    result = asyncio.run(tool.handler(
        None,
        SimpleNamespace(arguments={}),
        SimpleNamespace(request_id="req-supervisor-safe"),
    ))
    data = json.loads(result.content[0].text)["data"]
    route = data["routes"][0]

    assert route == {
        "route_id": "bridge",
        "title": "Development Bridge Infra",
        "binding_state": "bound",
        "channel_id": "telegram-bridge-g0",
        "generation": 0,
        "default": True,
    }
    _assert_model_surfaces_exclude(
        result,
        (
            "https://chatgpt.com",
            "g-p-sensitive-project",
            "conv-sensitive-supervisor",
            "private-route-control-token",
        ),
    )


def test_coordinator_x_mount_accepts_only_exact_registered_pending_channel(
    tmp_path: Path,
):
    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-current",
        "telegram-bridge-g0",
    )
    pending = container.route_registry.prepare_rollover("bridge")
    tool = build_tool_registry(container).get("coordinator_x_mount")
    ctx = SimpleNamespace(
        session=SimpleNamespace(_connection=SimpleNamespace(session_id="pending-mount"))
    )

    result = asyncio.run(tool.handler(
        ctx,
        SimpleNamespace(arguments={"channel_id": pending["channel_id"]}),
        SimpleNamespace(request_id="req-pending-mount"),
    ))

    assert result.structured_content["channel_id"] == "telegram-bridge-g1"
    assert result.structured_content["route_id"] == "bridge"
    assert result.structured_content["generation"] == 1
    assert result.structured_content["route_state"] == "pending"
    binding = container.coordinator.session_binding("pending-mount")
    assert binding["channel_id"] == "telegram-bridge-g1"
    assert binding["route_state"] == "pending"

    with pytest.raises(BridgeError, match="pending route-generation"):
        container.route_registry.wake_route_for_channel(pending["channel_id"])

    with pytest.raises(BridgeError, match="unregistered route-generation"):
        asyncio.run(tool.handler(
            ctx,
            SimpleNamespace(arguments={"channel_id": "telegram-bridge-g2"}),
            SimpleNamespace(request_id="req-arbitrary-future-mount"),
        ))


def test_coordinator_pending_mount_cannot_wake_but_legacy_explicit_channel_can(
    tmp_path: Path,
):
    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-current",
        "telegram-bridge-g0",
    )
    pending = container.route_registry.prepare_rollover("bridge")
    registry = build_tool_registry(container)
    continue_tool = registry.get("coordinator_continue")

    with pytest.raises(BridgeError, match="pending route-generation"):
        asyncio.run(continue_tool.handler(
            None,
            SimpleNamespace(arguments={
                "channel_id": pending["channel_id"],
                "message": "must not wake pending successor",
                "delay_seconds": 0,
            }),
            SimpleNamespace(request_id="req-pending-wake"),
        ))

    legacy = asyncio.run(continue_tool.handler(
        None,
        SimpleNamespace(arguments={
            "channel_id": "legacy-supervisor",
            "message": "legacy wake remains supported",
            "delay_seconds": 0,
        }),
        SimpleNamespace(request_id="req-legacy-wake"),
    ))
    legacy_data = json.loads(legacy.content[0].text)["data"]
    assert legacy_data["channel_id"] == "legacy-supervisor"
    assert legacy_data["state"] == "pending"


def test_coordinator_route_takeover_hides_physical_route_identity(tmp_path: Path):
    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-sensitive-project/c/conv-old",
        "telegram-bridge-g0",
        "Development Bridge Infra",
    )
    tool = build_tool_registry(container).get("coordinator_route_takeover")

    result = asyncio.run(tool.handler(
        None,
        SimpleNamespace(arguments={
            "route_id": "bridge",
            "url": "https://chatgpt.com/g/g-p-sensitive-project/c/conv-sensitive-takeover",
        }),
        SimpleNamespace(request_id="req-takeover-safe"),
    ))

    _assert_model_surfaces_exclude(
        result,
        ("https://chatgpt.com", "g-p-sensitive-project", "conv-sensitive-takeover"),
    )


def test_coordinator_continue_rejects_unregistered_future_route_channel(tmp_path: Path):
    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-current",
        "telegram-bridge-g0",
    )
    tool = build_tool_registry(container).get("coordinator_continue")

    with pytest.raises(BridgeError, match="route-generation"):
        asyncio.run(tool.handler(
            None,
            SimpleNamespace(arguments={
                "channel_id": "telegram-bridge-g1",
                "message": "wake a future route",
            }),
            SimpleNamespace(request_id="req-future-channel"),
        ))


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
    assert routes["bridge"]["binding_state"] == "bound"
    assert "project_id" not in routes["bridge"]
    assert routes["bridge"]["channel_id"] == "telegram-bridge-g0"
    assert routes["bridge"]["generation"] == 0
    assert routes["bridge"]["default"] is True

    assert routes["ad5xwork"]["title"] == "AD5X Work"
    assert routes["ad5xwork"]["binding_state"] == "bound"
    assert "project_id" not in routes["ad5xwork"]
    assert routes["ad5xwork"]["channel_id"] == "telegram-ad5xwork-g0"
    assert routes["ad5xwork"]["generation"] == 0
    assert routes["ad5xwork"]["default"] is False

    # Check that requested_route, default_route, and snapshot remain unchanged
    snapshot_after = container.route_registry.snapshot()
    assert snapshot_after == snapshot_before

    # Check session binding was not created/changed
    assert container.coordinator.session_binding("test-session") is None


def test_bind_current_allows_sessionless_modern_mcp_request(tmp_path: Path):
    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/conv-old",
        "telegram-bridge-g4",
    )
    registry = build_tool_registry(container)
    tool = registry.get("coordinator_route_bind_current")
    result = asyncio.run(tool.handler(
        None,
        SimpleNamespace(arguments={"route_id": "bridge"}),
        SimpleNamespace(request_id="req-bind-current-sessionless"),
    ))
    data = json.loads(result.content[0].text)["data"]
    assert data["state"] == "bind_pending"
    assert data["route_id"] == "bridge"
    assert data["generation"] == 0
    assert set(data.keys()) == {"route_id", "state", "generation"}

    pending = container.route_registry.pending_current_bind("bridge")
    assert pending is not None
    assert pending["session_id"] is None

    # Structured content must strictly contain only the safe whitelist fields
    assert result.structured_content == {
        "route_id": "bridge",
        "state": "bind_pending",
        "generation": 0,
    }
    assert "channel_id" not in result.structured_content
    assert "trigger_url" not in result.structured_content
    assert "delivery_lease" not in result.structured_content
    assert "route_state" not in result.structured_content

    # UI meta must contain the coordinator UI resource descriptor
    assert result.meta["ui"]["resourceUri"] == COORDINATOR_UI_URI
    assert result.meta["ui/resourceUri"] == COORDINATOR_UI_URI
    assert result.meta["openai/outputTemplate"] == COORDINATOR_UI_URI

    # Opaque operation details exist only in result.meta (MCP _meta)
    route_control = result.meta.get("route_control")
    assert route_control is not None
    assert route_control["action"] == "bind"
    assert route_control["route_id"] == "bridge"
    assert route_control["operation_id"] == pending["token"]
    assert route_control["operation_url"].endswith(f"/bind/{pending['token']}")
    assert route_control["diagnostic_id"].startswith("bind-")

    # Structured content and model text must have no secret tokens or URLs
    assert "route_discovery" not in (result.structured_content or {})
    assert "operation_url" not in (result.structured_content or {})
    assert "token" not in (result.structured_content or {})
    assert pending["token"] not in result.content[0].text
    assert "conv-old" not in result.content[0].text
    assert route_control["operation_url"] not in result.content[0].text


def test_bind_current_does_not_issue_or_mutate_delivery_lease(tmp_path: Path):
    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/conv-old",
        "telegram-bridge-g4",
    )
    # Pre-issue delivery lease for an active session
    issued = container.coordinator.issue_delivery_lease(
        "telegram-bridge-g4",
        session_id="mounted-session-1",
        route_id="bridge",
        generation=0,
    )
    before_lease = dict(container.coordinator.delivery_lease("telegram-bridge-g4"))
    assert before_lease["lease_id"] == issued["lease_id"]

    registry = build_tool_registry(container)
    tool = registry.get("coordinator_route_bind_current")

    # Call bind_current from another session
    other_ctx = SimpleNamespace(
        session=SimpleNamespace(_connection=SimpleNamespace(session_id="other-mcp-session"))
    )
    result = asyncio.run(tool.handler(
        other_ctx,
        SimpleNamespace(arguments={"route_id": "bridge"}),
        SimpleNamespace(request_id="req-bind-preserve-lease"),
    ))
    assert result.structured_content == {
        "route_id": "bridge",
        "state": "bind_pending",
        "generation": 0,
    }

    # Verify delivery lease remains byte-for-byte / logically unchanged
    after_lease = container.coordinator.delivery_lease("telegram-bridge-g4")
    assert after_lease == before_lease

    # Failed/abandoned prep also does not mutate lease
    with pytest.raises(BridgeError):
        asyncio.run(tool.handler(
            other_ctx,
            SimpleNamespace(arguments={"route_id": "nonexistent"}),
            SimpleNamespace(request_id="req-bind-failed"),
        ))
    assert container.coordinator.delivery_lease("telegram-bridge-g4") == before_lease


def test_bind_current_handles_unbound_route(tmp_path: Path):
    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/c/conv-1",
        "telegram-bridge-g0",
    )
    container.route_registry.unbind("bridge", expected_generation=0)

    registry = build_tool_registry(container)
    tool = registry.get("coordinator_route_bind_current")
    result = asyncio.run(tool.handler(
        None,
        SimpleNamespace(arguments={"route_id": "bridge"}),
        SimpleNamespace(request_id="req-bind-unbound"),
    ))
    data = json.loads(result.content[0].text)["data"]
    assert data["state"] == "bind_pending"
    assert data["route_id"] == "bridge"
    assert data["generation"] == 0
    assert result.structured_content == {
        "route_id": "bridge",
        "state": "bind_pending",
        "generation": 0,
    }
    assert result.meta["ui"]["resourceUri"] == COORDINATOR_UI_URI

    route_control = result.meta.get("route_control")
    assert route_control is not None
    assert route_control["action"] == "bind"
    assert route_control["route_id"] == "bridge"
    assert route_control["operation_url"].endswith(f"/bind/{route_control['operation_id']}")

    # Model content has no leak
    assert route_control["operation_id"] not in result.content[0].text
    assert route_control["operation_url"] not in result.content[0].text


def test_bind_current_repeated_prepare_updates_operation_and_meta(tmp_path: Path):
    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/c/conv-1",
        "telegram-bridge-g0",
    )
    registry = build_tool_registry(container)
    tool = registry.get("coordinator_route_bind_current")

    first = asyncio.run(tool.handler(
        None,
        SimpleNamespace(arguments={"route_id": "bridge"}),
        SimpleNamespace(request_id="req-bind-1"),
    ))
    assert first.structured_content == {
        "route_id": "bridge",
        "state": "bind_pending",
        "generation": 0,
    }
    first_meta = first.meta["route_control"]
    assert first_meta["action"] == "bind"

    second = asyncio.run(tool.handler(
        None,
        SimpleNamespace(arguments={"route_id": "bridge"}),
        SimpleNamespace(request_id="req-bind-2"),
    ))
    assert second.structured_content == {
        "route_id": "bridge",
        "state": "bind_pending",
        "generation": 0,
    }
    second_meta = second.meta["route_control"]
    assert second_meta["action"] == "bind"
    assert second_meta["operation_id"] == first_meta["operation_id"]
    assert second_meta["diagnostic_id"] == first_meta["diagnostic_id"]
    assert second_meta["operation_url"] == first_meta["operation_url"]
    assert len(list((tmp_path / "traces").glob("*.json"))) == 1



def test_bind_current_schema_requires_explicit_boolean_for_project_change(tmp_path: Path):
    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    registry = build_tool_registry(build_container(settings))
    schema = registry.get("coordinator_route_bind_current").definition.input_schema
    assert schema["properties"]["allow_project_change"]["type"] == "boolean"
    assert schema["properties"]["allow_project_change"]["default"] is False


def test_is_bound_identifies_bound_unbound_and_legacy_records(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    # Legacy bound record without explicit binding_state
    legacy_bound = {
        "title": "Legacy",
        "url": "https://chatgpt.com/c/00000000-0000-0000-0000-000000000001",
        "conversation_id": "00000000-0000-0000-0000-000000000001",
        "channel_id": "telegram-legacy-g0",
        "generation": 0,
    }
    assert registry.is_bound(legacy_bound) is True

    # Legacy record missing physical target
    legacy_empty = {"title": "Empty", "generation": 0}
    assert registry.is_bound(legacy_empty) is False

    # Explicit bound record
    explicit_bound = {**legacy_bound, "binding_state": "bound"}
    assert registry.is_bound(explicit_bound) is True

    # Explicit bound record missing physical target fields must NOT be considered bound
    explicit_bound_missing_target = {"title": "Broken", "binding_state": "bound"}
    assert registry.is_bound(explicit_bound_missing_target) is False

    explicit_bound_missing_conv = {"title": "Broken", "url": "https://chatgpt.com/c/123", "binding_state": "bound"}
    assert registry.is_bound(explicit_bound_missing_conv) is False

    # Explicit unbound record
    explicit_unbound = {"title": "Unbound", "channel_id": "telegram-unbound-g0", "generation": 0, "binding_state": "unbound"}
    assert registry.is_bound(explicit_unbound) is False

    assert registry.is_bound(None) is False
    assert registry.is_bound({}) is False


def test_candidate_based_current_bind_flow_does_not_mutate_on_record_and_commits_atomically(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/conv-old",
        "telegram-bridge-g0",
        "Bridge",
    )
    pending = registry.prepare_current_bind("bridge", session_id="session-1")
    assert pending["state"] == "prepared"
    assert pending["token"].startswith("bind_")
    assert pending["marker"].startswith("DBRIDGE_ROUTE_BIND_")

    before = registry.resolve("bridge")
    candidate_url = "https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/conv-new"

    # Candidate recording must not mutate active route
    cand_record = registry.record_current_bind_candidate("bridge", pending["token"], candidate_url)
    assert cand_record["state"] == "candidate"
    assert cand_record["candidate_conversation_id"] == "conv-new"
    assert registry.resolve("bridge") == before

    # Commit atomically updates the route
    bound = registry.complete_current_bind("bridge", pending["token"])
    assert bound["binding_state"] == "bound"
    assert bound["conversation_id"] == "conv-new"
    assert bound["generation"] == 1
    assert bound["channel_id"] == "telegram-bridge-g1"
    assert bound["changed"] is True
    assert registry.pending_current_bind("bridge") is None
    assert registry.resolve("bridge")["conversation_id"] == "conv-new"


def test_candidate_based_current_bind_same_target_is_idempotent(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/conv-old",
        "telegram-bridge-g0",
        "Bridge",
    )
    pending = registry.prepare_current_bind("bridge", session_id="session-1")
    registry.record_current_bind_candidate(
        "bridge", pending["token"],
        "https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/conv-old",
    )
    bound = registry.complete_current_bind("bridge", pending["token"])
    assert bound["changed"] is False
    assert bound["generation"] == 0
    assert bound["channel_id"] == "telegram-bridge-g0"
    assert bound["binding_state"] == "bound"


def test_candidate_recording_rejects_project_mismatch(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/conv-old",
        "telegram-bridge-g0",
    )

    pending = registry.prepare_current_bind("bridge", session_id="session-1", allow_project_change=False)
    with pytest.raises(BridgeError) as exc:
        registry.record_current_bind_candidate(
            "bridge", pending["token"],
            "https://chatgpt.com/g/g-p-22222222222222222222222222222222/c/conv-other",
        )
    assert exc.value.code is ErrorCode.POLICY_VIOLATION
    assert registry.resolve("bridge")["conversation_id"] == "conv-old"


def test_candidate_recording_allows_authorized_project_change(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/conv-old",
        "telegram-bridge-g0",
    )
    pending = registry.prepare_current_bind("bridge", session_id="session-1", allow_project_change=True)
    registry.record_current_bind_candidate(
        "bridge", pending["token"],
        "https://chatgpt.com/c/conv-plain",
    )
    bound = registry.complete_current_bind("bridge", pending["token"])
    assert bound["changed"] is True
    assert bound["conversation_id"] == "conv-plain"
    assert bound["project_id"] is None
    assert bound["generation"] == 1


def test_candidate_recording_and_complete_fail_on_generation_race(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/c/conv-old",
        "telegram-bridge-g0",
    )
    pending = registry.prepare_current_bind("bridge", session_id="session-1")

    # Race: route generation changes before record
    registry.takeover("bridge", "https://chatgpt.com/c/conv-raced")
    assert registry.resolve("bridge")["generation"] == 1

    with pytest.raises(BridgeError) as exc:
        registry.record_current_bind_candidate(
            "bridge", pending["token"], "https://chatgpt.com/c/conv-new"
        )
    assert exc.value.code is ErrorCode.POLICY_VIOLATION

    # Race: record succeeds at gen 1, but gen changes to gen 2 before complete
    pending2 = registry.prepare_current_bind("bridge", session_id="session-2")
    registry.record_current_bind_candidate("bridge", pending2["token"], "https://chatgpt.com/c/conv-new")
    registry.takeover("bridge", "https://chatgpt.com/c/conv-raced2")

    with pytest.raises(BridgeError) as exc2:
        registry.complete_current_bind("bridge", pending2["token"])
    assert exc2.value.code is ErrorCode.POLICY_VIOLATION


def test_candidate_recording_and_complete_fail_on_expired_token(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/c/conv-old",
        "telegram-bridge-g0",
    )
    pending = registry.prepare_current_bind("bridge", session_id="session-1")

    data = json.loads(registry.path.read_text(encoding="utf-8"))
    data["current_binds"]["bridge"]["created_at"] = "2000-01-01T00:00:00+00:00"
    registry.path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(BridgeError) as exc:
        registry.record_current_bind_candidate("bridge", pending["token"], "https://chatgpt.com/c/conv-new")
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT

    # Also test complete after expiry
    pending2 = registry.prepare_current_bind("bridge", session_id="session-2")
    registry.record_current_bind_candidate("bridge", pending2["token"], "https://chatgpt.com/c/conv-new")

    data = json.loads(registry.path.read_text(encoding="utf-8"))
    data["current_binds"]["bridge"]["created_at"] = "2000-01-01T00:00:00+00:00"
    registry.path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(BridgeError) as exc2:
        registry.complete_current_bind("bridge", pending2["token"])
    assert exc2.value.code is ErrorCode.INVALID_ARGUMENT


def test_complete_current_bind_cannot_be_replayed(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/c/conv-old",
        "telegram-bridge-g0",
    )
    pending = registry.prepare_current_bind("bridge", session_id="session-1")
    registry.record_current_bind_candidate("bridge", pending["token"], "https://chatgpt.com/c/conv-new")
    registry.complete_current_bind("bridge", pending["token"])

    # Replay fails
    with pytest.raises(BridgeError) as exc:
        registry.complete_current_bind("bridge", pending["token"])
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT


def test_complete_current_bind_fails_if_candidate_not_ready(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/c/conv-old",
        "telegram-bridge-g0",
    )
    pending = registry.prepare_current_bind("bridge", session_id="session-1")
    # Complete without recording candidate or passing url
    with pytest.raises(BridgeError) as exc:
        registry.complete_current_bind("bridge", pending["token"])
    assert exc.value.code is ErrorCode.POLICY_VIOLATION


def test_unbind_removes_physical_target_and_persists_unbound_state(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-bridge",
        "telegram-bridge-g0",
        "Development Bridge Infra",
    )
    assert registry.is_bound(registry.resolve("bridge")) is True

    unbound = registry.unbind("bridge", expected_generation=0)
    assert unbound["route_id"] == "bridge"
    assert unbound["title"] == "Development Bridge Infra"
    assert unbound["binding_state"] == "unbound"
    assert unbound["generation"] == 0
    assert unbound["channel_id"] == "telegram-bridge-g0"
    assert "url" not in unbound
    assert "conversation_id" not in unbound
    assert "project_id" not in unbound

    # Check persistence and reload
    registry2 = RouteRegistry(tmp_path / "routes.json")
    resolved = registry2.resolve("bridge")
    assert resolved["binding_state"] == "unbound"
    assert "url" not in resolved
    assert registry2.is_bound(resolved) is False

    # Check list_routes preserves unbound state
    routes = registry2.list_routes()
    bridge_route = next(r for r in routes if r["route_id"] == "bridge")
    assert bridge_route["binding_state"] == "unbound"
    assert "url" not in bridge_route


def test_unbind_guards_expected_generation(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/c/conv-1",
        "telegram-bridge-g0",
    )
    with pytest.raises(BridgeError) as exc:
        registry.unbind("bridge", expected_generation=5)
    assert exc.value.code is ErrorCode.POLICY_VIOLATION

    # Unbind without expected_generation must fail with TypeError
    with pytest.raises(TypeError):
        registry.unbind("bridge")  # type: ignore[call-arg]

    # Correct expected generation succeeds
    unbound = registry.unbind("bridge", expected_generation=0)
    assert unbound["binding_state"] == "unbound"


def test_binding_an_unbound_route_allocates_next_generation_and_channel(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/c/conv-1",
        "telegram-bridge-g0",
    )
    registry.unbind("bridge", expected_generation=0)
    assert registry.resolve("bridge")["binding_state"] == "unbound"

    pending = registry.prepare_current_bind("bridge", session_id="session-1")
    assert pending["source_generation"] == 0
    registry.record_current_bind_candidate("bridge", pending["token"], "https://chatgpt.com/c/conv-2")
    bound = registry.complete_current_bind("bridge", pending["token"])

    assert bound["binding_state"] == "bound"
    assert bound["conversation_id"] == "conv-2"
    assert bound["generation"] == 1
    assert bound["channel_id"] == "telegram-bridge-g1"
    assert bound["changed"] is True


def test_takeover_rejects_moving_bound_non_project_route_to_project(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    # Bootstrap a bound non-Project route (project_id is None)
    registry.bootstrap(
        "plain",
        "https://chatgpt.com/c/00000000-0000-0000-0000-000000000001",
        "telegram-plain-g0",
    )
    assert registry.resolve("plain")["project_id"] is None
    assert registry.is_bound(registry.resolve("plain")) is True

    # Attempting to takeover a bound non-project route into a project must be rejected
    with pytest.raises(BridgeError) as exc:
        registry.takeover("plain", "https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/conv-proj")
    assert exc.value.code is ErrorCode.POLICY_VIOLATION
    assert "different project" in exc.value.message

    # But taking over an unbound route into a project is allowed
    registry.unbind("plain", expected_generation=0)
    taken = registry.takeover("plain", "https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/conv-proj")
    assert taken["project_id"] == "g-p-11111111111111111111111111111111"
    assert taken["generation"] == 1


def test_candidate_recording_cannot_be_overwritten_or_replayed(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/c/conv-old",
        "telegram-bridge-g0",
    )
    pending = registry.prepare_current_bind("bridge", session_id="session-1")
    # First record succeeds
    rec = registry.record_current_bind_candidate("bridge", pending["token"], "https://chatgpt.com/c/conv-first")
    assert rec["state"] == "candidate"

    # Second record with same token must fail closed (one-shot candidate recording)
    with pytest.raises(BridgeError) as exc:
        registry.record_current_bind_candidate("bridge", pending["token"], "https://chatgpt.com/c/conv-second")
    assert exc.value.code is ErrorCode.POLICY_VIOLATION


@pytest.mark.parametrize(
    "bad_url",
    [
        "http://chatgpt.com/c/conv-1",
        "https://example.com/c/conv-1",
        "https://chatgpt.com:443/c/conv-1",
        "https://chatgpt.com/",
        "https://chatgpt.com/c/",
        "not_a_url",
        "",
    ],
)
def test_candidate_recording_rejects_malformed_or_cross_origin_targets(tmp_path: Path, bad_url: str):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/c/conv-1",
        "telegram-bridge-g0",
    )
    pending = registry.prepare_current_bind("bridge", session_id="session-1")
    with pytest.raises(BridgeError) as exc:
        registry.record_current_bind_candidate("bridge", pending["token"], bad_url)
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT
    assert registry.resolve("bridge")["conversation_id"] == "conv-1"
