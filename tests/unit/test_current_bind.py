from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.coordinator.review_gpt_transport import ReviewGptWakeTransport
from app.coordinator.routes import RouteRegistry
from app.coordinator.wake_delivery import CoordinatorWakeDeliveryService
from app.coordinator.wake_transport import WakeTransport


def _registry(tmp_path: Path) -> RouteRegistry:
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/conv-old",
        "telegram-bridge-g4",
        "Bridge",
    )
    return registry


def test_prepare_current_bind_is_idempotent_and_uses_only_opaque_token(tmp_path: Path):
    registry = _registry(tmp_path)
    first = registry.prepare_current_bind("bridge", session_id="mcp-session-1")
    second = registry.prepare_current_bind("bridge", session_id="mcp-session-1")
    assert first == second
    assert first["route_id"] == "bridge"
    assert first["source_generation"] == 0
    assert first["channel_id"] == "telegram-bridge-g4"
    assert first["session_id"] == "mcp-session-1"
    assert first["token"].startswith("bind_")
    assert "marker" not in first


def test_complete_current_bind_changes_route_once_and_clears_pending(tmp_path: Path):
    registry = _registry(tmp_path)
    pending = registry.prepare_current_bind("bridge", session_id="mcp-session-1")
    bound = registry.complete_current_bind(
        "bridge",
        pending["token"],
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
        "bridge",
        pending["token"],
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
            "bridge",
            pending["token"],
            "https://chatgpt.com/g/g-p-22222222222222222222222222222222/c/conv-new",
        )
    assert exc.value.code is ErrorCode.POLICY_VIOLATION
    assert registry.resolve("bridge")["conversation_id"] == "conv-old"


def test_stale_pending_current_bind_is_replaced(tmp_path: Path):
    registry = _registry(tmp_path)
    first = registry.prepare_current_bind("bridge", session_id="mcp-session-1")
    data = json.loads(registry.path.read_text(encoding="utf-8"))
    data["current_binds"]["bridge"]["created_at"] = "2000-01-01T00:00:00+00:00"
    registry.path.write_text(json.dumps(data), encoding="utf-8")

    second = registry.prepare_current_bind("bridge", session_id="mcp-session-2")
    assert second["token"] != first["token"]
    assert second["session_id"] == "mcp-session-2"


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


def test_legacy_marker_search_discovery_surface_is_removed():
    assert not hasattr(WakeTransport, "discover_current_chat")
    assert "discover_and_bind_current_route" not in CoordinatorWakeDeliveryService.__dict__
    assert "discover_current_chat" not in ReviewGptWakeTransport.__dict__
    assert not (Path(__file__).parents[2] / "app/coordinator/review_gpt_discovery.mjs").exists()
