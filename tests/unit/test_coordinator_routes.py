

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api.errors import BridgeError, ErrorCode
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
    assert data["state"] == "discovery_prepared"
    pending = container.route_registry.pending_current_bind("bridge")
    assert pending is not None
    assert pending["session_id"] is None
    assert result.structured_content["route_discovery"]["route_id"] == "bridge"


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
    import pytest
    from app.api.errors import BridgeError, ErrorCode

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
    import pytest
    from app.api.errors import BridgeError, ErrorCode

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
    import pytest
    from app.api.errors import BridgeError, ErrorCode

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
    import pytest
    from app.api.errors import BridgeError, ErrorCode

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
    import pytest
    from app.api.errors import BridgeError, ErrorCode

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

    unbound = registry.unbind("bridge")
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
    import pytest
    from app.api.errors import BridgeError, ErrorCode

    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/c/conv-1",
        "telegram-bridge-g0",
    )
    with pytest.raises(BridgeError) as exc:
        registry.unbind("bridge", expected_generation=5)
    assert exc.value.code is ErrorCode.POLICY_VIOLATION

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
    registry.unbind("bridge")
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
    import pytest
    from app.api.errors import BridgeError, ErrorCode

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
