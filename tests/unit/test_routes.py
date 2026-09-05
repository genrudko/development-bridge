from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.api.errors import BridgeError, ErrorCode
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
        "https://chatgpt.com/g/g-p-project-plaginy-ad5x/c/conv-b?temporary=1",
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


def test_unbind_invalidates_pending_rollover_and_consumes_reserved_generation(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    active = registry.bootstrap(
        "ad5x", "https://chatgpt.com/g/g-p-project/c/conv-a",
        "telegram-ad5x-g0",
    )
    prepared = registry.prepare_rollover("ad5x")
    registry.record_rollover_candidate(
        "ad5x", prepared["token"],
        "https://chatgpt.com/g/g-p-project/c/conv-b",
    )

    unbound = registry.unbind("ad5x", expected_generation=active["generation"])

    assert registry.pending_rollover("ad5x") is None
    assert unbound["generation"] == prepared["target_generation"]
    assert unbound["channel_id"] == prepared["channel_id"]
    with pytest.raises(BridgeError, match="invalid or stale"):
        registry.commit_rollover("ad5x", prepared["token"])

    rebound = registry.takeover(
        "ad5x", "https://chatgpt.com/g/g-p-project/c/conv-c"
    )
    assert rebound["generation"] == prepared["target_generation"] + 1
    assert rebound["channel_id"] == "telegram-ad5x-g2"


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


def test_takeover_rejects_different_project_and_preserves_old_route(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    original = registry.bootstrap(
        "ad5x", "https://chatgpt.com/g/g-p-11111111111111111111111111111111-old-slug/c/conv-a",
        "telegram-ad5x-g0", "AD5X Project A",
    )
    assert original["generation"] == 0
    assert original["conversation_id"] == "conv-a"
    assert original["project_id"] == "g-p-11111111111111111111111111111111-old-slug"

    with pytest.raises(BridgeError) as exc_info:
        registry.takeover("ad5x", "https://chatgpt.com/g/g-p-22222222222222222222222222222222-other/c/conv-b")
    assert exc_info.value.code == ErrorCode.POLICY_VIOLATION
    assert "different project" in str(exc_info.value)

    # Prove the old route is preserved unchanged
    preserved = registry.resolve("ad5x")
    assert preserved["conversation_id"] == "conv-a"
    assert preserved["project_id"] == "g-p-11111111111111111111111111111111-old-slug"
    assert preserved["generation"] == 0
    assert preserved["channel_id"] == "telegram-ad5x-g0"

    # Prove same-project takeover is permitted
    taken_over = registry.takeover("ad5x", "https://chatgpt.com/g/g-p-11111111111111111111111111111111-new-slug/c/conv-b")
    assert taken_over["generation"] == 1
    assert taken_over["conversation_id"] == "conv-b"
    assert registry.resolve("ad5x")["conversation_id"] == "conv-b"


@pytest.mark.asyncio
async def test_route_registry_route_lock_reentrancy_and_exclusion(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    lock = registry.route_lock("test-route")

    # Reentrancy within the same task
    async with lock:
        assert lock.locked()
        async with lock:
            assert lock.locked()

    assert not lock.locked()

    # Release without acquire
    with pytest.raises(RuntimeError):
        lock.release()

    # Mutual exclusion across tasks
    acquired_task2 = False
    task1_hold = asyncio.Event()
    task1_can_release = asyncio.Event()

    async def task1():
        async with registry.route_lock("test-route"):
            task1_hold.set()
            await task1_can_release.wait()

    async def task2():
        nonlocal acquired_task2
        async with registry.route_lock("test-route"):
            acquired_task2 = True

    t1 = asyncio.create_task(task1())
    await task1_hold.wait()
    t2 = asyncio.create_task(task2())
    await asyncio.sleep(0.01)
    assert not acquired_task2

    task1_can_release.set()
    await t1
    await t2
    assert acquired_task2


@pytest.mark.parametrize("change", ["unbind", "channel", "url", "abort", "generation"])
def test_rollover_completion_rejects_invalid_successor(tmp_path, change):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap("ad5x", "https://chatgpt.com/g/g-p-ad5x/c/old", "telegram-ad5x-g0")
    pending = registry.prepare_rollover("ad5x")
    registry.record_rollover_candidate("ad5x", pending["token"], "https://chatgpt.com/g/g-p-ad5x/c/new")
    registry.commit_rollover("ad5x", pending["token"])
    if change == "unbind":
        registry.unbind("ad5x", expected_generation=1)
    else:
        data = registry._load()
        if change == "abort":
            data["last_rollover"]["ad5x"]["state"] = "aborted"
        else:
            field, value = {"channel": ("channel_id", "wrong"), "url": ("url", "https://chatgpt.com/g/g-p-ad5x/c/wrong"), "generation": ("generation", 2)}[change]
            data["routes"]["ad5x"][field] = value
        registry._save(data)
    with pytest.raises(BridgeError, match="invalid or stale"):
        registry.complete_rollover("ad5x", pending["token"])
    assert registry._load()["last_rollover"]["ad5x"]["bootstrap_sent"] is False
