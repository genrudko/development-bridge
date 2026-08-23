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
