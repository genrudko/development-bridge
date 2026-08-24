from __future__ import annotations

from pathlib import Path

import pytest

from app.api.errors import BridgeError
from app.coordinator.routes import RouteRegistry


def test_route_registry_bootstrap_select_and_takeover(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    first = registry.bootstrap("ad5x", "https://chatgpt.com/g/g-p-project/c/conv-a?x=1", "telegram-supervisor", "Cold Wake Test")
    assert first["generation"] == 0
    assert first["conversation_id"] == "conv-a"
    assert registry.resolve()["route_id"] == "ad5x"
    assert registry.snapshot()["requested_route"] == "ad5x"
    next_route = registry.takeover("ad5x", "https://chatgpt.com/g/g-p-project/c/conv-b", "AD5X continuation")
    assert next_route["generation"] == 1
    assert next_route["channel_id"] == "telegram-ad5x-g1"
    assert registry.resolve()["conversation_id"] == "conv-b"
    registry.bootstrap("bridge-dev", "https://chatgpt.com/c/conv-c", "telegram-bridge")
    selected = registry.select_default("bridge-dev")
    assert selected["default"] is True
    assert registry.snapshot()["requested_route"] == "bridge-dev"
    assert registry.resolve()["route_id"] == "bridge-dev"


def test_route_registry_rejects_unknown_default(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    with pytest.raises(BridgeError):
        registry.select_default("missing")


def test_route_registry_reads_browser_discovery(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    (tmp_path / "chat-registry.json").write_text(
        '{"version":1,"chats":{"c1":{"conversation_id":"c1","title":"One","last_seen":"2026-08-24T00:00:00+00:00"},"c2":{"conversation_id":"c2","title":"Two","last_seen":"2026-08-24T01:00:00+00:00"}}}',
        encoding="utf-8",
    )
    chats = registry.list_discovered_chats(limit=1)
    assert [item["conversation_id"] for item in chats] == ["c2"]
