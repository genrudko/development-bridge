from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from telethon import TelegramClient, events
from telethon.errors import RPCError

from app.api.errors import BridgeError, ErrorCode
from app.coordinator import CoordinatorService
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
    ) -> None:
        self.enabled = enabled
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_path = session_path
        self.chat_id = chat_id
        self.channel_id = CoordinatorService.validate_channel(channel_id)
        self.coordinator = coordinator
        self._client = None
        self._lock = asyncio.Lock()
        self._connected = False
        self._chat_title = None
        self._last_inbound_message_id = None
        self._last_inbound_at = None
        self._last_error = None

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

    async def stop(self) -> None:
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
            "coordinator": await self.coordinator.status(self.channel_id),
        }

    async def _on_message(self, event) -> None:
        text = str(getattr(event, "raw_text", "") or "").strip()
        if not text or text.startswith((self.BRIDGE_PREFIX, self.CHATGPT_PREFIX)):
            return
        message_id = int(event.message.id)
        self._last_inbound_message_id = message_id
        self._last_inbound_at = datetime.now(UTC).isoformat()
        try:
            await self.coordinator.arm(
                f"[Telegram supervisor | message_id={message_id}]\n{text}",
                channel_id=self.channel_id,
                delay_seconds=0,
                conflict="reject",
            )
        except BridgeError as error:
            self._last_error = error.message
            await self._notice(
                "предыдущая команда ещё не забрана ChatGPT; это сообщение не передано."
            )
            return
        self._last_error = None
        await self._notice("команда передана в ChatGPT.")

    async def _notice(self, text: str) -> None:
        if self._client is None or self.chat_id is None:
            return
        try:
            async with self._lock:
                await self._client.send_message(
                    self.chat_id, f"{self.BRIDGE_PREFIX} {text}"
                )
        except (RPCError, OSError, TimeoutError) as error:
            self._last_error = f"Telegram notice failed: {type(error).__name__}"
