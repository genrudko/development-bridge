from __future__ import annotations

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.coordinator.service import CoordinatorService


@pytest.mark.asyncio
async def test_delivery_lease_exclusive_endpoint_fails_closed_for_different_session(tmp_path):
    service = CoordinatorService(tmp_path / "wakes.json")
    first = service.issue_delivery_lease("route-g1", session_id="session-a", route_id="route", generation=1)

    # Different second session while current heartbeat is active fails closed with POLICY_VIOLATION
    with pytest.raises(BridgeError) as exc_info:
        service.issue_delivery_lease("route-g1", session_id="session-b", route_id="route", generation=1)
    assert exc_info.value.code == ErrorCode.POLICY_VIOLATION

    # Preserves old lease
    preserved = service.delivery_lease("route-g1")
    assert preserved is not None
    assert preserved["lease_id"] == first["lease_id"]
    assert preserved["session_id"] == "session-a"

    # Missing session_id also fails closed
    with pytest.raises(BridgeError) as exc_info_anon:
        service.issue_delivery_lease("route-g1", session_id=None, route_id="route", generation=1)
    assert exc_info_anon.value.code == ErrorCode.POLICY_VIOLATION


@pytest.mark.asyncio
async def test_delivery_lease_same_session_remount_reuses_and_refreshes_lease(tmp_path):
    service = CoordinatorService(tmp_path / "wakes.json")
    first = service.issue_delivery_lease("route-g1", session_id="session-a", route_id="route", generation=1)
    same = service.issue_delivery_lease("route-g1", session_id="session-a", route_id="route", generation=1)
    assert same["lease_id"] == first["lease_id"]
    assert same["session_id"] == "session-a"


@pytest.mark.asyncio
async def test_delivery_lease_takeover_allowed_after_heartbeat_ttl_expires(tmp_path, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    service = CoordinatorService(tmp_path / "wakes.json")
    service.X_LISTENER_HEARTBEAT_TTL_SECONDS = 10.0
    first = service.issue_delivery_lease("route-g1", session_id="session-a", route_id="route", generation=1)

    clock[0] = 1005.0
    with pytest.raises(BridgeError) as exc_info:
        service.issue_delivery_lease("route-g1", session_id="session-b", route_id="route", generation=1)
    assert exc_info.value.code == ErrorCode.POLICY_VIOLATION

    # After TTL expiry, different session acquires new lease
    clock[0] = 1011.0
    second = service.issue_delivery_lease("route-g1", session_id="session-b", route_id="route", generation=1)
    assert second["lease_id"] != first["lease_id"]
    assert second["session_id"] == "session-b"


@pytest.mark.asyncio
async def test_delivery_lease_generation_turnover_allows_new_session(tmp_path):
    service = CoordinatorService(tmp_path / "wakes.json")
    first = service.issue_delivery_lease("route-g1", session_id="session-a", route_id="route", generation=1)

    # Generation turnover to generation 2 succeeds even with active heartbeat on gen 1
    second = service.issue_delivery_lease("route-g1", session_id="session-b", route_id="route", generation=2)
    assert second["lease_id"] != first["lease_id"]
    assert second["session_id"] == "session-b"
    assert second["generation"] == 2


@pytest.mark.asyncio
async def test_x_endpoints_reject_missing_or_stale_lease_when_lease_exists(tmp_path):
    service = CoordinatorService(tmp_path / "wakes.json")
    service.MIN_WEB_TURN_INTERVAL_SECONDS = 0
    lease = service.issue_delivery_lease("route-g1", session_id="session-a", route_id="route", generation=1)

    await service.arm("wake-one", channel_id="route-g1", delay_seconds=0)

    # Status with missing lease
    missing_status = await service.status("route-g1", delivery_lease=None, delivery_mode="x")
    assert missing_status["state"] == "standby"
    assert missing_status["ready"] is False
    assert missing_status.get("delivery_lease_required") is True

    # Status with stale lease
    stale_status = await service.status("route-g1", delivery_lease="stale-lease", delivery_mode="x")
    assert stale_status["state"] == "standby"
    assert stale_status["ready"] is False
    assert stale_status.get("delivery_lease_required") is True

    # Claim with missing lease
    missing_claim = await service.claim("route-g1", delivery_lease=None, delivery_mode="x")
    assert missing_claim["claimed"] is False
    assert missing_claim["state"] == "standby"
    assert missing_claim.get("delivery_lease_required") is True

    # Claim with stale lease
    stale_claim = await service.claim("route-g1", delivery_lease="stale-lease", delivery_mode="x")
    assert stale_claim["claimed"] is False
    assert stale_claim["state"] == "standby"
    assert stale_claim.get("delivery_lease_required") is True

    # Claim with valid lease succeeds
    valid_claim = await service.claim("route-g1", delivery_lease=lease["lease_id"], delivery_mode="x")
    assert valid_claim["claimed"] is True

    # Ack with missing lease
    missing_ack = await service.ack("route-g1", valid_claim["claim_id"], delivery_lease=None)
    assert missing_ack["acknowledged"] is False
    assert missing_ack["state"] == "standby"
    assert missing_ack.get("delivery_lease_required") is True

    # Ack with stale lease
    stale_ack = await service.ack("route-g1", valid_claim["claim_id"], delivery_lease="stale-lease")
    assert stale_ack["acknowledged"] is False
    assert stale_ack["state"] == "standby"
    assert stale_ack.get("delivery_lease_required") is True

    # Ack with valid lease succeeds
    valid_ack = await service.ack("route-g1", valid_claim["claim_id"], delivery_lease=lease["lease_id"])
    assert valid_ack["acknowledged"] is True


@pytest.mark.asyncio
async def test_direct_delivery_fallback_works_after_x_heartbeat_expires_when_lease_exists(
    tmp_path, monkeypatch
):
    clock = [1000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    service = CoordinatorService(tmp_path / "wakes.json")
    service.X_LISTENER_HEARTBEAT_TTL_SECONDS = 10.0
    service.issue_delivery_lease("route-g1", session_id="session-a", route_id="route", generation=1)

    await service.arm("wake-direct", channel_id="route-g1", delay_seconds=0)

    # Active heartbeat blocks direct fallback
    clock[0] = 1005.0
    direct_status = await service.status("route-g1", delivery_mode="direct")
    assert direct_status["state"] == "x_listener_active"
    assert direct_status["ready"] is False
    direct_claim = await service.claim("route-g1", delivery_mode="direct")
    assert direct_claim["claimed"] is False

    # After TTL expiry, direct fallback works without delivery lease
    clock[0] = 1012.0
    expired_status = await service.status("route-g1", delivery_mode="direct")
    assert expired_status["state"] == "pending"
    assert expired_status["ready"] is True
    expired_claim = await service.claim("route-g1", delivery_mode="direct")
    assert expired_claim["claimed"] is True


def test_delivery_lease_survives_bridge_restart(tmp_path):
    state = tmp_path / "wakes.json"
    first = CoordinatorService(state)
    lease = first.issue_delivery_lease("route-g2", session_id="session-a", route_id="route", generation=2)
    second = CoordinatorService(state)
    restored = second.delivery_lease("route-g2")
    assert restored is not None
    assert restored["lease_id"] == lease["lease_id"]
    assert restored["generation"] == 2


@pytest.mark.asyncio
async def test_current_explicit_delivery_lease_bypasses_browser_preflight(tmp_path):
    service = CoordinatorService(tmp_path / "wakes-x.json", browser_preflight_required=True)
    lease = service.issue_delivery_lease(
        "route-g3", session_id="session-current", route_id="route", generation=3
    )
    await service.arm_resilient("wake", channel_id="route-g3", delay_seconds=0)

    status = await service.status(
        "route-g3", delivery_lease=lease["lease_id"], delivery_mode="x"
    )
    assert status["state"] == "pending"
    assert status["ready"] is True
    claim = await service.claim(
        "route-g3", delivery_lease=lease["lease_id"], delivery_mode="x"
    )
    assert claim["claimed"] is True


@pytest.mark.asyncio
async def test_recent_x_listener_blocks_direct_fallback_until_heartbeat_expires(
    tmp_path, monkeypatch
):
    clock = [1000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    service = CoordinatorService(tmp_path / "wakes-heartbeat.json", browser_preflight_required=True)
    service.X_LISTENER_HEARTBEAT_TTL_SECONDS = 10.0
    lease = service.issue_delivery_lease(
        "route-g4", session_id="session-current", route_id="route", generation=4
    )
    await service.arm_resilient("wake", channel_id="route-g4", delay_seconds=0)

    clock[0] = 1008.0
    await service.status("route-g4", delivery_lease=lease["lease_id"], delivery_mode="x")
    clock[0] = 1015.0
    direct = await service.status("route-g4", delivery_mode="direct")
    assert direct["state"] == "x_listener_active"
    assert direct["ready"] is False

    clock[0] = 1019.0
    direct_after_expiry = await service.status("route-g4", delivery_mode="direct")
    assert direct_after_expiry["state"] == "pending"
    assert direct_after_expiry["ready"] is True

@pytest.mark.asyncio
async def test_restart_grace_blocks_direct_fallback_until_x_listener_can_reconnect(
    tmp_path, monkeypatch
):
    clock = [2000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    path = tmp_path / "wakes-restart-grace.json"

    first = CoordinatorService(path, browser_preflight_required=True)
    first.X_LISTENER_HEARTBEAT_TTL_SECONDS = 10.0
    lease = first.issue_delivery_lease(
        "route-g5", session_id="session-current", route_id="route", generation=5
    )
    await first.arm_resilient("wake", channel_id="route-g5", delay_seconds=0)

    # The last persisted lease refresh is deliberately older than the restart.
    clock[0] = 2020.0
    restarted = CoordinatorService(path, browser_preflight_required=True)
    restarted.X_LISTENER_HEARTBEAT_TTL_SECONDS = 10.0

    direct_status = await restarted.status("route-g5", delivery_mode="direct")
    assert direct_status["state"] == "x_listener_active"
    assert direct_status["ready"] is False
    assert (
        await restarted.claim("route-g5", delivery_mode="direct")
    )["claimed"] is False

    # Once the mounted X listener reconnects, its current lease refresh extends priority.
    clock[0] = 2028.0
    x_status = await restarted.status(
        "route-g5", delivery_lease=lease["lease_id"], delivery_mode="x"
    )
    assert x_status["x_listener_active"] is True

    clock[0] = 2035.0
    assert (await restarted.status("route-g5", delivery_mode="direct"))["state"] == "x_listener_active"

    clock[0] = 2039.0
    expired = await restarted.status("route-g5", delivery_mode="direct")
    assert expired["state"] == "pending"
    assert expired["ready"] is True

@pytest.mark.asyncio
async def test_direct_claim_rechecks_x_heartbeat_after_waiting_for_coordinator_lock(
    tmp_path, monkeypatch
):
    import asyncio

    clock = [3000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    service = CoordinatorService(tmp_path / "wakes-race.json", browser_preflight_required=True)
    service.X_LISTENER_HEARTBEAT_TTL_SECONDS = 10.0
    lease = service.issue_delivery_lease(
        "route-g6", session_id="session-current", route_id="route", generation=6
    )
    await service.arm_resilient("wake", channel_id="route-g6", delay_seconds=0)

    # Let the original heartbeat expire, then force direct to snapshot liveness and
    # wait on the coordinator lock before X refreshes the same current lease.
    clock[0] = 3011.0
    async with service._lock:
        direct_task = asyncio.create_task(
            service.claim("route-g6", delivery_mode="direct")
        )
        await asyncio.sleep(0)
        x_task = asyncio.create_task(
            service.status(
                "route-g6", delivery_lease=lease["lease_id"], delivery_mode="x"
            )
        )
        await asyncio.sleep(0)

    direct = await direct_task
    x_status = await x_task

    assert x_status["x_listener_active"] is True
    assert direct["claimed"] is False
    assert (await service.status("route-g6", delivery_mode="direct"))["state"] == "x_listener_active"

@pytest.mark.asyncio
async def test_x_claim_revalidates_explicit_lease_after_waiting_for_coordinator_lock(
    tmp_path, monkeypatch
):
    import asyncio

    clock = [4000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    service = CoordinatorService(tmp_path / "wakes-rotation.json", browser_preflight_required=True)
    old = service.issue_delivery_lease(
        "route-g7", session_id="session-old", route_id="route", generation=7
    )
    await service.arm_resilient("wake", channel_id="route-g7", delay_seconds=0)

    async with service._lock:
        stale_claim_task = asyncio.create_task(
            service.claim(
                "route-g7", delivery_lease=old["lease_id"], delivery_mode="x"
            )
        )
        await asyncio.sleep(0)
        new = service.issue_delivery_lease(
            "route-g7", session_id="session-new", route_id="route", generation=8
        )
        assert new["lease_id"] != old["lease_id"]

    stale = await stale_claim_task
    assert stale["claimed"] is False
    assert stale.get("state") == "standby"
    current = await service.claim(
        "route-g7", delivery_lease=new["lease_id"], delivery_mode="x"
    )
    assert current["claimed"] is True


@pytest.mark.asyncio
async def test_direct_status_uses_lock_time_when_x_heartbeat_expires_while_waiting(
    tmp_path, monkeypatch
):
    import asyncio

    clock = [5000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    service = CoordinatorService(tmp_path / "wakes-expiry-race.json", browser_preflight_required=True)
    service.X_LISTENER_HEARTBEAT_TTL_SECONDS = 10.0
    service.issue_delivery_lease(
        "route-g8", session_id="session-current", route_id="route", generation=8
    )
    await service.arm_resilient("wake", channel_id="route-g8", delay_seconds=0)

    clock[0] = 5005.0
    async with service._lock:
        direct_status_task = asyncio.create_task(
            service.status("route-g8", delivery_mode="direct")
        )
        await asyncio.sleep(0)
        clock[0] = 5012.0

    direct = await direct_status_task
    assert direct["state"] == "pending"
    assert direct["ready"] is True


@pytest.mark.asyncio
async def test_x_ack_revalidates_explicit_lease_after_waiting_for_coordinator_lock(
    tmp_path, monkeypatch
):
    import asyncio

    clock = [6000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    service = CoordinatorService(tmp_path / "wakes-ack-race.json", browser_preflight_required=True)
    service.MIN_WEB_TURN_INTERVAL_SECONDS = 0
    old = service.issue_delivery_lease(
        "route-g9", session_id="session-old", route_id="route", generation=9
    )
    await service.arm_resilient(
        "wake-ack",
        channel_id="route-g9",
        delay_seconds=0,
        retry_delays_seconds=[0.0, 0.0],
    )

    old_claim = await service.claim(
        "route-g9", delivery_lease=old["lease_id"], delivery_mode="x"
    )
    assert old_claim["claimed"] is True
    claim_id = old_claim["claim_id"]

    async with service._lock:
        old_ack_task = asyncio.create_task(
            service.ack("route-g9", claim_id, delivery_lease=old["lease_id"])
        )
        await asyncio.sleep(0)
        new = service.issue_delivery_lease(
            "route-g9", session_id="session-new", route_id="route", generation=10
        )
        assert new["lease_id"] != old["lease_id"]

    old_ack = await old_ack_task
    assert old_ack["acknowledged"] is False
    assert old_ack.get("state") == "standby"
    assert old_ack.get("delivery_lease_required") is True

    wake = service._pending.get("route-g9")
    assert wake is not None
    assert wake.transport_delivered is False
    assert wake.transport_delivered_at is None
    assert wake.claim_id == claim_id
    assert wake.lease_expires_at is not None

    clock[0] = wake.lease_expires_at + 1.0
    current_claim = await service.claim(
        "route-g9", delivery_lease=new["lease_id"], delivery_mode="x"
    )
    assert current_claim["claimed"] is True
    current_ack = await service.ack(
        "route-g9", current_claim["claim_id"], delivery_lease=new["lease_id"]
    )
    assert current_ack["acknowledged"] is True
    assert current_ack.get("transport_delivered") is True

    wake_after = service._pending.get("route-g9")
    assert wake_after is not None
    assert wake_after.transport_delivered is True
