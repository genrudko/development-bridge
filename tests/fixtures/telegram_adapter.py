from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.knowledge.telegram import (
    TelegramAttachment,
    TelegramMessage,
    TelegramSource,
)


SOURCE = TelegramSource(
    entity_id="987654321",
    username="ad5x_community",
    title="AD5X Community",
    kind="group",
    canonical_url="https://t.me/ad5x_community",
)


def message(message_id: int, text: str | None = None) -> TelegramMessage:
    return TelegramMessage(
        message_id=message_id,
        timestamp=datetime(2025, 1, 1, tzinfo=UTC) + timedelta(minutes=message_id),
        edited_timestamp=None,
        author_id=f"user-{message_id % 2}",
        author_name="Alice" if message_id % 2 else "Bob",
        text=text or f"AD5X Z-offset message {message_id}",
        reply_to_message_id=message_id - 1 if message_id == 5 else None,
        topic={"reply_to_top_id": 4, "forum_topic": True} if message_id == 5 else None,
        permalink=f"https://t.me/ad5x_community/{message_id}",
        attachments=(
            TelegramAttachment(
                "document",
                {"telegram_media_id": "doc-5", "mime_type": "application/pdf", "size": 1234},
            ),
        ) if message_id == 5 else (),
    )


class FakeTelegramAdapter:
    def __init__(self, messages=None, *, resolve_error=None, fetch_error=None):
        self.messages = {item.message_id: item for item in (messages or [])}
        self.resolve_error = resolve_error
        self.fetch_error = fetch_error
        self.resolve_calls = []
        self.fetch_calls = []

    async def resolve(self, canonical_url):
        self.resolve_calls.append(canonical_url)
        if self.resolve_error:
            raise self.resolve_error
        return SOURCE

    async def fetch_messages(self, source, *, limit, before_id=None, after_id=None):
        self.fetch_calls.append({
            "limit": limit, "before_id": before_id, "after_id": after_id,
        })
        if self.fetch_error:
            raise self.fetch_error
        values = sorted(
            self.messages.values(),
            key=lambda item: item.message_id,
            reverse=after_id is None,
        )
        if before_id is not None:
            values = [item for item in values if item.message_id < before_id]
        if after_id is not None:
            values = [item for item in values if item.message_id > after_id]
        return tuple(values[:limit])
