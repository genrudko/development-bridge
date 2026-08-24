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
async def test_resilient_continuation_retries_until_model_ack():
    service = CoordinatorService()
    armed = await service.arm_resilient(
        "resume",
        channel_id="route-g2",
        retry_delays_seconds=(0, 0),
        escalation_delay_seconds=0,
        escalation_message="escalate",
    )
    continuation_id = armed["continuation_id"]

    first = await service.claim("route-g2")
    assert first["delivery_attempt"] == 1
    assert first["continuation_id"] == continuation_id
    await service.ack("route-g2", first["claim_id"])

    second = await service.claim("route-g2")
    assert second["delivery_attempt"] == 2
    await service.ack("route-g2", second["claim_id"])

    acked = await service.model_ack(continuation_id)
    assert acked["acknowledged"] is True
    assert (await service.status("route-g2"))["state"] == "idle"
    assert await service.escalations_due() == []


@pytest.mark.asyncio
async def test_resilient_continuation_escalates_after_three_unacked_deliveries():
    service = CoordinatorService()
    armed = await service.arm_resilient(
        "resume",
        channel_id="route-g2",
        retry_delays_seconds=(0, 0),
        escalation_delay_seconds=0,
        escalation_message="telegram fallback",
    )
    for expected_attempt in (1, 2, 3):
        claim = await service.claim("route-g2")
        assert claim["delivery_attempt"] == expected_attempt
        await service.ack("route-g2", claim["claim_id"])

    due = await service.escalations_due()
    assert len(due) == 1
    assert due[0]["continuation_id"] == armed["continuation_id"]
    assert due[0]["delivery_attempts"] == 3
    assert due[0]["escalation_message"] == "telegram fallback"
    assert (await service.claim("route-g2"))["claimed"] is False


@pytest.mark.asyncio
async def test_resilient_retry_state_survives_restart(tmp_path):
    path = tmp_path / "coordinator-wakes.json"
    first_service = CoordinatorService(path)
    armed = await first_service.arm_resilient(
        "resume",
        channel_id="route-g2",
        retry_delays_seconds=(0, 0),
        escalation_delay_seconds=0,
    )
    first_claim = await first_service.claim("route-g2")
    await first_service.ack("route-g2", first_claim["claim_id"])

    second_service = CoordinatorService(path)
    second_claim = await second_service.claim("route-g2")
    assert second_claim["claimed"] is True
    assert second_claim["delivery_attempt"] == 2
    assert second_claim["continuation_id"] == armed["continuation_id"]


@pytest.mark.asyncio
async def test_model_ack_during_transport_claim_prevents_retry():
    service = CoordinatorService()
    armed = await service.arm_resilient("resume", channel_id="route-g2", retry_delays_seconds=(0, 0), escalation_delay_seconds=0)
    claim = await service.claim("route-g2")
    acked = await service.model_ack_channel("route-g2")
    assert acked["continuation_id"] == armed["continuation_id"]
    transport = await service.ack("route-g2", claim["claim_id"])
    assert transport["acknowledged"] is True
    assert (await service.status("route-g2"))["state"] == "idle"
    assert (await service.claim("route-g2"))["claimed"] is False
