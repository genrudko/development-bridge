from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.coordinator import RouteRegistry
from app.telegram_supervisor import TelegramSupervisorService, prepare_supervisor_session


class FakeCoordinator:
    def __init__(self):
        self.armed = []

    async def arm(self, message, **kwargs):
        self.armed.append((message, kwargs))


class FakeClient:
    def __init__(self):
        self.calls = []

    async def send_message(self, chat_id, text, **kwargs):
        self.calls.append((chat_id, text, kwargs))
        return SimpleNamespace(id=123)


def make_supervisor(tmp_path: Path, *, topic_id: int | None = 56):
    return TelegramSupervisorService(
        enabled=False,
        api_id=None,
        api_hash=None,
        session_path=None,
        chat_id=-1004377708839,
        topic_id=topic_id,
        channel_id="telegram-supervisor",
        coordinator=FakeCoordinator(),
        route_registry=RouteRegistry(tmp_path / "routes.json"),
    )


def forum_event(text: str, message_id: int, topic_id: int | None):
    reply_to = (
        None
        if topic_id is None
        else SimpleNamespace(
            forum_topic=True, reply_to_top_id=None, reply_to_msg_id=topic_id
        )
    )
    return SimpleNamespace(
        raw_text=text,
        message=SimpleNamespace(id=message_id, reply_to=reply_to),
    )


def test_message_topic_id_uses_forum_root_reply():
    message = forum_event("test", 57, 56).message
    assert TelegramSupervisorService._message_topic_id(message) == 56
    assert TelegramSupervisorService._message_topic_id(
        forum_event("general", 58, None).message
    ) is None


@pytest.mark.asyncio
async def test_supervisor_ignores_messages_outside_configured_topic(tmp_path):
    supervisor = make_supervisor(tmp_path)
    await supervisor._on_message(forum_event("outside", 100, 77))
    await supervisor._on_message(forum_event("general", 101, None))
    assert supervisor.coordinator.armed == []
    assert supervisor._last_inbound_message_id is None


@pytest.mark.asyncio
async def test_supervisor_arms_only_configured_topic(tmp_path):
    supervisor = make_supervisor(tmp_path)
    notices = []

    async def notice(text):
        notices.append(text)
        return True

    supervisor._notice = notice
    await supervisor._on_message(forum_event("hello bridge", 102, 56))
    assert len(supervisor.coordinator.armed) == 1
    message, kwargs = supervisor.coordinator.armed[0]
    assert "message_id=102" in message
    assert message.endswith("hello bridge")
    assert kwargs["channel_id"] == "telegram-supervisor"
    assert notices == ["команда передана в ChatGPT."]


@pytest.mark.asyncio
async def test_supervisor_rejects_unbound_default_route(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-current",
        "telegram-bridge-g0",
    )
    supervisor.route_registry.unbind("bridge", expected_generation=0)
    notices = []

    async def notice(text):
        notices.append(text)
        return True

    supervisor._notice = notice
    await supervisor._on_message(forum_event("must not wake", 103, 56))

    assert supervisor.coordinator.armed == []
    assert notices == ["предыдущая команда ещё не забрана ChatGPT; это сообщение не передано."]


@pytest.mark.asyncio
async def test_supervisor_arms_bound_route_under_route_lock(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-current",
        "telegram-bridge-g0",
    )
    route_lock = supervisor.route_registry.route_lock("bridge")
    lock_observations = []

    async def observe_lock(_message, **_kwargs):
        lock_observations.append(route_lock.locked())

    async def notice(_text):
        return True

    supervisor.coordinator.arm = observe_lock
    supervisor._notice = notice
    await supervisor._on_message(forum_event("current wake", 104, 56))

    assert lock_observations == [True]


@pytest.mark.asyncio
async def test_supervisor_rejects_route_generation_change_before_arm(tmp_path):
    supervisor = make_supervisor(tmp_path)
    supervisor.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-current",
        "telegram-bridge-g0",
    )
    route_lock = supervisor.route_registry.route_lock("bridge")
    first_resolve = asyncio.Event()
    original_resolve = supervisor.route_registry.resolve

    def observe_resolve(route_id=None):
        route = original_resolve(route_id)
        if route is not None and route["route_id"] == "bridge":
            first_resolve.set()
        return route

    supervisor.route_registry.resolve = observe_resolve

    async def notice(_text):
        return True

    supervisor._notice = notice
    async with route_lock:
        wake_task = asyncio.create_task(
            supervisor._on_message(forum_event("stale wake", 105, 56))
        )
        await first_resolve.wait()
        supervisor.route_registry.takeover(
            "bridge", "https://chatgpt.com/g/g-p-infra/c/conv-successor"
        )

    await wake_task
    assert supervisor.coordinator.armed == []


@pytest.mark.asyncio
async def test_supervisor_replies_to_configured_topic(tmp_path):
    supervisor = make_supervisor(tmp_path)
    client = FakeClient()
    supervisor._client = client
    assert await supervisor._notice("ok") is True
    assert client.calls == [
        (-1004377708839, "⚡ Bridge: ok", {"reply_to": 56})
    ]


def test_supervisor_session_isolated_copy(tmp_path):
    source = tmp_path / "telegram.session"
    source.write_bytes(b"authorized-session")
    source.chmod(0o600)

    isolated = prepare_supervisor_session(source)

    assert isolated != source
    assert isolated.name == "telegram.supervisor.session"
    assert isolated.read_bytes() == source.read_bytes()
    assert isolated.stat().st_mode & 0o777 == 0o600
