from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from app.coordinator.review_gpt_transport import (
    classify_probe_failure,
    default_process_runner,
)
from app.coordinator.routes import RouteRegistry
from app.coordinator.service import CoordinatorService
from app.coordinator.wake_delivery import CoordinatorWakeDeliveryService
from app.coordinator.wake_transport import (
    WakeDeliveryResult,
    WakeProbeResult,
)


@pytest.mark.parametrize(("message", "expected"), [
    ("ChatGPT target is actively generating (statusBusy or stopVisible)", "busy"),
    ("Process timed out after 60s", "timeout"),
    ("Cloudflare challenge detected: Just a moment", "authentication_required"),
    ("connect ECONNREFUSED 127.0.0.1:9222", "browser_unavailable"),
    ("Target chat URL mismatch", "target_mismatch"),
    ("Unexpected CLI failure", "unknown"),
])
def test_probe_disposition_categories(message: str, expected: str) -> None:
    assert classify_probe_failure(message) == expected


@pytest.mark.asyncio
async def test_runner_process_timeout_kills_child() -> None:
    with pytest.raises(TimeoutError, match="Process timed out"):
        await asyncio.wait_for(
            default_process_runner([sys.executable, "-c", "import time;time.sleep(20)"], 0.05),
            timeout=2.0,
        )


@pytest.mark.asyncio
async def test_runner_cancellation_does_not_hang() -> None:
    task = asyncio.create_task(
        default_process_runner([sys.executable, "-c", "import time;time.sleep(20)"], 60.0)
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=2.0)


@pytest.mark.asyncio
async def test_slow_probe_does_not_indefinitely_starve_another_route(tmp_path: Path) -> None:
    coordinator = CoordinatorService(tmp_path / "wakes.json", browser_preflight_required=True)
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap("aaa-slow", "https://chatgpt.com/c/11111-uuid", "channel-slow", "Slow")
    registry.bootstrap("bbb-ready", "https://chatgpt.com/c/22222-uuid", "channel-ready", "Ready")
    await coordinator.arm_resilient("slow route", channel_id="channel-slow", delay_seconds=0)
    await coordinator.arm_resilient("ready route", channel_id="channel-ready", delay_seconds=0)

    class Transport:
        name = "test"

        def __init__(self):
            self.deliveries = []

        async def probe(self, target):
            if target.route_id == "aaa-slow":
                await asyncio.Event().wait()
            return WakeProbeResult(ready=True, disposition="ready")

        async def deliver(self, request):
            self.deliveries.append(request)
            return WakeDeliveryResult(disposition="delivered")

    transport = Transport()
    service = CoordinatorWakeDeliveryService(
        coordinator, registry, transport=transport, enabled=True,
        probe_timeout_seconds=1.0,
    )
    await asyncio.wait_for(service.run_once(), timeout=3.0)
    assert [r.target.route_id for r in transport.deliveries] == ["bbb-ready"]
    slow = await coordinator.status("channel-slow", delivery_mode="direct")
    assert slow["state"] in {"pending", "web_cooldown"}
    assert slow["delivery_attempts"] == 0
    assert slow["transport_delivered"] is False
    ready = await coordinator.status("channel-ready", delivery_mode="direct")
    assert ready["transport_delivered"] is True


@pytest.mark.asyncio
async def test_expired_unclaimed_wake_recovers_only_through_direct_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [1000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    coordinator = CoordinatorService(browser_preflight_required=True)
    coordinator.MAX_UNDELIVERED_AGE_SECONDS = 30.0
    await coordinator.arm_resilient("resume", channel_id="old", delay_seconds=0)

    clock[0] = 1045.0
    old_x = await coordinator.status("old", delivery_mode="x")
    direct = await coordinator.status("old", delivery_mode="direct")
    assert old_x["state"] == "escalation_due"
    assert old_x["ready"] is False
    assert direct["ready"] is True
    assert (await coordinator.claim("old", delivery_mode="x"))["claimed"] is False
    assert (await coordinator.claim("old", delivery_mode="direct"))["claimed"] is True


@pytest.mark.asyncio
async def test_expired_x_listener_cannot_starve_direct_wake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [1000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    coordinator = CoordinatorService(browser_preflight_required=True)
    coordinator.MAX_UNDELIVERED_AGE_SECONDS = 30.0
    await coordinator.arm_resilient("direct fallback", channel_id="active-x", delay_seconds=0)
    lease = coordinator.issue_delivery_lease(
        "active-x", route_id="energologic", generation=0,
    )["lease_id"]

    # The legitimate X client is still polling after the X delivery window
    # expires, so the status heartbeat is fresh but X is not eligible to claim.
    clock[0] = 1045.0
    x_status = await coordinator.status("active-x", delivery_lease=lease)
    assert x_status["x_listener_active"] is True
    assert x_status["ready"] is False
    assert x_status["state"] == "escalation_due"
    direct = await coordinator.status("active-x", delivery_mode="direct")
    assert direct["x_listener_active"] is True
    assert direct["ready"] is True

    assert (await coordinator.claim(
        "active-x", delivery_lease=lease, delivery_mode="x",
    ))["claimed"] is False
    direct_claim = await coordinator.claim("active-x", delivery_mode="direct")
    assert direct_claim["claimed"] is True
    assert (await coordinator.claim(
        "active-x", delivery_lease=lease, delivery_mode="x",
    ))["claimed"] is False


@pytest.mark.asyncio
async def test_fresh_x_listener_retains_exclusive_delivery_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [1000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    coordinator = CoordinatorService(browser_preflight_required=True)
    await coordinator.arm_resilient("fresh", channel_id="active-x", delay_seconds=0)
    lease = coordinator.issue_delivery_lease(
        "active-x", route_id="energologic", generation=0,
    )["lease_id"]
    x_status = await coordinator.status("active-x", delivery_lease=lease)
    assert x_status["ready"] is True
    direct = await coordinator.status("active-x", delivery_mode="direct")
    assert direct["ready"] is False
    assert direct["state"] == "x_listener_active"
    assert (await coordinator.claim("active-x", delivery_mode="direct"))["claimed"] is False


@pytest.mark.asyncio
async def test_five_minute_delayed_direct_fallback_despite_active_x_polls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [1000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    coordinator = CoordinatorService(browser_preflight_required=True)
    await coordinator.arm_resilient(
        "five minute wake", channel_id="direct-delayed", delay_seconds=300,
    )
    lease = coordinator.issue_delivery_lease(
        "direct-delayed", route_id="energologic", generation=0,
    )["lease_id"]

    clock[0] = 1299.0
    await coordinator.status("direct-delayed", delivery_lease=lease)
    assert (await coordinator.status("direct-delayed", delivery_mode="direct"))["ready"] is False

    clock[0] = 1305.0
    await coordinator.status("direct-delayed", delivery_lease=lease)
    assert (await coordinator.status("direct-delayed", delivery_mode="direct"))["ready"] is False

    clock[0] = 1321.0
    x_status = await coordinator.status("direct-delayed", delivery_lease=lease)
    assert x_status["x_listener_active"] and x_status["ready"]
    direct = await coordinator.status("direct-delayed", delivery_mode="direct")
    assert direct["ready"] is True and direct["x_listener_active"] is True
    assert (await coordinator.claim("direct-delayed", delivery_mode="direct"))["claimed"] is True
    assert (await coordinator.claim(
        "direct-delayed", delivery_mode="x", delivery_lease=lease,
    ))["claimed"] is False


@pytest.mark.asyncio
async def test_atomic_claim_prevents_direct_duplicate_if_x_claims_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [1000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    coordinator = CoordinatorService(browser_preflight_required=True)
    await coordinator.arm_resilient("one delivery", channel_id="race", delay_seconds=0)
    lease = coordinator.issue_delivery_lease(
        "race", route_id="energologic", generation=0,
    )["lease_id"]
    clock[0] = 1025.0
    assert (await coordinator.status("race", delivery_lease=lease))["ready"] is True
    assert (await coordinator.status("race", delivery_mode="direct"))["ready"] is True
    assert (await coordinator.claim("race", delivery_lease=lease))["claimed"] is True
    assert (await coordinator.claim("race", delivery_mode="direct"))["claimed"] is False


@pytest.mark.asyncio
async def test_escalation_without_custom_message_does_not_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [1000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    coordinator = CoordinatorService(browser_preflight_required=False)
    await coordinator.arm_resilient(
        "wake", channel_id="escalation", retry_delays_seconds=(),
        escalation_message=None,
    )
    assert (await coordinator.claim("escalation"))["claimed"] is True
    clock[0] = 1100.0
    due = await coordinator.escalations_due()
    assert len(due) == 1
    assert "requires delivery review" in due[0]["escalation_message"]


@pytest.mark.asyncio
async def test_preclaim_login_block_is_retried_and_wake_is_sent_once(tmp_path: Path) -> None:
    coordinator = CoordinatorService(tmp_path / "wakes.json", browser_preflight_required=True)
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap("main", "https://chatgpt.com/c/11111-uuid", "channel-main", "Main")
    await coordinator.arm_resilient("resume", channel_id="channel-main", delay_seconds=0)

    class Transport:
        name = "review-gpt"

        def __init__(self):
            self.probes = 0
            self.deliveries = []

        async def probe(self, target):
            self.probes += 1
            if self.probes == 1:
                return WakeProbeResult(
                    ready=False, owner_input_required=True,
                    detail="Log in required", disposition="authentication_required",
                )
            return WakeProbeResult(ready=True, disposition="ready")

        async def deliver(self, request):
            self.deliveries.append(request)
            return WakeDeliveryResult(disposition="delivered")

    transport = Transport()
    service = CoordinatorWakeDeliveryService(
        coordinator, registry, transport=transport, enabled=True,
    )
    await service.run_once()
    blocked = await coordinator.status("channel-main", delivery_mode="direct")
    assert blocked["state"] == "owner_input_required"
    assert blocked["delivery_attempts"] == 0
    assert transport.deliveries == []

    # Simulate passage of the recovery interval without waiting a minute.
    service._auth_reprobe_after["main"] = 0.0
    await service.run_once()
    released = await coordinator.status("channel-main", delivery_mode="direct")
    assert released["ready"] is True
    assert released["delivery_attempts"] == 0
    assert transport.deliveries == []

    await service.run_once()
    assert len(transport.deliveries) == 1
    assert (await coordinator.status("channel-main", delivery_mode="direct"))["transport_delivered"] is True
    await service.run_once()
    assert len(transport.deliveries) == 1


@pytest.mark.asyncio
async def test_legacy_probe_auth_block_recovers_without_duplicate(tmp_path: Path) -> None:
    coordinator = CoordinatorService(tmp_path / "wakes.json", browser_preflight_required=True)
    await coordinator.arm_resilient("old wake", channel_id="legacy", delay_seconds=0)
    claim = await coordinator.claim("legacy", delivery_mode="direct")
    assert claim["claimed"]
    await coordinator.finalize_transport(
        "legacy", claim["claim_id"], "review-gpt", "owner_input_required",
        detail="Probe failed with exit code 1: Log in required",
    )
    assert (await coordinator.status("legacy", delivery_mode="direct"))["delivery_attempts"] == 1
    cleared = await coordinator.clear_preclaim_auth_block(
        "legacy", claim["continuation_id"], "review-gpt",
    )
    assert cleared["released"] is True
    status = await coordinator.status("legacy", delivery_mode="direct")
    assert status["delivery_attempts"] == 0
    assert status["ready"] is True


@pytest.mark.asyncio
async def test_possible_post_send_auth_failure_cannot_auto_release(tmp_path: Path) -> None:
    coordinator = CoordinatorService(tmp_path / "wakes.json", browser_preflight_required=True)
    await coordinator.arm_resilient("unsafe to replay", channel_id="uncertain", delay_seconds=0)
    claim = await coordinator.claim("uncertain", delivery_mode="direct")
    assert claim["claimed"]
    await coordinator.finalize_transport(
        "uncertain", claim["claim_id"], "review-gpt", "owner_input_required",
        detail="Browser or login intervention required after send",
    )
    cleared = await coordinator.clear_preclaim_auth_block(
        "uncertain", claim["continuation_id"], "review-gpt",
    )
    assert cleared["released"] is False
    assert (await coordinator.status("uncertain", delivery_mode="direct"))["ready"] is False


@pytest.mark.asyncio
async def test_telegram_notice_persists_without_discarding_durable_wake(tmp_path: Path) -> None:
    path = tmp_path / "wakes.json"
    coordinator = CoordinatorService(path, browser_preflight_required=True)
    coordinator.MAX_UNDELIVERED_AGE_SECONDS = 0.1
    armed = await coordinator.arm_resilient("recover later", channel_id="persisted", delay_seconds=0)
    await asyncio.sleep(0.12)
    due = await coordinator.escalations_due()
    assert len(due) == 1
    result = await coordinator.mark_escalation_notified(armed["continuation_id"])
    assert result["notified"] is True

    restored = CoordinatorService(path, browser_preflight_required=True)
    restored.MAX_UNDELIVERED_AGE_SECONDS = 0.1
    assert await restored.escalations_due() == []
    direct = await restored.status("persisted", delivery_mode="direct")
    assert direct["continuation_id"] == armed["continuation_id"]
    assert direct["ready"] is True
    assert direct["delivery_attempts"] == 0
