from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from telethon import TelegramClient, utils
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    RPCError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl import types


USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")


class TelegramAuthorizationRequired(Exception):
    pass


class TelegramSourceNotFound(Exception):
    pass


class TelegramFloodWait(Exception):
    def __init__(self, seconds: int) -> None:
        super().__init__(f"Telegram requested a {seconds} second wait")
        self.seconds = seconds


class TelegramRequestFailed(Exception):
    pass


class TelegramAttachmentTooLarge(Exception):
    def __init__(self, actual_size: int, limit: int) -> None:
        super().__init__("Telegram attachment exceeds the download size limit")
        self.actual_size = actual_size
        self.limit = limit


@dataclass(frozen=True, slots=True)
class TelegramSource:
    entity_id: str
    username: str
    title: str
    kind: str
    canonical_url: str


@dataclass(frozen=True, slots=True)
class TelegramAttachment:
    attachment_type: str
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class TelegramMessage:
    message_id: int
    timestamp: datetime
    edited_timestamp: datetime | None
    author_id: str | None
    author_name: str | None
    text: str
    message_type: str = "message"
    reply_to_message_id: int | None = None
    topic: dict[str, object] | None = None
    permalink: str | None = None
    attachments: tuple[TelegramAttachment, ...] = ()


class TelegramAdapter(Protocol):
    async def resolve(self, canonical_url: str) -> TelegramSource: ...

    async def fetch_messages(
        self,
        source: TelegramSource,
        *,
        limit: int,
        before_id: int | None = None,
        after_id: int | None = None,
    ) -> tuple[TelegramMessage, ...]:
        """Fetch history newest-first, or incremental messages oldest-first."""
        ...

    async def download_attachment(
        self,
        source: TelegramSource,
        *,
        message_id: int,
        attachment_id: str,
        expected_metadata: dict[str, object],
        destination: Path,
        max_bytes: int,
    ) -> None: ...


def ensure_session_file(session_path: Path) -> Path:
    actual_path = (
        session_path
        if str(session_path).endswith(".session")
        else Path(str(session_path) + ".session")
    )
    actual_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(actual_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        os.chmod(actual_path, 0o600)
    else:
        os.close(descriptor)
    return actual_path


def canonicalize_public_url(value: str) -> tuple[str, str]:
    candidate = value.strip()
    if candidate.startswith("@"):
        username = candidate[1:]
    else:
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {
            "t.me", "www.t.me", "telegram.me", "www.telegram.me"
        }:
            raise ValueError("Only public t.me links or @username are supported")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 1 or parsed.query or parsed.fragment:
            raise ValueError("Only public Telegram username links are supported")
        username = parts[0]
    if username.startswith("+") or username.lower() in {"joinchat", "c", "s"}:
        raise ValueError("Private invite and internal Telegram links are not supported")
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("Invalid public Telegram username")
    normalized = username.lower()
    return f"https://t.me/{normalized}", normalized


class TelethonTelegramAdapter:
    def __init__(self, api_id: int, api_hash: str, session_path: Path) -> None:
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_path = session_path
        self._lock = asyncio.Lock()

    def _client(self) -> TelegramClient:
        ensure_session_file(self.session_path)
        return TelegramClient(
            str(self.session_path), self.api_id, self.api_hash,
            flood_sleep_threshold=0,
        )

    async def resolve(self, canonical_url: str) -> TelegramSource:
        async with self._lock:
            client = self._client()
            try:
                await client.connect()
                await self._require_authorized(client)
                entity = await client.get_entity(canonical_url)
                username = getattr(entity, "username", None)
                if not username or not isinstance(entity, types.Channel):
                    raise TelegramSourceNotFound("Telegram entity is not a public group or channel")
                kind = "group" if entity.megagroup else "channel"
                return TelegramSource(
                    entity_id=str(entity.id), username=username.lower(),
                    title=str(entity.title), kind=kind,
                    canonical_url=f"https://t.me/{username.lower()}",
                )
            except (UsernameInvalidError, UsernameNotOccupiedError, ChannelPrivateError) as error:
                raise TelegramSourceNotFound("Public Telegram source was not found or is inaccessible") from error
            except FloodWaitError as error:
                raise TelegramFloodWait(int(error.seconds)) from error
            except TelegramAuthorizationRequired:
                raise
            except TelegramSourceNotFound:
                raise
            except (RPCError, OSError, asyncio.TimeoutError) as error:
                raise TelegramRequestFailed("Telegram request failed") from error
            finally:
                await client.disconnect()

    async def fetch_messages(
        self,
        source: TelegramSource,
        *,
        limit: int,
        before_id: int | None = None,
        after_id: int | None = None,
    ) -> tuple[TelegramMessage, ...]:
        async with self._lock:
            client = self._client()
            try:
                await client.connect()
                await self._require_authorized(client)
                entity = await client.get_entity(source.canonical_url)
                messages = []
                async for message in client.iter_messages(
                    entity,
                    limit=limit,
                    max_id=before_id or 0,
                    min_id=after_id or 0,
                    reverse=after_id is not None,
                ):
                    messages.append(self._normalize_message(message, source))
                return tuple(messages)
            except (UsernameInvalidError, UsernameNotOccupiedError, ChannelPrivateError) as error:
                raise TelegramSourceNotFound("Public Telegram source was not found or is inaccessible") from error
            except FloodWaitError as error:
                raise TelegramFloodWait(int(error.seconds)) from error
            except TelegramAuthorizationRequired:
                raise
            except (RPCError, OSError, asyncio.TimeoutError) as error:
                raise TelegramRequestFailed("Telegram request failed") from error
            finally:
                await client.disconnect()

    async def download_attachment(
        self,
        source: TelegramSource,
        *,
        message_id: int,
        attachment_id: str,
        expected_metadata: dict[str, object],
        destination: Path,
        max_bytes: int,
    ) -> None:
        from .attachment_identity import stable_attachment_id

        async with self._lock:
            client = self._client()
            try:
                await client.connect()
                await self._require_authorized(client)
                entity = await client.get_entity(source.canonical_url)
                message = await client.get_messages(entity, ids=message_id)
                if message is None:
                    raise TelegramSourceNotFound("Telegram message is not available")
                normalized = self._normalize_message(message, source)
                matched = None
                for index, attachment in enumerate(normalized.attachments):
                    candidate = stable_attachment_id(
                        attachment.attachment_type,
                        attachment.metadata,
                        fallback_index=index,
                    )
                    if candidate == attachment_id:
                        matched = attachment
                        break
                if matched is None or (
                    expected_metadata.get("telegram_media_id")
                    != matched.metadata.get("telegram_media_id")
                ):
                    raise TelegramSourceNotFound("Telegram attachment identity changed")
                written = 0
                download = client.iter_download(message.media)
                try:
                    with destination.open("wb") as stream:
                        async for chunk in download:
                            chunk = bytes(chunk)
                            remaining = max_bytes - written
                            if len(chunk) > remaining:
                                if remaining:
                                    stream.write(chunk[:remaining])
                                    written += remaining
                                raise TelegramAttachmentTooLarge(
                                    written + len(chunk) - remaining, max_bytes
                                )
                            stream.write(chunk)
                            written += len(chunk)
                finally:
                    await download.close()
            except (UsernameInvalidError, UsernameNotOccupiedError, ChannelPrivateError, ValueError) as error:
                raise TelegramSourceNotFound("Telegram source or attachment is inaccessible") from error
            except FloodWaitError as error:
                raise TelegramFloodWait(int(error.seconds)) from error
            except (
                TelegramAuthorizationRequired, TelegramSourceNotFound,
                TelegramRequestFailed, TelegramAttachmentTooLarge,
            ):
                raise
            except (RPCError, OSError, asyncio.TimeoutError) as error:
                raise TelegramRequestFailed("Telegram request failed") from error
            finally:
                await client.disconnect()

    @staticmethod
    async def _require_authorized(client: TelegramClient) -> None:
        if not await client.is_user_authorized():
            raise TelegramAuthorizationRequired("Telegram session is not authorized")

    @staticmethod
    def _normalize_message(message, source: TelegramSource) -> TelegramMessage:
        sender = getattr(message, "sender", None)
        author_id = getattr(message, "sender_id", None)
        author_name = utils.get_display_name(sender) if sender is not None else None
        reply = getattr(message, "reply_to", None)
        topic = None
        if reply is not None:
            topic_values = {
                "reply_to_top_id": getattr(reply, "reply_to_top_id", None),
                "forum_topic": getattr(reply, "forum_topic", None),
            }
            topic = {key: value for key, value in topic_values.items() if value is not None} or None
        attachments: list[TelegramAttachment] = []
        photo = getattr(message, "photo", None)
        if photo is not None:
            metadata: dict[str, object] = {"telegram_media_id": str(photo.id)}
            sizes = getattr(photo, "sizes", ())
            if sizes:
                largest = max(
                    sizes,
                    key=lambda size: int(getattr(size, "w", 0)) * int(getattr(size, "h", 0)),
                )
                for name in ("w", "h", "size"):
                    value = getattr(largest, name, None)
                    if value is not None:
                        metadata[name] = value
            attachments.append(TelegramAttachment("photo", metadata))
        document = getattr(message, "document", None)
        if document is not None:
            metadata: dict[str, object] = {
                "telegram_media_id": str(document.id), "size": document.size,
                "mime_type": document.mime_type,
            }
            for attribute in document.attributes:
                for name in ("file_name", "w", "h", "duration"):
                    value = getattr(attribute, name, None)
                    if value is not None:
                        metadata[name] = value
            attachment_type = (
                "video" if str(document.mime_type or "").startswith("video/") else "document"
            )
            attachments.append(TelegramAttachment(attachment_type, metadata))
        return TelegramMessage(
            message_id=int(message.id), timestamp=message.date,
            edited_timestamp=getattr(message, "edit_date", None),
            author_id=str(author_id) if author_id is not None else None,
            author_name=author_name,
            text=str(getattr(message, "message", None) or ""),
            message_type="service" if getattr(message, "action", None) is not None else "message",
            reply_to_message_id=getattr(message, "reply_to_msg_id", None),
            topic=topic,
            permalink=f"{source.canonical_url}/{message.id}",
            attachments=tuple(attachments),
        )
