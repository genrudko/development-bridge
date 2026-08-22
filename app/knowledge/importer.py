from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.api.errors import BridgeError, ErrorCode

from .store import KnowledgeStore


def plain_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(plain_text(item) for item in value)
    if isinstance(value, dict):
        return plain_text(value.get("text", ""))
    return ""


def normalized_timestamp(message: dict[str, Any], key: str, unix_key: str) -> str | None:
    value = message.get(key)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC).isoformat()
        except ValueError:
            pass
    unix_value = message.get(unix_key)
    if unix_value is not None:
        try:
            return datetime.fromtimestamp(int(unix_value), UTC).isoformat()
        except (TypeError, ValueError, OverflowError):
            pass
    return None


class TelegramJsonImporter:
    def __init__(self, store: KnowledgeStore) -> None:
        self.store = store

    def import_file(
        self,
        input_path: Path,
        source_id: str,
        *,
        source_url: str | None = None,
        title: str | None = None,
    ) -> dict[str, int | str]:
        if not source_id or len(source_id) > 200:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "source_id must contain 1 to 200 characters")
        try:
            with input_path.open("r", encoding="utf-8") as stream:
                document = json.load(stream)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "Malformed Telegram JSON export",
                details={"input": str(input_path)},
            ) from error
        if not isinstance(document, dict) or not isinstance(document.get("messages"), list):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Malformed Telegram JSON export")
        imported_at = datetime.now(UTC).isoformat()
        source_title = title or str(document.get("name") or source_id)
        inserted = updated = skipped = 0
        self.store.initialize()
        with self.store.connect() as connection:
            connection.execute(
                """INSERT INTO sources(source_id, platform, title, source_url, imported_at, metadata_json)
                   VALUES (?, 'telegram', ?, ?, ?, ?)
                   ON CONFLICT(source_id) DO UPDATE SET
                     platform='telegram', title=excluded.title,
                     source_url=COALESCE(excluded.source_url, sources.source_url),
                     imported_at=excluded.imported_at, metadata_json=excluded.metadata_json""",
                (source_id, source_title, source_url, imported_at, json.dumps({"export_type": document.get("type")}, ensure_ascii=False)),
            )
            source_fk = connection.execute(
                "SELECT id FROM sources WHERE source_id = ?", (source_id,)
            ).fetchone()[0]
            for message in document["messages"]:
                if not isinstance(message, dict) or message.get("id") is None:
                    skipped += 1
                    continue
                timestamp = normalized_timestamp(message, "date", "date_unixtime")
                if timestamp is None:
                    skipped += 1
                    continue
                platform_message_id = str(message["id"])
                author_fk = self._author(connection, source_fk, message)
                text_value = message.get("text", "")
                topic = {
                    key: message[key]
                    for key in ("topic_id", "message_thread_id", "reply_to_top_id", "forum_topic_created")
                    if key in message
                }
                values = (
                    source_fk, platform_message_id, str(message.get("type") or "message"),
                    timestamp, normalized_timestamp(message, "edited", "edited_unixtime"),
                    author_fk, plain_text(text_value), json.dumps(text_value, ensure_ascii=False),
                    str(message["reply_to_message_id"]) if message.get("reply_to_message_id") is not None else None,
                    json.dumps(topic, ensure_ascii=False) if topic else None,
                    message.get("permalink"),
                    json.dumps(
                        {"text_entities": message.get("text_entities", [])},
                        ensure_ascii=False,
                    ),
                )
                existed = connection.execute(
                    "SELECT id FROM messages WHERE source_fk=? AND platform_message_id=?",
                    (source_fk, platform_message_id),
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
                    values,
                )
                message_fk = connection.execute(
                    "SELECT id FROM messages WHERE source_fk=? AND platform_message_id=?",
                    (source_fk, platform_message_id),
                ).fetchone()[0]
                connection.execute("DELETE FROM attachments WHERE message_fk=?", (message_fk,))
                attachment = self._attachment(message)
                if attachment is not None:
                    connection.execute(
                        "INSERT INTO attachments(message_fk, attachment_type, exported_path, metadata_json) VALUES (?, ?, ?, ?)",
                        (message_fk, *attachment),
                    )
                if existed is None:
                    inserted += 1
                else:
                    updated += 1
        return {"source_id": source_id, "inserted": inserted, "updated": updated, "skipped": skipped}

    @staticmethod
    def _author(connection, source_fk: int, message: dict[str, Any]) -> int | None:
        display = message.get("from") or message.get("actor")
        platform_id = message.get("from_id") or message.get("actor_id")
        if display is None and platform_id is None:
            return None
        display_name = str(display or platform_id)
        author_key = str(platform_id or f"name:{display_name}")
        connection.execute(
            """INSERT INTO authors(source_fk, author_key, platform_author_id, display_name)
               VALUES (?, ?, ?, ?) ON CONFLICT(source_fk, author_key) DO UPDATE SET
               platform_author_id=excluded.platform_author_id, display_name=excluded.display_name""",
            (source_fk, author_key, str(platform_id) if platform_id is not None else None, display_name),
        )
        return connection.execute(
            "SELECT id FROM authors WHERE source_fk=? AND author_key=?", (source_fk, author_key)
        ).fetchone()[0]

    @staticmethod
    def _attachment(message: dict[str, Any]) -> tuple[str, str | None, str] | None:
        path = message.get("file") or message.get("photo") or message.get("thumbnail")
        media_keys = (
            "media_type", "mime_type", "duration_seconds", "width", "height",
            "file_size", "sticker_emoji", "location_information", "contact_information",
        )
        metadata = {key: message[key] for key in media_keys if key in message}
        if path is None and not metadata:
            return None
        attachment_type = str(message.get("media_type") or ("photo" if message.get("photo") else "file"))
        return attachment_type, str(path) if path is not None else None, json.dumps(metadata, ensure_ascii=False)
