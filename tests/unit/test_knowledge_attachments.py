from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.api.errors import BridgeError, ErrorCode
from app.knowledge.attachments import (
    AttachmentStorage,
    KnowledgeAttachmentService,
    PreviewFrame,
)
from app.knowledge.exports import (
    AttachmentExportRegistry,
    KnowledgeAttachmentExportService,
)
from app.knowledge.service import KnowledgeService
from app.knowledge.store import KnowledgeStore
from app.knowledge.telegram import TelegramAttachment, TelegramFloodWait
from app.knowledge.telegram_service import TelegramKnowledgeService
from tests.fixtures.telegram_adapter import FakeTelegramAdapter, message


PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
)


async def configured(
    tmp_path: Path, payload: bytes, metadata: dict, *, error=None,
    max_bytes: int = 1024 * 1024,
):
    live = replace(
        message(5),
        attachments=(TelegramAttachment("document", metadata),),
    )
    attachment_id = "document-" + metadata["telegram_media_id"]
    adapter = FakeTelegramAdapter(
        [message(4), live], attachment_bytes={attachment_id: payload}, download_error=error
    )
    store = KnowledgeStore(tmp_path / "knowledge.sqlite3")
    added = await TelegramKnowledgeService(store, adapter, default_batch_size=10).source_add(
        "@ad5x_community"
    )
    service = KnowledgeAttachmentService(
        store, AttachmentStorage(tmp_path / "attachments", max_bytes), adapter
    )
    return store, adapter, service, added["source_id"], attachment_id


@pytest.mark.asyncio
async def test_stable_identity_survives_refresh_and_open_is_lazy_and_cached(tmp_path):
    metadata = {
        "telegram_media_id": "config-5", "mime_type": "text/plain",
        "file_name": "../../printer.cfg", "size": 17,
    }
    store, adapter, service, source_id, attachment_id = await configured(
        tmp_path, b"z_offset: -1.25\n", metadata
    )
    assert adapter.download_calls == []
    before = KnowledgeService(store).message(source_id, "5")["attachments"][0]
    assert before["attachment_id"] == attachment_id
    assert before["cached"] is False

    # A normal message refresh updates the attachment row without changing identity.
    await TelegramKnowledgeService(store, adapter, default_batch_size=10).source_add(
        "@ad5x_community"
    )
    after = KnowledgeService(store).message(source_id, "5")["attachments"][0]
    assert after["attachment_id"] == attachment_id

    first = await service.open(source_id, "5", attachment_id)
    second = await service.open(source_id, "5", attachment_id)
    assert first.text_preview == "z_offset: -1.25\n"
    assert second.metadata["sha256"] == first.metadata["sha256"]
    assert first.metadata["file_name"] == "printer.cfg"
    assert len(adapter.download_calls) == 1
    assert first.path.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "attachments").stat().st_mode & 0o777 == 0o700


@pytest.mark.asyncio
async def test_wrong_identity_corruption_and_floodwait_are_structured(tmp_path):
    metadata = {"telegram_media_id": "bin-5", "mime_type": "application/octet-stream"}
    _, _, service, source_id, attachment_id = await configured(tmp_path, b"\x00\xff", metadata)
    for wrong_source, wrong_message, wrong_attachment in (
        ("telegram-wrong", "5", attachment_id),
        (source_id, "999", attachment_id),
        (source_id, "5", "document-wrong"),
    ):
        with pytest.raises(BridgeError) as missing:
            await service.open(wrong_source, wrong_message, wrong_attachment)
        assert missing.value.code is ErrorCode.KNOWLEDGE_ATTACHMENT_NOT_FOUND

    opened = await service.open(source_id, "5", attachment_id)
    opened.path.write_bytes(b"corrupt")
    with pytest.raises(BridgeError) as corrupt:
        await service.open(source_id, "5", attachment_id)
    assert corrupt.value.code is ErrorCode.KNOWLEDGE_ATTACHMENT_CORRUPT

    _, _, limited, source_id, attachment_id = await configured(
        tmp_path / "limited", b"ignored", metadata, error=TelegramFloodWait(19)
    )
    with pytest.raises(BridgeError) as flooded:
        await limited.open(source_id, "5", attachment_id)
    assert flooded.value.code is ErrorCode.TELEGRAM_RATE_LIMITED
    assert flooded.value.details == {"retry_after_seconds": 19}


@pytest.mark.asyncio
async def test_image_binary_and_video_presentations(tmp_path):
    image_meta = {"telegram_media_id": "image-5", "mime_type": "image/png"}
    _, _, image_service, source_id, attachment_id = await configured(
        tmp_path / "image", PNG, image_meta
    )
    image = await image_service.open(source_id, "5", attachment_id)
    assert image.images[0].media_type == "image/png"

    binary_meta = {"telegram_media_id": "bin-5", "mime_type": "application/octet-stream"}
    _, _, binary_service, source_id, attachment_id = await configured(
        tmp_path / "binary", b"\x00\xff\x01", binary_meta
    )
    binary = await binary_service.open(source_id, "5", attachment_id)
    assert binary.text_preview is None and binary.images == ()

    class FakePreviewer:
        def preview(self, path, max_frames):
            assert path.read_bytes() == b"fake-video"
            return {"available": True, "duration_seconds": 12, "width": 640, "height": 480}, (
                PreviewFrame(PNG), PreviewFrame(PNG),
            )

    video_meta = {"telegram_media_id": "video-5", "mime_type": "video/mp4"}
    store, adapter, _, source_id, attachment_id = await configured(
        tmp_path / "video", b"fake-video", video_meta
    )
    video_service = KnowledgeAttachmentService(
        store, AttachmentStorage(tmp_path / "video" / "attachments", 1024 * 1024),
        adapter, video_previewer=FakePreviewer(),
    )
    video = await video_service.open(source_id, "5", attachment_id)
    assert video.metadata["video_preview"]["duration_seconds"] == 12
    assert len(video.images) == 2


@pytest.mark.asyncio
async def test_declared_oversize_is_rejected_before_provider_download(tmp_path):
    metadata = {
        "telegram_media_id": "large-5", "mime_type": "application/octet-stream",
        "size": 9,
    }
    store, adapter, service, source_id, attachment_id = await configured(
        tmp_path, b"123456789", metadata, max_bytes=8
    )
    with pytest.raises(BridgeError) as rejected:
        await service.open(source_id, "5", attachment_id)
    assert rejected.value.code is ErrorCode.POLICY_VIOLATION
    assert rejected.value.details == {"declared_size": 9, "limit": 8}
    assert adapter.download_calls == []
    assert list((tmp_path / "attachments").glob(".knowledge-attachment-*")) == []
    with store.connect() as connection:
        assert connection.execute("SELECT count(*) FROM attachment_snapshots").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_actual_stream_is_stopped_at_hard_limit_and_leaves_no_snapshot(tmp_path):
    metadata = {"telegram_media_id": "large-5", "mime_type": "application/octet-stream"}
    store, adapter, service, source_id, attachment_id = await configured(
        tmp_path, b"123456789", metadata, max_bytes=8
    )
    with pytest.raises(BridgeError) as rejected:
        await service.open(source_id, "5", attachment_id)
    assert rejected.value.code is ErrorCode.POLICY_VIOLATION
    assert rejected.value.details == {"actual_size": 9, "limit": 8}
    assert adapter.download_calls[0]["written_bytes"] == 8
    assert list((tmp_path / "attachments").glob(".knowledge-attachment-*")) == []
    with store.connect() as connection:
        assert connection.execute("SELECT count(*) FROM attachment_snapshots").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_payload_exactly_at_hard_limit_is_saved(tmp_path):
    metadata = {
        "telegram_media_id": "exact-5", "mime_type": "application/octet-stream", "size": 8,
    }
    _, adapter, service, source_id, attachment_id = await configured(
        tmp_path, b"12345678", metadata, max_bytes=8
    )
    result = await service.open(source_id, "5", attachment_id)
    assert result.metadata["size_bytes"] == 8
    assert adapter.download_calls[0]["written_bytes"] == 8


@pytest.mark.asyncio
async def test_declared_image_with_invalid_bytes_remains_raw_only(tmp_path):
    metadata = {
        "telegram_media_id": "fake-image-5", "mime_type": "image/png",
        "file_name": "not-really.png",
    }
    _, _, service, source_id, attachment_id = await configured(
        tmp_path, b"definitely not a PNG", metadata
    )
    result = await service.open(source_id, "5", attachment_id)
    assert result.images == ()
    assert result.metadata["media_type"] == "application/octet-stream"
    assert result.metadata["declared_media_type"] == "image/png"
    assert result.metadata["detected_media_type"] is None
    assert result.metadata["media_type_mismatch"] is True
    snapshot, raw = service.snapshot_file(source_id, "5", attachment_id)
    assert snapshot["media_type"] == "application/octet-stream"
    assert raw.read_bytes() == b"definitely not a PNG"


@pytest.mark.asyncio
async def test_pdf_returns_bounded_page_metadata_without_ocr(tmp_path):
    stream = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    writer.write(stream)
    metadata = {"telegram_media_id": "pdf-5", "mime_type": "application/pdf"}
    _, _, service, source_id, attachment_id = await configured(
        tmp_path, stream.getvalue(), metadata
    )
    result = await service.open(source_id, "5", attachment_id)
    assert result.metadata["pdf"] == {"pages": 1, "encrypted": False}
    assert result.text_preview == ""


def test_legacy_attachment_schema_is_migrated_without_recreating_rows(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(database)
    connection.executescript("""
        CREATE TABLE sources(id INTEGER PRIMARY KEY, source_id TEXT UNIQUE, platform TEXT,
          title TEXT, source_url TEXT, imported_at TEXT, metadata_json TEXT);
        CREATE TABLE messages(id INTEGER PRIMARY KEY, source_fk INTEGER,
          platform_message_id TEXT, message_type TEXT, timestamp TEXT, edited_timestamp TEXT,
          author_fk INTEGER, text TEXT, original_text_json TEXT, reply_to_message_id TEXT,
          topic_json TEXT, permalink TEXT, metadata_json TEXT,
          UNIQUE(source_fk, platform_message_id));
        CREATE TABLE attachments(id INTEGER PRIMARY KEY, message_fk INTEGER,
          attachment_type TEXT, exported_path TEXT, metadata_json TEXT);
        INSERT INTO sources VALUES(1,'legacy','telegram','Legacy',NULL,'2025-01-01','{}');
        INSERT INTO messages VALUES(7,1,'42','message','2025-01-01',NULL,NULL,'log','[]',NULL,NULL,NULL,'{}');
        INSERT INTO attachments VALUES(9,7,'file','files/run.log','{"mime_type":"text/plain","size":4}');
    """)
    connection.commit()
    connection.close()

    store = KnowledgeStore(database)
    store.initialize()
    attachment = KnowledgeService(store).message("legacy", "42")["attachments"][0]
    assert attachment["attachment_id"].startswith("file-")
    assert attachment["media_type"] == "text/plain"
    assert attachment["file_name"] == "run.log"


def test_export_tokens_are_opaque_bounded_repeatable_and_expire():
    current = {"monotonic": 100.0}
    registry = AttachmentExportRegistry(
        600,
        capacity=2,
        monotonic=lambda: current["monotonic"],
        utcnow=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )
    first_token, first = registry.issue("source-secret", "123", "attachment-secret")
    second_token, _ = registry.issue("other", "456", "second")
    assert first_token != second_token
    assert len(first_token) >= 43
    assert "source-secret" not in first_token
    assert (first.source_id, first.message_id, first.attachment_id) == (
        "source-secret", "123", "attachment-secret",
    )
    assert registry.lookup(first_token) == first
    assert registry.lookup(first_token) == first

    # Capacity is bounded; the grant nearest expiry is evicted when issuing more.
    third_token, _ = registry.issue("third", "789", "third")
    assert registry.lookup(first_token) is None
    assert registry.lookup(third_token) is not None

    current["monotonic"] = 701.0
    assert registry.lookup(second_token) is None
    assert registry.lookup(third_token) is None


@pytest.mark.asyncio
async def test_export_without_public_origin_is_a_configuration_error(tmp_path):
    metadata = {"telegram_media_id": "export-5", "mime_type": "text/plain"}
    _, adapter, attachments, source_id, attachment_id = await configured(
        tmp_path, b"export", metadata
    )
    exports = KnowledgeAttachmentExportService(
        attachments, AttachmentExportRegistry(600), None, "/mcp"
    )
    with pytest.raises(BridgeError) as missing:
        await exports.export(source_id, "5", attachment_id)
    assert missing.value.code is ErrorCode.KNOWLEDGE_EXPORT_NOT_CONFIGURED
    assert adapter.download_calls == []
