from __future__ import annotations

import pytest

from app.coordinator import CoordinatorService, RouteRegistry
from app.telegram_supervisor import TelegramSupervisorService


@pytest.mark.asyncio
async def test_telegram_supervisor_resolves_due_escalation_after_notice(tmp_path):
    coordinator = CoordinatorService(tmp_path / "wakes.json")
    registry = RouteRegistry(tmp_path / "routes.json")
    supervisor = TelegramSupervisorService(
        enabled=False,
        api_id=None,
        api_hash=None,
        session_path=None,
        chat_id=None,
        channel_id="telegram-supervisor",
        coordinator=coordinator,
        route_registry=registry,
    )
    notices = []

    async def notice(text: str) -> bool:
        notices.append(text)
        return True

    supervisor._notice = notice
    armed = await coordinator.arm_resilient(
        "resume",
        channel_id="route-g2",
        retry_delays_seconds=(0, 0),
        escalation_delay_seconds=0,
        escalation_message="final fallback",
    )
    claim = await coordinator.claim("route-g2")
    transport = await coordinator.ack("route-g2", claim["claim_id"])
    assert transport["transport_delivered"] is True

    await supervisor._drain_escalations_once()

    assert notices == ["final fallback"]
    assert (await coordinator.model_ack(armed["continuation_id"]))["acknowledged"] is False
    assert (await coordinator.status("route-g2"))["state"] == "idle"
