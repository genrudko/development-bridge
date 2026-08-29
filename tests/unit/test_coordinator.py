from __future__ import annotations

import asyncio

import pytest

from app.api.errors import BridgeError
from app.coordinator import CoordinatorService


@pytest.mark.asyncio
async def test_wake_coalesces_and_rejects_without_growing_queue():
    service = CoordinatorService()
    first = await service.arm("first", delay_seconds=0)
    second = await service.arm("second", delay_seconds=0)
    assert first["coalesced"] is False
    assert second["coalesced"] is True
    claim = await service.claim()
    assert claim["claimed"] is True
    assert claim["message"] == "second"
    with pytest.raises(BridgeError):
        await service.arm("third", delay_seconds=0, conflict="reject")


@pytest.mark.asyncio
async def test_delay_claim_ack_and_lease_retry_prevent_duplicate_claims():
    service = CoordinatorService()
    service.LEASE_SECONDS = 0.02
    await service.arm("wake", channel_id="stable", delay_seconds=0.02)
    assert (await service.claim("stable"))["claimed"] is False
    await asyncio.sleep(0.025)
    claims = await asyncio.gather(service.claim("stable"), service.claim("stable"))
    assert sum(item["claimed"] for item in claims) == 1
    winner = next(item for item in claims if item["claimed"])
    assert (await service.claim("stable"))["claimed"] is False
    await asyncio.sleep(0.025)
    retry = await service.claim("stable")
    assert retry["claimed"] is True
    assert retry["claim_id"] != winner["claim_id"]
    assert (await service.ack("stable", winner["claim_id"]))["acknowledged"] is False
    assert (await service.ack("stable", retry["claim_id"]))["acknowledged"] is True
    assert (await service.status("stable"))["state"] == "idle"


@pytest.mark.asyncio
async def test_pending_wake_survives_service_restart(tmp_path):
    path = tmp_path / "coordinator-wakes.json"
    first = CoordinatorService(path)
    await first.arm("resume", channel_id="route-g1", delay_seconds=0)

    second = CoordinatorService(path)
    status = await second.status("route-g1")
    assert status["state"] == "pending"
    assert status["ready"] is True
    claim = await second.claim("route-g1")
    assert claim["claimed"] is True
    assert claim["message"] == "resume"

    third = CoordinatorService(path)
    persisted = await third.status("route-g1")
    assert persisted["state"] == "claimed"
    assert (await third.ack("route-g1", claim["claim_id"]))["acknowledged"] is True
    assert CoordinatorService(path)._pending == {}


@pytest.mark.asyncio
async def test_successful_transport_delivery_waits_for_model_ack_without_redelivery():
    service = CoordinatorService()
    armed = await service.arm_resilient(
        "resume", channel_id="route-g2", retry_delays_seconds=(0, 0),
        escalation_delay_seconds=60, escalation_message="escalate",
    )
    first = await service.claim("route-g2")
    assert first["delivery_attempt"] == 1
    transport = await service.ack("route-g2", first["claim_id"])
    assert transport["transport_delivered"] is True
    assert (await service.claim("route-g2"))["claimed"] is False
    status = await service.status("route-g2")
    assert status["state"] == "waiting_model_ack"
    assert status["transport_delivered"] is True
    acked = await service.model_ack(armed["continuation_id"])
    assert acked["acknowledged"] is True
    assert (await service.status("route-g2"))["state"] == "idle"


@pytest.mark.asyncio
async def test_transport_failures_retry_three_claims_then_escalate():
    service = CoordinatorService()
    service.LEASE_SECONDS = 0
    armed = await service.arm_resilient(
        "resume", channel_id="route-g2", retry_delays_seconds=(0, 0),
        escalation_delay_seconds=0, escalation_message="telegram fallback",
    )
    for expected_attempt in (1, 2, 3):
        claim = await service.claim("route-g2")
        assert claim["claimed"] is True
        assert claim["delivery_attempt"] == expected_attempt
    due = await service.escalations_due()
    assert len(due) == 1
    assert due[0]["continuation_id"] == armed["continuation_id"]
    assert due[0]["delivery_attempts"] == 3
    assert due[0]["escalation_message"] == "telegram fallback"
    assert (await service.claim("route-g2"))["claimed"] is False


@pytest.mark.asyncio
async def test_transport_retry_state_survives_restart(tmp_path):
    path = tmp_path / "coordinator-wakes.json"
    first_service = CoordinatorService(path)
    first_service.LEASE_SECONDS = 0
    armed = await first_service.arm_resilient(
        "resume", channel_id="route-g2", retry_delays_seconds=(0, 0), escalation_delay_seconds=0
    )
    first_claim = await first_service.claim("route-g2")
    assert first_claim["delivery_attempt"] == 1
    second_service = CoordinatorService(path)
    second_service.LEASE_SECONDS = 0
    second_claim = await second_service.claim("route-g2")
    assert second_claim["claimed"] is True
    assert second_claim["delivery_attempt"] == 2
    assert second_claim["continuation_id"] == armed["continuation_id"]


@pytest.mark.asyncio
async def test_model_ack_during_transport_claim_prevents_retry():
    service = CoordinatorService()
    armed = await service.arm_resilient("resume", channel_id="route-g2", retry_delays_seconds=(0, 0), escalation_delay_seconds=0)
    claim = await service.claim("route-g2")
    acked = await service.model_ack(armed["continuation_id"])
    assert acked["continuation_id"] == armed["continuation_id"]
    transport = await service.ack("route-g2", claim["claim_id"])
    assert transport["acknowledged"] is True
    assert (await service.status("route-g2"))["state"] == "idle"
    assert (await service.claim("route-g2"))["claimed"] is False


@pytest.mark.asyncio
async def test_model_ack_cleans_up_after_lost_transport_ack_lease_expires():
    service = CoordinatorService()
    service.LEASE_SECONDS = 0.01
    armed = await service.arm_resilient("resume", channel_id="route-g2", retry_delays_seconds=(0, 0))
    await service.claim("route-g2")
    acked = await service.model_ack(armed["continuation_id"])
    assert acked["acknowledged"] is True
    await asyncio.sleep(0.015)
    assert (await service.status("route-g2"))["state"] == "idle"


@pytest.mark.asyncio
async def test_resilient_events_batch_before_first_delivery_and_deduplicate():
    service = CoordinatorService()
    first = await service.arm_resilient("A", channel_id="route-g2")
    second = await service.arm_resilient("B", channel_id="route-g2")
    duplicate = await service.arm_resilient("A", channel_id="route-g2")
    assert second["continuation_id"] == first["continuation_id"]
    assert second["batch_size"] == 2
    assert duplicate["deduplicated"] is True
    claim = await service.claim("route-g2")
    assert claim["continuation_id"] == first["continuation_id"]
    assert claim["message"].split(service.BATCH_SEPARATOR) == ["A", "B"]


@pytest.mark.asyncio
async def test_event_while_waiting_model_ack_is_consumed_by_same_turn():
    service = CoordinatorService()
    armed = await service.arm_resilient("A", channel_id="route-g2", retry_delays_seconds=(0, 0))
    claim = await service.claim("route-g2")
    await service.ack("route-g2", claim["claim_id"])
    queued = await service.arm_resilient("B", channel_id="route-g2", retry_delays_seconds=(0, 0))
    assert queued["continuation_id"] == armed["continuation_id"]
    assert queued["queued_events"] == 1
    acked = await service.model_ack(armed["continuation_id"] )
    assert acked["batched_messages"] == ["B"]
    assert (await service.status("route-g2"))["state"] == "idle"


@pytest.mark.asyncio
async def test_event_after_model_ack_becomes_one_followup_continuation():
    service = CoordinatorService()
    armed = await service.arm_resilient("A", channel_id="route-g2", retry_delays_seconds=(0, 0))
    claim = await service.claim("route-g2")
    acked = await service.model_ack(armed["continuation_id"] )
    assert acked["batched_count"] == 0
    queued = await service.arm_resilient("B", channel_id="route-g2", retry_delays_seconds=(0, 0))
    assert queued["queued_events"] == 1
    transport = await service.ack("route-g2", claim["claim_id"])
    assert transport["followup_pending"] is True
    assert transport["next_continuation_id"] != armed["continuation_id"]
    throttled = await service.claim("route-g2")
    assert throttled["claimed"] is False
    assert (await service.status("route-g2"))["state"] == "web_cooldown"
    service._global_cooldown_until = 0
    service._cooldown_until["route-g2"] = 0
    service._pending["route-g2"].available_at = 0
    followup = await service.claim("route-g2")
    assert followup["message"] == "B"
    assert followup["continuation_id"] == transport["next_continuation_id"]


@pytest.mark.asyncio
async def test_queued_batch_survives_restart_until_model_ack(tmp_path):
    path = tmp_path / "coordinator-wakes.json"
    first = CoordinatorService(path)
    armed = await first.arm_resilient("A", channel_id="route-g2", retry_delays_seconds=(0, 0))
    claim = await first.claim("route-g2")
    await first.ack("route-g2", claim["claim_id"])
    await first.arm_resilient("B", channel_id="route-g2", retry_delays_seconds=(0, 0))
    second = CoordinatorService(path)
    acked = await second.model_ack(armed["continuation_id"] )
    assert acked["batched_messages"] == ["B"]
    assert (await second.status("route-g2"))["state"] == "idle"


@pytest.mark.asyncio
async def test_eight_concurrent_events_keep_one_active_continuation():
    service = CoordinatorService()
    results = await asyncio.gather(*(service.arm_resilient(f"job-{index}", channel_id="route-g2") for index in range(8)))
    assert len({item["continuation_id"] for item in results}) == 1
    claim = await service.claim("route-g2")
    assert claim["batch_size"] == 8
    assert set(claim["message"].split(service.BATCH_SEPARATOR)) == {f"job-{index}" for index in range(8)}


@pytest.mark.asyncio
async def test_resilient_debounce_extends_quiet_window_but_is_bounded(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    service = CoordinatorService()
    service.MAX_BATCH_DEBOUNCE_WINDOW_SECONDS = 15.0
    first = await service.arm_resilient("A", channel_id="route-g2", delay_seconds=5)
    assert first["delay_seconds"] == 5
    assert service._pending["route-g2"].available_at == 1005.0
    clock[0] = 1004.0
    await service.arm_resilient("B", channel_id="route-g2", delay_seconds=5)
    assert service._pending["route-g2"].available_at == 1009.0
    clock[0] = 1014.0
    await service.arm_resilient("C", channel_id="route-g2", delay_seconds=5)
    assert service._pending["route-g2"].available_at == 1015.0


@pytest.mark.asyncio
async def test_transport_ack_persists_web_turn_cooldown(tmp_path, monkeypatch):
    clock = [2000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    path = tmp_path / "coordinator-wakes.json"
    service = CoordinatorService(path)
    service.MIN_WEB_TURN_INTERVAL_SECONDS = 20.0
    armed = await service.arm_resilient("A", channel_id="route-g2", retry_delays_seconds=(0, 0))
    claim = await service.claim("route-g2")
    transport = await service.ack("route-g2", claim["claim_id"])
    assert transport["web_turn_cooldown_seconds"] == 20.0
    await service.model_ack(armed["continuation_id"])
    followup = await service.arm_resilient("B", channel_id="route-g2", delay_seconds=0)
    assert followup["delay_seconds"] == 0
    assert service._pending["route-g2"].available_at == 2020.0
    restored = CoordinatorService(path)
    assert restored._cooldown_until["route-g2"] == 2020.0
    assert restored._global_cooldown_until == 2020.0
    assert (await restored.status("route-g2"))["ready"] is False


@pytest.mark.asyncio
async def test_external_web_backoff_suppresses_claim_until_expiry(tmp_path, monkeypatch):
    clock = [3000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    path = tmp_path / "coordinator-wakes.json"
    service = CoordinatorService(path)
    await service.arm_resilient("A", channel_id="route-g2", delay_seconds=0)
    (tmp_path / "web-backoff.json").write_text('{"until":3060}', encoding="utf-8")
    status = await service.status("route-g2")
    assert status["state"] == "web_backoff"
    assert status["ready"] is False
    assert status["web_backoff_seconds"] == 60.0
    assert (await service.claim("route-g2"))["claimed"] is False
    clock[0] = 3061.0
    assert (await service.claim("route-g2"))["claimed"] is True


@pytest.mark.asyncio
async def test_web_turn_gate_serializes_channels_and_applies_global_cooldown(monkeypatch):
    clock = [4000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    service = CoordinatorService()
    service.MIN_WEB_TURN_INTERVAL_SECONDS = 20.0
    await service.arm_resilient("A", channel_id="route-a", delay_seconds=0, retry_delays_seconds=(0, 0))
    await service.arm_resilient("B", channel_id="route-b", delay_seconds=0, retry_delays_seconds=(0, 0))
    claim_a = await service.claim("route-a")
    assert claim_a["claimed"] is True
    assert (await service.claim("route-b"))["claimed"] is False
    await service.ack("route-a", claim_a["claim_id"])
    status_b = await service.status("route-b")
    assert status_b["state"] == "web_cooldown"
    assert status_b["web_turn_cooldown_seconds"] == 20.0
    clock[0] = 4021.0
    assert (await service.claim("route-b"))["claimed"] is True


@pytest.mark.asyncio
async def test_observed_model_turn_resolves_delivered_continuation():
    service = CoordinatorService()
    armed = await service.arm_resilient(
        "resume", channel_id="route-g2", retry_delays_seconds=(0, 0)
    )
    claim = await service.claim("route-g2")
    await service.ack("route-g2", claim["claim_id"])
    status = await service.status("route-g2")
    assert status["transport_delivered_at"] is not None
    observed = await service.observe_model_turn("route-g2", armed["continuation_id"])
    assert observed["observed"] is True
    assert observed["delivery_attempts"] == 1
    assert observed["followup_pending"] is False
    assert (await service.status("route-g2"))["state"] == "idle"


@pytest.mark.asyncio
async def test_observed_model_turn_promotes_queued_event_to_followup():
    service = CoordinatorService()
    service.MIN_WEB_TURN_INTERVAL_SECONDS = 0
    armed = await service.arm_resilient(
        "A", channel_id="route-g2", retry_delays_seconds=(0, 0)
    )
    claim = await service.claim("route-g2")
    await service.ack("route-g2", claim["claim_id"])
    queued = await service.arm_resilient(
        "B", channel_id="route-g2", retry_delays_seconds=(0, 0)
    )
    assert queued["queued_events"] == 1
    observed = await service.observe_model_turn("route-g2", armed["continuation_id"])
    assert observed["observed"] is True
    assert observed["queued_events"] == 1
    assert observed["followup_pending"] is True
    assert observed["next_continuation_id"] != armed["continuation_id"]
    service._pending["route-g2"].available_at = 0
    followup = await service.claim("route-g2")
    assert followup["message"] == "B"


@pytest.mark.asyncio
async def test_observed_model_turn_requires_matching_delivered_continuation():
    service = CoordinatorService()
    armed = await service.arm_resilient("A", channel_id="route-g2")
    assert (await service.observe_model_turn("route-g2", armed["continuation_id"]))["observed"] is False


@pytest.mark.asyncio
async def test_browser_preflight_gate_blocks_resilient_claim_until_authorized():
    service = CoordinatorService(browser_preflight_required=True)
    armed = await service.arm_resilient(
        "resume", channel_id="route-g9", delay_seconds=0, retry_delays_seconds=(0, 0)
    )
    status = await service.status("route-g9")
    assert status["state"] == "browser_preflight"
    assert status["ready"] is False
    assert status["browser_preflight_required"] is True
    assert status["browser_preflight_authorized"] is False
    assert (await service.claim("route-g9"))["claimed"] is False
    authorized = await service.authorize_browser_preflight(
        "route-g9", armed["continuation_id"]
    )
    assert authorized["authorized"] is True
    assert (await service.status("route-g9"))["ready"] is True
    claim = await service.claim("route-g9")
    assert claim["claimed"] is True
    assert (await service.status("route-g9"))["state"] == "claimed"


@pytest.mark.asyncio
async def test_browser_preflight_authorization_is_one_shot_and_expires(monkeypatch):
    clock = [5000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    service = CoordinatorService(browser_preflight_required=True)
    service.LEASE_SECONDS = 0
    service.BROWSER_PREFLIGHT_TTL_SECONDS = 10
    armed = await service.arm_resilient(
        "resume", channel_id="route-g9", delay_seconds=0, retry_delays_seconds=(0, 0)
    )
    await service.authorize_browser_preflight("route-g9", armed["continuation_id"] )
    clock[0] = 5011.0
    assert (await service.claim("route-g9"))["claimed"] is False
    assert (await service.status("route-g9"))["state"] == "browser_preflight"
    await service.authorize_browser_preflight("route-g9", armed["continuation_id"] )
    claim = await service.claim("route-g9")
    assert claim["claimed"] is True
    assert service._pending["route-g9"].browser_preflight_authorized_at is None


@pytest.mark.asyncio
async def test_undelivered_resilient_wake_escalates_after_max_age(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    service = CoordinatorService(browser_preflight_required=True)
    service.MAX_UNDELIVERED_AGE_SECONDS = 30.0
    armed = await service.arm_resilient(
        "jobs=job_deadbeef; reason=all_terminal",
        channel_id="route-g9",
        delay_seconds=0,
        escalation_message="generic fallback",
    )
    assert await service.escalations_due() == []
    clock[0] = 1031.0
    due = await service.escalations_due()
    assert len(due) == 1
    assert due[0]["continuation_id"] == armed["continuation_id"]
    assert due[0]["delivery_attempts"] == 0
    assert due[0]["reason"] == "undelivered_timeout"
    assert "expired before X delivery" in due[0]["escalation_message"]


@pytest.mark.asyncio
async def test_expired_undelivered_wake_cannot_reenter_browser_delivery(monkeypatch):
    clock = [2000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    service = CoordinatorService(browser_preflight_required=True)
    service.MAX_UNDELIVERED_AGE_SECONDS = 30.0
    armed = await service.arm_resilient(
        "jobs=job_stale; reason=all_terminal",
        channel_id="route-g10",
        delay_seconds=0,
    )
    clock[0] = 2031.0
    status = await service.status("route-g10")
    assert status["state"] == "escalation_due"
    assert status["ready"] is False
    assert status["retry_after_seconds"] == 0.0
    authorized = await service.authorize_browser_preflight("route-g10", armed["continuation_id"] )
    assert authorized["authorized"] is False
    assert (await service.claim("route-g10"))["claimed"] is False
    due = await service.escalations_due()
    assert due[0]["reason"] == "undelivered_timeout"
