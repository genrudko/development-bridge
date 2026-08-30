from __future__ import annotations

import pytest

from app.coordinator.service import CoordinatorService


@pytest.mark.asyncio
async def test_delivery_lease_rejects_explicit_stale_owner_but_allows_legacy_widget(tmp_path):
    service = CoordinatorService(tmp_path / "wakes.json")
    service.MIN_WEB_TURN_INTERVAL_SECONDS = 0
    first = service.issue_delivery_lease("route-g1", session_id="session-a", route_id="route", generation=1)
    same = service.issue_delivery_lease("route-g1", session_id="session-a", route_id="route", generation=1)
    assert same["lease_id"] == first["lease_id"]

    await service.arm("wake-one", channel_id="route-g1", delay_seconds=0)
    visible = await service.status("route-g1")
    assert visible["state"] == "pending"
    claim = await service.claim("route-g1")
    assert claim["claimed"] is True
    assert (await service.ack("route-g1", claim["claim_id"], delivery_lease="wrong"))["acknowledged"] is False
    assert (await service.ack("route-g1", claim["claim_id"]))["acknowledged"] is True

    second = service.issue_delivery_lease("route-g1", session_id="session-b", route_id="route", generation=1)
    assert second["lease_id"] != first["lease_id"]
    await service.arm("wake-two", channel_id="route-g1", delay_seconds=0)
    assert (await service.claim("route-g1", delivery_lease=first["lease_id"]))["claimed"] is False
    assert (await service.claim("route-g1", delivery_lease=second["lease_id"]))["claimed"] is True


def test_delivery_lease_survives_bridge_restart(tmp_path):
    state = tmp_path / "wakes.json"
    first = CoordinatorService(state)
    lease = first.issue_delivery_lease("route-g2", session_id="session-a", route_id="route", generation=2)
    second = CoordinatorService(state)
    restored = second.delivery_lease("route-g2")
    assert restored is not None
    assert restored["lease_id"] == lease["lease_id"]
    assert restored["generation"] == 2
