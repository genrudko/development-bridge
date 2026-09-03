from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.coordinator.routes import RouteRegistry
from app.coordinator.service import CoordinatorService
from app.coordinator.wake_delivery import CoordinatorWakeDeliveryService
from app.coordinator.wake_transport import WakeDiscoveryResult, WakeTarget


@dataclass
class DiscoveryTransport:
    result: WakeDiscoveryResult
    name: str = "discovery-test"
    calls: list[tuple[str, WakeTarget]] | None = None

    def __post_init__(self):
        if self.calls is None:
            self.calls = []

    async def discover_current_chat(self, marker: str, target: WakeTarget) -> WakeDiscoveryResult:
        self.calls.append((marker, target))
        return self.result

    async def probe(self, target):
        raise AssertionError("not used")

    async def deliver(self, request):
        raise AssertionError("not used")


def _registry(tmp_path: Path) -> RouteRegistry:
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/conv-old",
        "telegram-bridge-g4",
        "Bridge",
    )
    return registry


def test_prepare_current_bind_is_idempotent_and_uses_unique_marker(tmp_path: Path):
    registry = _registry(tmp_path)
    first = registry.prepare_current_bind("bridge", session_id="mcp-session-1")
    second = registry.prepare_current_bind("bridge", session_id="mcp-session-1")
    assert first == second
    assert first["route_id"] == "bridge"
    assert first["source_generation"] == 0
    assert first["channel_id"] == "telegram-bridge-g4"
    assert first["session_id"] == "mcp-session-1"
    assert first["token"].startswith("bind_")
    assert first["marker"].startswith("DBRIDGE_ROUTE_BIND_")
    assert len(first["marker"]) >= 40


def test_complete_current_bind_changes_route_once_and_clears_pending(tmp_path: Path):
    registry = _registry(tmp_path)
    pending = registry.prepare_current_bind("bridge", session_id="mcp-session-1")
    bound = registry.complete_current_bind(
        "bridge", pending["token"],
        "https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/conv-new",
    )
    assert bound["changed"] is True
    assert bound["conversation_id"] == "conv-new"
    assert bound["generation"] == 1
    assert bound["channel_id"] == "telegram-bridge-g1"
    assert registry.pending_current_bind("bridge") is None


def test_complete_current_bind_same_chat_is_noop(tmp_path: Path):
    registry = _registry(tmp_path)
    pending = registry.prepare_current_bind("bridge", session_id="mcp-session-1")
    bound = registry.complete_current_bind(
        "bridge", pending["token"],
        "https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/conv-old",
    )
    assert bound["changed"] is False
    assert bound["generation"] == 0
    assert bound["channel_id"] == "telegram-bridge-g4"


def test_complete_current_bind_rejects_cross_project(tmp_path: Path):
    registry = _registry(tmp_path)
    pending = registry.prepare_current_bind("bridge", session_id="mcp-session-1")
    with pytest.raises(BridgeError) as exc:
        registry.complete_current_bind(
            "bridge", pending["token"],
            "https://chatgpt.com/g/g-p-22222222222222222222222222222222/c/conv-new",
        )
    assert exc.value.code is ErrorCode.POLICY_VIOLATION
    assert registry.resolve("bridge")["conversation_id"] == "conv-old"


@pytest.mark.asyncio
async def test_discover_and_bind_current_route_uses_marker_and_rebinds_session(tmp_path: Path):
    registry = _registry(tmp_path)
    coordinator = CoordinatorService(tmp_path / "wakes.json")
    pending = registry.prepare_current_bind("bridge", session_id="mcp-session-1")
    transport = DiscoveryTransport(WakeDiscoveryResult(
        found=True,
        route_url="https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/conv-new",
        conversation_id="conv-new",
    ))
    service = CoordinatorWakeDeliveryService(
        coordinator, registry, transport=transport, enabled=True, poll_interval_seconds=1,
    )
    result = await service.discover_and_bind_current_route("bridge", pending["token"])
    assert transport.calls and transport.calls[0][0] == pending["marker"]
    assert transport.calls[0][1].conversation_id == "conv-old"
    assert result["conversation_id"] == "conv-new"
    binding = coordinator.session_binding("mcp-session-1")
    assert binding["route_id"] == "bridge"
    assert binding["generation"] == 1
    assert binding["channel_id"] == "telegram-bridge-g1"


@pytest.mark.asyncio
async def test_discover_and_bind_current_route_fails_closed_on_ambiguous_search(tmp_path: Path):
    registry = _registry(tmp_path)
    coordinator = CoordinatorService(tmp_path / "wakes.json")
    pending = registry.prepare_current_bind("bridge", session_id="mcp-session-1")
    transport = DiscoveryTransport(WakeDiscoveryResult(
        found=False, detail="Expected exactly one marker match; found 2",
    ))
    service = CoordinatorWakeDeliveryService(coordinator, registry, transport=transport, enabled=True)
    with pytest.raises(BridgeError) as exc:
        await service.discover_and_bind_current_route("bridge", pending["token"])
    assert exc.value.code is ErrorCode.POLICY_VIOLATION
    assert registry.resolve("bridge")["conversation_id"] == "conv-old"
    assert registry.pending_current_bind("bridge") is not None


def test_stale_pending_current_bind_is_replaced(tmp_path: Path):
    import json

    registry = _registry(tmp_path)
    first = registry.prepare_current_bind("bridge", session_id="mcp-session-1")
    data = json.loads(registry.path.read_text(encoding="utf-8"))
    data["current_binds"]["bridge"]["created_at"] = "2000-01-01T00:00:00+00:00"
    registry.path.write_text(json.dumps(data), encoding="utf-8")

    second = registry.prepare_current_bind("bridge", session_id="mcp-session-2")
    assert second["token"] != first["token"]
    assert second["session_id"] == "mcp-session-2"


def test_discovery_helper_uses_observed_project_route_not_synthetic_expected_prefix():
    helper = (Path(__file__).parents[2] / "app/coordinator/review_gpt_discovery.mjs").read_text(encoding="utf-8")
    assert "candidateUrl(" not in helper
    assert "matches[0].href" in helper
    assert "authoritativeRoutes" in helper
    assert "location.href" in helper
    assert "command-timeout" in helper
    assert "allowProjectChange" in helper
    assert "group/project-item" in helper


def test_complete_current_bind_allows_explicit_project_change(tmp_path: Path):
    registry = _registry(tmp_path)
    pending = registry.prepare_current_bind(
        "bridge", session_id="mcp-session-1", allow_project_change=True
    )
    bound = registry.complete_current_bind(
        "bridge", pending["token"], "https://chatgpt.com/c/conv-new"
    )
    assert bound["changed"] is True
    assert bound["conversation_id"] == "conv-new"
    assert bound["project_id"] is None
    assert bound["generation"] == 1


@pytest.mark.asyncio
async def test_discovery_transport_receives_explicit_project_change_authorization(tmp_path: Path):
    registry = _registry(tmp_path)
    coordinator = CoordinatorService(tmp_path / "wakes.json")
    pending = registry.prepare_current_bind(
        "bridge", session_id="mcp-session-1", allow_project_change=True
    )
    transport = DiscoveryTransport(WakeDiscoveryResult(
        found=True, route_url="https://chatgpt.com/c/conv-new", conversation_id="conv-new"
    ))
    service = CoordinatorWakeDeliveryService(coordinator, registry, transport=transport, enabled=True)
    result = await service.discover_and_bind_current_route("bridge", pending["token"])
    assert transport.calls[0][1].allow_project_change is True
    assert result["project_id"] is None


def test_discovery_helper_uses_observed_slugged_project_landing_for_membership_check():
    helper = (Path(__file__).parents[2] / "app/coordinator/review_gpt_discovery.mjs").read_text(encoding="utf-8")
    assert "observedProjectLanding" in helper
    assert "await cmd(\'Page.navigate\', {url:routeUrl});" in helper
    assert "querySelectorAll('a[href*=\\\"/project\\\"]')" in helper
    assert "https://chatgpt.com/g/${encodeURIComponent(expectedProject)}/project" not in helper


def test_discovery_helper_binds_search_result_by_click_not_virtualized_body_text():
    helper = (Path(__file__).parents[2] / "app/coordinator/review_gpt_discovery.mjs").read_text(encoding="utf-8")
    assert "markerMatchClicked" in helper
    assert "anchor.click()" in helper
    assert "Marker result did not navigate to the indexed conversation" in helper
    assert "Marker result did not verify in the navigated conversation" not in helper
    assert "Authoritative project route did not re-verify marker" not in helper
