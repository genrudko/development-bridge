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


def test_route_registry_rollover_is_fail_safe_until_commit(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    original = registry.bootstrap(
        "ad5x", "https://chatgpt.com/g/g-p-project/c/conv-a",
        "telegram-ad5x-g5", "AD5X",
    )
    prepared = registry.prepare_rollover("ad5x")
    assert prepared["state"] == "prepared"
    assert prepared["target_generation"] == 1
    assert prepared["channel_id"] == "telegram-ad5x-g1"
    assert registry.prepare_rollover("ad5x")["token"] == prepared["token"]
    assert registry.resolve("ad5x")["conversation_id"] == original["conversation_id"]

    candidate = registry.record_rollover_candidate(
        "ad5x", prepared["token"],
        "https://chatgpt.com/g/g-p-project/c/conv-b?temporary=1",
    )
    assert candidate["state"] == "candidate"
    assert candidate["candidate_conversation_id"] == "conv-b"
    assert registry.resolve("ad5x")["conversation_id"] == "conv-a"

    committed = registry.commit_rollover("ad5x", prepared["token"])
    assert committed["conversation_id"] == "conv-b"
    assert committed["generation"] == 1
    assert committed["channel_id"] == "telegram-ad5x-g1"
    assert registry.pending_rollover("ad5x") is None
    snapshot = registry.snapshot()
    assert snapshot["last_rollover"]["ad5x"]["bootstrap_sent"] is False
    completed = registry.complete_rollover("ad5x", prepared["token"])
    assert completed["state"] == "complete"
    assert completed["bootstrap_sent"] is True


def test_route_registry_rollover_rejects_wrong_project_and_can_abort(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "ad5x", "https://chatgpt.com/g/g-p-project/c/conv-a",
        "telegram-ad5x-g5",
    )
    prepared = registry.prepare_rollover("ad5x")
    with pytest.raises(BridgeError):
        registry.record_rollover_candidate(
            "ad5x", prepared["token"],
            "https://chatgpt.com/g/g-p-other/c/conv-b",
        )
    aborted = registry.abort_rollover("ad5x", prepared["token"], "verification failed")
    assert aborted["aborted"] is True
    assert registry.resolve("ad5x")["conversation_id"] == "conv-a"
    assert registry.pending_rollover("ad5x") is None


def test_manual_takeover_is_rejected_while_rollover_pending(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "ad5x", "https://chatgpt.com/g/g-p-project/c/conv-a",
        "telegram-ad5x-g5",
    )
    registry.prepare_rollover("ad5x")
    with pytest.raises(BridgeError):
        registry.takeover(
            "ad5x", "https://chatgpt.com/g/g-p-project/c/conv-b"
        )
    assert registry.resolve("ad5x")["conversation_id"] == "conv-a"
