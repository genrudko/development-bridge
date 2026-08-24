from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from telethon import TelegramClient, events
from telethon.errors import RPCError

from app.api.errors import BridgeError, ErrorCode
from app.coordinator import CoordinatorService, RouteRegistry
from app.knowledge.telegram import ensure_session_file


class TelegramSupervisorService:
    BRIDGE_PREFIX = "⚡ Bridge:"
    CHATGPT_PREFIX = "🤖 ChatGPT:"

    def __init__(
        self,
        *,
        enabled: bool,
        api_id: int | None,
        api_hash: str | None,
        session_path: Path | None,
        chat_id: int | None,
        channel_id: str,
        coordinator: CoordinatorService,
        route_registry: RouteRegistry,
    ) -> None:
        self.enabled = enabled
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_path = session_path
        self.chat_id = chat_id
        self.channel_id = CoordinatorService.validate_channel(channel_id)
        self.coordinator = coordinator
        self.route_registry = route_registry
        self._client = None
        self._lock = asyncio.Lock()
        self._connected = False
        self._chat_title = None
        self._last_inbound_message_id = None
        self._last_inbound_at = None
        self._last_error = None
        self._escalation_task: asyncio.Task | None = None

    @property
    def configured(self) -> bool:
        return (
            self.enabled
            and self.api_id is not None
            and self.api_hash is not None
            and self.session_path is not None
            and self.chat_id is not None
        )

    async def start(self) -> None:
        if not self.enabled:
            return
        if not self.configured:
            raise BridgeError(
                ErrorCode.TELEGRAM_NOT_CONFIGURED,
                "Telegram supervisor configuration is incomplete",
            )
        ensure_session_file(self.session_path)
        client = TelegramClient(
            str(self.session_path), self.api_id, self.api_hash, flood_sleep_threshold=0
        )
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            raise BridgeError(
                ErrorCode.TELEGRAM_AUTHORIZATION_REQUIRED,
                "Telegram supervisor session is not authorized",
            )
        entity = await client.get_entity(self.chat_id)
        self._chat_title = str(getattr(entity, "title", self.chat_id))
        client.add_event_handler(
            self._on_message, events.NewMessage(chats=self.chat_id)
        )
        self._client = client
        self._connected = True
        self._last_error = None
        self._escalation_task = asyncio.create_task(self._escalation_loop())

    async def stop(self) -> None:
        task = self._escalation_task
        self._escalation_task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        client = self._client
        self._client = None
        self._connected = False
        if client is not None:
            await client.disconnect()

    def _require_client(self):
        if not self.configured:
            raise BridgeError(
                ErrorCode.TELEGRAM_NOT_CONFIGURED,
                "Telegram supervisor is not configured",
            )
        if not self._connected or self._client is None:
            raise BridgeError(
                ErrorCode.TELEGRAM_REQUEST_FAILED,
                "Telegram supervisor is not connected",
                retryable=True,
            )
        return self._client

    async def send(self, text: str) -> dict:
        text = str(text).strip()
        if not text:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT, "Telegram message cannot be empty"
            )
        if len(text) > 3500:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "Telegram message is limited to 3500 characters",
            )
        client = self._require_client()
        async with self._lock:
            message = await client.send_message(
                self.chat_id, f"{self.CHATGPT_PREFIX} {text}"
            )
        return {
            "chat_id": self.chat_id,
            "chat_title": self._chat_title,
            "message_id": int(message.id),
            "sent": True,
        }

    async def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "configured": self.configured,
            "connected": self._connected,
            "chat_id": self.chat_id,
            "chat_title": self._chat_title,
            "channel_id": self.channel_id,
            "last_inbound_message_id": self._last_inbound_message_id,
            "last_inbound_at": self._last_inbound_at,
            "last_error": self._last_error,
            "routes": self.route_registry.list_routes(),
            "coordinator": await self.coordinator.status((self.route_registry.resolve() or {}).get("channel_id", self.channel_id)),
        }

    async def _on_message(self, event) -> None:
        text = str(getattr(event, "raw_text", "") or "").strip()
        if not text or text.startswith((self.BRIDGE_PREFIX, self.CHATGPT_PREFIX)):
            return
        message_id = int(event.message.id)
        self._last_inbound_message_id = message_id
        self._last_inbound_at = datetime.now(UTC).isoformat()
        try:
            if text == "/chats":
                routes = self.route_registry.list_routes()
                if not routes:
                    await self._notice(f"маршруты ещё не зарегистрированы; используется legacy channel {self.channel_id}.")
                    return
                lines = ["маршруты:"]
                for route in routes:
                    marker = "*" if route.get("default") else " "
                    lines.append(f"{marker} {route['route_id']} -> {route.get('title') or route['conversation_id']} (g{route.get('generation', 0)})")
                discovered = self.route_registry.list_discovered_chats(limit=10)
                if discovered:
                    lines.append("\nнедавно обнаруженные чаты:")
                    for chat in discovered:
                        lines.append(f"- {chat.get('title') or chat.get('conversation_id')} [{chat.get('conversation_id')}]")
                await self._notice("\n".join(lines)); return
            if text.startswith("/to "):
                route = self.route_registry.select_default(text[4:].strip())
                await self._notice(f"маршрут переключён на {route['route_id']} -> {route.get('title') or route['conversation_id']}."); return
            route_id = None; body = text
            if text.startswith("@") and " " in text:
                candidate, body = text[1:].split(" ", 1); route_id = candidate.strip(); body = body.strip()
            route = self.route_registry.resolve(route_id); target_channel = route["channel_id"] if route else self.channel_id; route_label = route["route_id"] if route else "legacy"
            if route:
                self.route_registry.request(route["route_id"])
            await self.coordinator.arm(
                f"[Telegram supervisor | route={route_label} | message_id={message_id}]\n{body}",
                channel_id=target_channel, delay_seconds=0, conflict="reject",
            )
        except BridgeError as error:
            self._last_error = error.message
            await self._notice(
                "предыдущая команда ещё не забрана ChatGPT; это сообщение не передано."
            )
            return
        self._last_error = None
        await self._notice("команда передана в ChatGPT.")

    async def _escalation_loop(self) -> None:
        while True:
            await self._drain_escalations_once()
            await asyncio.sleep(5)

    async def _drain_escalations_once(self) -> None:
        for escalation in await self.coordinator.escalations_due():
            text = escalation.get("escalation_message") or (
                "⚠️ Coordinator continuation was not acknowledged after "
                f"{escalation['delivery_attempts']} X delivery attempts.\n"
                f"Channel: {escalation['channel_id']}\n"
                "Please check ChatGPT / Browser Host."
            )
            if await self._notice(text):
                await self.coordinator.resolve_escalation(escalation["continuation_id"])

    async def _notice(self, text: str) -> bool:
        if self._client is None or self.chat_id is None:
            return False
        try:
            async with self._lock:
                await self._client.send_message(
                    self.chat_id, f"{self.BRIDGE_PREFIX} {text}"
                )
            return True
        except (RPCError, OSError, TimeoutError) as error:
            self._last_error = f"Telegram notice failed: {type(error).__name__}"
            return False
