from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Any

from app.api.errors import BridgeError, ErrorCode

from .store import KnowledgeStore
from .attachment_identity import attachment_fields, stable_attachment_id
from .telegram import (
    TelegramAdapter,
    TelegramAuthorizationRequired,
    TelegramFloodWait,
    TelegramMessage,
    TelegramRequestFailed,
    TelegramSource,
    TelegramSourceNotFound,
    canonicalize_public_url,
)


class TelegramKnowledgeService:
    def __init__(
        self,
        store: KnowledgeStore,
        adapter: TelegramAdapter,
        *,
        default_batch_size: int = 2000,
        recent_window_size: int = 100,
    ) -> None:
        self.store = store
        self.adapter = adapter
        self.default_batch_size = default_batch_size
        self.recent_window_size = recent_window_size
        self._lock = asyncio.Lock()
        self.store.initialize()

    async def source_add(self, url: str) -> dict[str, Any]:
        try:
            canonical_url, _ = canonicalize_public_url(url)
        except ValueError as error:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        async with self._lock:
            source = await self._resolve(canonical_url)
            source_id = self._register_source(source)
            sync = await self._sync_locked(source_id, self.default_batch_size)
        return {
            "source_id": source_id,
            "platform": "telegram",
            "title": source.title,
            "url": source.canonical_url,
            "entity_id": source.entity_id,
            "username": source.username,
            "source_type": source.kind,
            "sync": sync,
        }

    async def source_sync(self, source_id: str, *, limit: int | None = None) -> dict[str, Any]:
        batch_size = self.default_batch_size if limit is None else limit
        if not 1 <= batch_size <= 5000:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "limit must be between 1 and 5000")
        async with self._lock:
            return await self._sync_locked(source_id, batch_size)

    async def _sync_locked(self, source_id: str, limit: int) -> dict[str, Any]:
        source, state = self._load_source(source_id)
        oldest = state["oldest_message_id"]
        newest = state["newest_message_id"]
        history_complete = bool(state["history_complete"])
        phase = "initial"
        try:
            if oldest is None:
                messages = await self.adapter.fetch_messages(source, limit=limit)
                history_complete = len(messages) < limit
            elif not history_complete:
                phase = "history"
                new_messages = await self.adapter.fetch_messages(
                    source, limit=limit, after_id=int(newest)
                )
                new_count = len(new_messages)
                remaining = limit - new_count
                history_messages = ()
                if remaining > 0:
                    history_messages = await self.adapter.fetch_messages(
                        source, limit=remaining, before_id=int(oldest)
                    )
                    history_complete = len(history_messages) < remaining
                messages = tuple(new_messages) + tuple(history_messages)
            else:
                phase = "incremental"
                new_messages = await self.adapter.fetch_messages(
                    source, limit=limit, after_id=int(newest)
                )
                new_count = len(new_messages)
                messages = new_messages
                if new_count < limit and self.recent_window_size > 0:
                    recent = await self.adapter.fetch_messages(
                        source, limit=min(limit, self.recent_window_size)
                    )
                    new_ids = {message.message_id for message in new_messages}
                    recent_only = [
                        message for message in recent
                        if message.message_id not in new_ids
                    ]
                    messages = tuple(new_messages) + tuple(
                        recent_only[: limit - new_count]
                    )
        except (
            TelegramAuthorizationRequired, TelegramSourceNotFound,
            TelegramFloodWait, TelegramRequestFailed,
        ) as error:
            raise self._bridge_error(error) from error

        inserted, updated = self._store_messages(
            source_id, source, tuple(messages), history_complete=history_complete
        )
        ids = [message.message_id for message in messages]
        oldest_result = min(([int(oldest)] if oldest is not None else []) + ids, default=None)
        newest_result = max(([int(newest)] if newest is not None else []) + ids, default=None)
        has_more = not history_complete
        if phase == "incremental":
            has_more = new_count >= limit
        return {
            "source_id": source_id,
            "fetched": len(messages),
            "inserted": inserted,
            "updated": updated,
            "phase": phase,
            "history_complete": history_complete,
            "has_more": has_more,
            "oldest_message_id": str(oldest_result) if oldest_result is not None else None,
            "newest_message_id": str(newest_result) if newest_result is not None else None,
        }

    async def _resolve(self, canonical_url: str) -> TelegramSource:
        try:
            return await self.adapter.resolve(canonical_url)
        except (
            TelegramAuthorizationRequired, TelegramSourceNotFound,
            TelegramFloodWait, TelegramRequestFailed,
        ) as error:
            raise self._bridge_error(error) from error

    def _register_source(self, source: TelegramSource) -> str:
        now = datetime.now(UTC).isoformat()
        with self.store.connect() as connection:
            existing = connection.execute(
                """SELECT s.source_id FROM source_sync_state x
                   JOIN sources s ON s.id=x.source_fk
                   WHERE x.provider='telegram' AND x.entity_id=?""",
                (source.entity_id,),
            ).fetchone()
            if existing is not None:
                source_id = existing["source_id"]
                connection.execute(
                    """UPDATE sources SET title=?, source_url=?, metadata_json=?
                       WHERE source_id=?""",
                    (source.title, source.canonical_url, self._source_metadata(source), source_id),
                )
                connection.execute(
                    """UPDATE source_sync_state SET username=?, source_kind=?
                       WHERE provider='telegram' AND entity_id=?""",
                    (source.username, source.kind, source.entity_id),
                )
                return source_id
            base = self.stable_source_id(source.username)
            source_id = base
            collision = connection.execute(
                "SELECT 1 FROM sources WHERE source_id=?", (source_id,)
            ).fetchone()
            if collision is not None:
                source_id = f"{base}-{re.sub(r'[^0-9a-z]+', '-', source.entity_id.lower()).strip('-')}"
            connection.execute(
                """INSERT INTO sources(
                       source_id, platform, title, source_url, imported_at, metadata_json)
                   VALUES (?, 'telegram', ?, ?, ?, ?)""",
                (source_id, source.title, source.canonical_url, now, self._source_metadata(source)),
            )
            source_fk = connection.execute(
                "SELECT id FROM sources WHERE source_id=?", (source_id,)
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO source_sync_state(
                       source_fk, provider, entity_id, username, source_kind)
                   VALUES (?, 'telegram', ?, ?, ?)""",
                (source_fk, source.entity_id, source.username, source.kind),
            )
        return source_id

    def _load_source(self, source_id: str) -> tuple[TelegramSource, Any]:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT s.source_url, s.title, x.* FROM sources s
                   JOIN source_sync_state x ON x.source_fk=s.id
                   WHERE s.source_id=? AND x.provider='telegram'""",
                (source_id,),
            ).fetchone()
        if row is None:
            raise BridgeError(
                ErrorCode.TELEGRAM_SOURCE_NOT_FOUND,
                "Telegram knowledge source is not registered",
            )
        return TelegramSource(
            entity_id=row["entity_id"], username=row["username"],
            title=row["title"], kind=row["source_kind"],
            canonical_url=row["source_url"],
        ), row

    def _store_messages(
        self,
        source_id: str,
        source: TelegramSource,
        messages: tuple[TelegramMessage, ...],
        *,
        history_complete: bool,
    ) -> tuple[int, int]:
        inserted = updated = 0
        now = datetime.now(UTC).isoformat()
        with self.store.connect() as connection:
            source_fk = connection.execute(
                "SELECT id FROM sources WHERE source_id=?", (source_id,)
            ).fetchone()[0]
            state = connection.execute(
                "SELECT oldest_message_id, newest_message_id FROM source_sync_state WHERE source_fk=?",
                (source_fk,),
            ).fetchone()
            ids = [message.message_id for message in messages]
            oldest = min(([state["oldest_message_id"]] if state["oldest_message_id"] is not None else []) + ids, default=None)
            newest = max(([state["newest_message_id"]] if state["newest_message_id"] is not None else []) + ids, default=None)
            for message in messages:
                author_fk = self._author(connection, source_fk, message)
                existed = connection.execute(
                    "SELECT id FROM messages WHERE source_fk=? AND platform_message_id=?",
                    (source_fk, str(message.message_id)),
                ).fetchone()
                connection.execute(
                    """INSERT INTO messages(
                         source_fk, platform_message_id, message_type, timestamp,
                         edited_timestamp, author_fk, text, original_text_json,
                         reply_to_message_id, topic_json, permalink, metadata_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(source_fk, platform_message_id) DO UPDATE SET
                         message_type=excluded.message_type, timestamp=excluded.timestamp,
                         edited_timestamp=excluded.edited_timestamp, author_fk=excluded.author_fk,
                         text=excluded.text, original_text_json=excluded.original_text_json,
                         reply_to_message_id=excluded.reply_to_message_id,
                         topic_json=excluded.topic_json, permalink=excluded.permalink,
                         metadata_json=excluded.metadata_json""",
                    (
                        source_fk, str(message.message_id), message.message_type,
                        self._timestamp(message.timestamp), self._timestamp(message.edited_timestamp),
                        author_fk, message.text, json.dumps(message.text, ensure_ascii=False),
                        str(message.reply_to_message_id) if message.reply_to_message_id is not None else None,
                        json.dumps(message.topic, ensure_ascii=False) if message.topic else None,
                        message.permalink,
                        json.dumps({"provider": "telethon", "entity_id": source.entity_id}),
                    ),
                )
                message_fk = connection.execute(
                    "SELECT id FROM messages WHERE source_fk=? AND platform_message_id=?",
                    (source_fk, str(message.message_id)),
                ).fetchone()[0]
                attachments = []
                for index, attachment in enumerate(message.attachments):
                    media_type, file_name, declared_size = attachment_fields(
                        attachment.attachment_type, attachment.metadata, None
                    )
                    attachments.append(
                        {
                            "attachment_id": stable_attachment_id(
                                attachment.attachment_type, attachment.metadata,
                                fallback_index=index,
                            ),
                            "type": attachment.attachment_type,
                            "exported_path": None,
                            "metadata": attachment.metadata,
                            "media_type": media_type,
                            "file_name": file_name,
                            "declared_size": declared_size,
                        }
                    )
                self.store.replace_attachments(connection, message_fk, attachments)
                inserted += existed is None
                updated += existed is not None
            connection.execute(
                """UPDATE sources SET imported_at=?, title=?, source_url=?, metadata_json=?
                   WHERE id=?""",
                (now, source.title, source.canonical_url, self._source_metadata(source), source_fk),
            )
            connection.execute(
                """UPDATE source_sync_state SET oldest_message_id=?, newest_message_id=?,
                       history_complete=?, last_sync_at=?, username=?, source_kind=?
                   WHERE source_fk=?""",
                (oldest, newest, int(history_complete), now, source.username, source.kind, source_fk),
            )
        return inserted, updated

    @staticmethod
    def stable_source_id(username: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", username.lower()).strip("-")
        return f"telegram-{slug}"

    @staticmethod
    def _author(connection, source_fk: int, message: TelegramMessage) -> int | None:
        if message.author_id is None and message.author_name is None:
            return None
        display_name = message.author_name or message.author_id or "Unknown"
        author_key = message.author_id or f"name:{display_name}"
        connection.execute(
            """INSERT INTO authors(source_fk, author_key, platform_author_id, display_name)
               VALUES (?, ?, ?, ?) ON CONFLICT(source_fk, author_key) DO UPDATE SET
               platform_author_id=excluded.platform_author_id,
               display_name=excluded.display_name""",
            (source_fk, author_key, message.author_id, display_name),
        )
        return connection.execute(
            "SELECT id FROM authors WHERE source_fk=? AND author_key=?",
            (source_fk, author_key),
        ).fetchone()[0]

    @staticmethod
    def _timestamp(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()

    @staticmethod
    def _source_metadata(source: TelegramSource) -> str:
        return json.dumps(
            {"entity_id": source.entity_id, "username": source.username, "source_type": source.kind},
            ensure_ascii=False,
        )

    @staticmethod
    def _bridge_error(error: Exception) -> BridgeError:
        if isinstance(error, TelegramAuthorizationRequired):
            return BridgeError(
                ErrorCode.TELEGRAM_AUTHORIZATION_REQUIRED,
                "Telegram session is not authorized; run the local authorization CLI",
            )
        if isinstance(error, TelegramSourceNotFound):
            return BridgeError(ErrorCode.TELEGRAM_SOURCE_NOT_FOUND, str(error))
        if isinstance(error, TelegramFloodWait):
            return BridgeError(
                ErrorCode.TELEGRAM_RATE_LIMITED,
                "Telegram rate limit requires a later retry",
                retryable=True,
                details={"retry_after_seconds": error.seconds},
            )
        return BridgeError(
            ErrorCode.TELEGRAM_REQUEST_FAILED,
            "Telegram request failed",
            retryable=True,
        )
