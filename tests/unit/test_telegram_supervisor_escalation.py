from __future__ import annotations

import pytest

from app.api.errors import BridgeError
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
        topic_id=None,
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



@pytest.mark.asyncio
async def test_telegram_supervisor_reports_successful_wake_delivery(tmp_path):
    coordinator = CoordinatorService(tmp_path / "wakes.json")
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/c/12345678-1234-1234-1234-123456789abc",
        "route-notify",
        "Bridge",
    )
    supervisor = TelegramSupervisorService(
        enabled=False,
        api_id=None,
        api_hash=None,
        session_path=None,
        chat_id=None,
        topic_id=None,
        channel_id="telegram-supervisor",
        coordinator=coordinator,
        route_registry=registry,
    )
    notices: list[str] = []

    async def notice(text: str) -> bool:
        notices.append(text)
        return True

    supervisor._notice = notice
    coordinator._delivery_notifier = getattr(supervisor, "notify_wake_delivered", None)
    await coordinator.arm_resilient(
        "resume",
        channel_id="route-notify",
        retry_delays_seconds=(0, 0),
    )
    claim = await coordinator.claim("route-notify")

    await coordinator.ack("route-notify", claim["claim_id"])

    assert notices == [
        "✅ Wake успешно доставлен: route=bridge, transport=X, attempt=1/3."
    ]


def test_container_wires_telegram_supervisor_as_delivery_notifier(tmp_path):
    from app.container import build_container
    from app.settings import BridgeSettings

    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": str(tmp_path / "routes.json")},
        "knowledge": {
            "telegram": {
                "api_id": 12345,
                "api_hash": "test-hash",
                "session_path": str(tmp_path / "telegram.session"),
            }
        },
        "telegram_supervisor": {
            "enabled": True,
            "chat_id": -1001234567890,
            "channel_id": "telegram-supervisor",
        },
    })

    container = build_container(settings)

    assert container.telegram_supervisor is not None
    notifier = getattr(container.coordinator, "_delivery_notifier", None)
    assert getattr(notifier, "__self__", None) is container.telegram_supervisor
    assert getattr(notifier, "__name__", None) == "notify_wake_delivered"



@pytest.mark.asyncio
async def test_success_notice_uses_safe_route_id_during_pending_rollover(tmp_path):
    coordinator = CoordinatorService(tmp_path / "wakes.json")
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/c/12345678-1234-1234-1234-123456789abc",
        "telegram-bridge-g0",
        "Bridge",
    )
    pending = registry.prepare_rollover("bridge")
    supervisor = TelegramSupervisorService(
        enabled=False,
        api_id=None,
        api_hash=None,
        session_path=None,
        chat_id=None,
        topic_id=None,
        channel_id="telegram-supervisor",
        coordinator=coordinator,
        route_registry=registry,
    )
    notices: list[str] = []

    async def notice(text: str) -> bool:
        notices.append(text)
        return True

    supervisor._notice = notice
    error = None
    try:
        await supervisor.notify_wake_delivered({
            "channel_id": pending["channel_id"],
            "transport": "x",
            "delivery_attempt": 1,
            "max_delivery_attempts": 3,
        })
    except BridgeError as exc:
        error = exc

    assert error is None
    assert notices == [
        "✅ Wake успешно доставлен: route=bridge, transport=X, attempt=1/3."
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unsafe_channel",
    [
        "telegram-bridge-g99",
        "123e4567-e89b-12d3-a456-426614174000",
    ],
)
async def test_success_notice_never_exposes_unresolved_channel_as_route_label(
    tmp_path, unsafe_channel
):
    coordinator = CoordinatorService(tmp_path / "wakes.json")
    registry = RouteRegistry(tmp_path / "routes.json")
    supervisor = TelegramSupervisorService(
        enabled=False,
        api_id=None,
        api_hash=None,
        session_path=None,
        chat_id=None,
        topic_id=None,
        channel_id="telegram-supervisor",
        coordinator=coordinator,
        route_registry=registry,
    )
    notices: list[str] = []

    async def notice(text: str) -> bool:
        notices.append(text)
        return True

    supervisor._notice = notice
    error = None
    try:
        await supervisor.notify_wake_delivered({
            "channel_id": unsafe_channel,
            "transport": "review-gpt",
            "delivery_attempt": 1,
            "max_delivery_attempts": 3,
        })
    except BridgeError as exc:
        error = exc

    assert error is None
    assert notices == [
        "✅ Wake успешно доставлен: route=legacy, transport=review-gpt, attempt=1/3."
    ]
    assert unsafe_channel not in notices[0]
