from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.knowledge import KnowledgeService, KnowledgeStore, TelegramKnowledgeService
from app.knowledge.telegram import (
    TelegramAuthorizationRequired,
    TelegramFloodWait,
    TelegramRequestFailed,
    TelegramSourceNotFound,
    TelethonTelegramAdapter,
    canonicalize_public_url,
    ensure_session_file,
)
from tests.fixtures.telegram_adapter import FakeTelegramAdapter, message
from tests.fixtures.telegram_adapter import SOURCE


@pytest.mark.parametrize(
    ("value", "canonical", "username"),
    [
        ("https://t.me/AD5X_Community", "https://t.me/ad5x_community", "ad5x_community"),
        ("http://telegram.me/AD5X_Community", "https://t.me/ad5x_community", "ad5x_community"),
        ("@AD5X_Community", "https://t.me/ad5x_community", "ad5x_community"),
    ],
)
def test_public_url_normalization(value, canonical, username):
    assert canonicalize_public_url(value) == (canonical, username)


@pytest.mark.parametrize(
    "value",
    ["https://example.com/group", "https://t.me/+invite", "https://t.me/c/123", "https://t.me/a/b", "not-a-link"],
)
def test_invalid_or_private_urls_are_rejected(value):
    with pytest.raises(ValueError):
        canonicalize_public_url(value)


def test_telethon_message_normalizer_keeps_metadata_without_downloading(monkeypatch):
    monkeypatch.setattr("app.knowledge.telegram.utils.get_display_name", lambda sender: "Alice")
    raw = SimpleNamespace(
        id=50,
        date=message(5).timestamp,
        edit_date=message(5).timestamp,
        sender=object(),
        sender_id=123,
        message="live Z-offset",
        action=None,
        reply_to=SimpleNamespace(reply_to_top_id=40, forum_topic=True),
        reply_to_msg_id=49,
        photo=SimpleNamespace(
            id=700,
            sizes=[SimpleNamespace(w=320, h=200, size=1000), SimpleNamespace(w=1280, h=800, size=4000)],
        ),
        document=SimpleNamespace(
            id=800, size=2048, mime_type="application/pdf",
            attributes=[SimpleNamespace(file_name="report.pdf")],
        ),
    )
    normalized = TelethonTelegramAdapter._normalize_message(raw, SOURCE)
    assert normalized.author_id == "123"
    assert normalized.author_name == "Alice"
    assert normalized.reply_to_message_id == 49
    assert normalized.topic == {"reply_to_top_id": 40, "forum_topic": True}
    assert [item.attachment_type for item in normalized.attachments] == ["photo", "document"]
    assert normalized.attachments[0].metadata["w"] == 1280
    assert normalized.attachments[1].metadata["file_name"] == "report.pdf"


def test_telethon_session_file_is_created_with_private_permissions(tmp_path):
    actual = ensure_session_file(tmp_path / "telegram")
    assert actual.name == "telegram.session"
    assert actual.stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_telethon_adapter_requests_forward_order_only_for_incremental(monkeypatch, tmp_path):
    class RecordingClient:
        def __init__(self):
            self.calls = []

        async def connect(self):
            pass

        async def disconnect(self):
            pass

        async def is_user_authorized(self):
            return True

        async def get_entity(self, value):
            return object()

        async def iter_messages(self, entity, **kwargs):
            self.calls.append(kwargs)
            if False:
                yield None

    client = RecordingClient()
    adapter = TelethonTelegramAdapter(12345, "0" * 32, tmp_path / "telegram.session")
    monkeypatch.setattr(adapter, "_client", lambda: client)
    await adapter.fetch_messages(SOURCE, limit=2, before_id=100)
    await adapter.fetch_messages(SOURCE, limit=2, after_id=100)
    assert client.calls == [
        {"limit": 2, "max_id": 100, "min_id": 0, "reverse": False},
        {"limit": 2, "max_id": 0, "min_id": 100, "reverse": True},
    ]


@pytest.mark.asyncio
async def test_add_is_stable_idempotent_and_syncs_history_in_batches(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.sqlite3")
    adapter = FakeTelegramAdapter([message(value) for value in range(1, 6)])
    service = TelegramKnowledgeService(store, adapter, default_batch_size=2, recent_window_size=2)

    added = await service.source_add("https://t.me/AD5X_Community")
    assert added["source_id"] == "telegram-ad5x-community"
    assert added["sync"]["fetched"] == 2
    assert added["sync"]["history_complete"] is False
    assert adapter.resolve_calls == ["https://t.me/ad5x_community"]

    repeated = await service.source_add("@ad5x_community")
    assert repeated["source_id"] == added["source_id"]
    assert len(KnowledgeService(store).source_list()) == 1
    assert repeated["sync"]["phase"] == "history"

    completed = await service.source_sync(added["source_id"])
    assert completed["fetched"] == 1
    assert completed["history_complete"] is True
    assert completed["has_more"] is False
    assert KnowledgeService(store).source_list()[0]["message_count"] == 5


@pytest.mark.asyncio
async def test_incremental_sync_adds_new_and_refreshes_edited_recent_message(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.sqlite3")
    adapter = FakeTelegramAdapter([message(value) for value in range(1, 4)])
    service = TelegramKnowledgeService(store, adapter, default_batch_size=5, recent_window_size=3)
    added = await service.source_add("@ad5x_community")
    assert added["sync"]["history_complete"] is True

    adapter.messages[3] = replace(message(3), text="edited reproducible Z-offset", edited_timestamp=message(3).timestamp)
    adapter.messages[4] = message(4, "new calibration result")
    synced = await service.source_sync(added["source_id"])
    assert synced["phase"] == "incremental"
    assert synced["inserted"] == 1
    assert synced["updated"] >= 1
    corpus = KnowledgeService(store)
    assert corpus.message(added["source_id"], "3")["text"] == "edited reproducible Z-offset"
    assert corpus.message(added["source_id"], "4")["text"] == "new calibration result"


@pytest.mark.asyncio
async def test_incremental_batches_advance_oldest_first_without_message_gaps(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.sqlite3")
    adapter = FakeTelegramAdapter([message(value) for value in range(1, 4)])
    service = TelegramKnowledgeService(
        store, adapter, default_batch_size=5, recent_window_size=2
    )
    added = await service.source_add("@ad5x_community")
    source_id = added["source_id"]
    assert added["sync"]["history_complete"] is True
    assert added["sync"]["newest_message_id"] == "3"

    adapter.messages.update({value: message(value) for value in range(4, 11)})
    cursors = []
    while True:
        synced = await service.source_sync(source_id, limit=2)
        cursors.append(synced["newest_message_id"])
        if not synced["has_more"]:
            break

    assert cursors == ["5", "7", "9", "10"]
    incremental_calls = [
        call for call in adapter.fetch_calls if call["after_id"] is not None
    ]
    assert [call["after_id"] for call in incremental_calls] == [3, 5, 7, 9]
    corpus = KnowledgeService(store)
    assert [corpus.message(source_id, str(value))["message_id"] for value in range(1, 11)] == [
        str(value) for value in range(1, 11)
    ]

    adapter.messages[10] = replace(
        message(10), text="edited newest Z-offset", edited_timestamp=message(10).timestamp
    )
    refreshed = await service.source_sync(source_id, limit=2)
    assert refreshed["has_more"] is False
    assert corpus.message(source_id, "10")["text"] == "edited newest Z-offset"


@pytest.mark.asyncio
async def test_live_normalization_preserves_author_reply_topic_and_attachment_metadata(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.sqlite3")
    service = TelegramKnowledgeService(
        store, FakeTelegramAdapter([message(4), message(5)]), default_batch_size=10
    )
    added = await service.source_add("@ad5x_community")
    normalized = KnowledgeService(store).message(added["source_id"], "5")
    assert normalized["author"] == "Alice"
    assert normalized["author_id"] == "user-1"
    assert normalized["reply_to_message_id"] == "4"
    assert normalized["topic"] == {"reply_to_top_id": 4, "forum_topic": True}
    assert normalized["attachments"] == [{
        "type": "document", "exported_path": None,
        "metadata": {"telegram_media_id": "doc-5", "mime_type": "application/pdf", "size": 1234},
    }]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (TelegramSourceNotFound("missing"), ErrorCode.TELEGRAM_SOURCE_NOT_FOUND, False),
        (TelegramAuthorizationRequired(), ErrorCode.TELEGRAM_AUTHORIZATION_REQUIRED, False),
        (TelegramFloodWait(42), ErrorCode.TELEGRAM_RATE_LIMITED, True),
        (TelegramRequestFailed(), ErrorCode.TELEGRAM_REQUEST_FAILED, True),
    ],
)
async def test_transport_errors_are_normalized(tmp_path, error, code, retryable):
    service = TelegramKnowledgeService(
        KnowledgeStore(tmp_path / "knowledge.sqlite3"),
        FakeTelegramAdapter(resolve_error=error),
    )
    with pytest.raises(BridgeError) as caught:
        await service.source_add("@ad5x_community")
    assert caught.value.code == code
    assert caught.value.retryable is retryable
    if code == ErrorCode.TELEGRAM_RATE_LIMITED:
        assert caught.value.details == {"retry_after_seconds": 42}


@pytest.mark.asyncio
async def test_sync_rejects_non_telegram_or_missing_source(tmp_path):
    service = TelegramKnowledgeService(
        KnowledgeStore(tmp_path / "knowledge.sqlite3"), FakeTelegramAdapter()
    )
    with pytest.raises(BridgeError) as caught:
        await service.source_sync("missing")
    assert caught.value.code == ErrorCode.TELEGRAM_SOURCE_NOT_FOUND
