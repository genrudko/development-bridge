from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.knowledge import KnowledgeService, KnowledgeStore, TelegramJsonImporter


FIXTURE = Path(__file__).parents[1] / "fixtures" / "telegram_export.json"


def imported(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.sqlite3")
    importer = TelegramJsonImporter(store)
    result = importer.import_file(
        FIXTURE, "ad5x", source_url="https://t.me/ad5x", title="AD5X Public"
    )
    return store, importer, KnowledgeService(store), result


def test_import_normalizes_text_metadata_replies_attachments_and_unknown_fields(tmp_path):
    _, _, service, result = imported(tmp_path)
    assert result == {"source_id": "ad5x", "inserted": 4, "updated": 0, "skipped": 0}
    source = service.source_list()[0]
    assert source["platform"] == "telegram"
    assert source["title"] == "AD5X Public"
    assert source["source_url"] == "https://t.me/ad5x"
    assert source["message_count"] == 4
    assert source["oldest_timestamp"] is not None
    assert source["newest_timestamp"] is not None
    assert source["last_imported_timestamp"] is not None

    mixed = service.message("ad5x", "102")
    assert mixed["text"] == "Confirmed: Z-offset remains stable after restart."
    assert mixed["author"] == "Bob Builder"
    assert mixed["reply_parent"]["message_id"] == "100"
    assert mixed["reply_parent"]["author"] == "Alice Admin"
    assert mixed["metadata"]["text_entities"][0]["type"] == "bold"
    attachment_message = service.message("ad5x", "101")
    assert attachment_message["topic"] == {"topic_id": 42, "reply_to_top_id": 100}
    attachment = attachment_message["attachments"][0]
    assert attachment["exported_path"] == "photos/photo_1.jpg"
    assert attachment["metadata"]["width"] == 1280
    assert service.message("ad5x", "103")["message_type"] == "service"


def test_repeated_import_is_idempotent_and_updates_existing_message(tmp_path):
    _, importer, service, _ = imported(tmp_path)
    repeated = importer.import_file(FIXTURE, "ad5x")
    assert repeated["inserted"] == 0
    assert repeated["updated"] == 4
    assert service.source_list()[0]["message_count"] == 4

    changed = json.loads(FIXTURE.read_text(encoding="utf-8"))
    changed["messages"][1]["text"] = "Updated reproducible Z-offset measurement"
    update_path = tmp_path / "updated.json"
    update_path.write_text(json.dumps(changed), encoding="utf-8")
    importer.import_file(update_path, "ad5x")
    assert service.message("ad5x", "100")["text"].startswith("Updated reproducible")
    assert service.search("drifts") == []
    assert service.search("reproducible")[0]["message_id"] == "100"


def test_search_filters_dates_limits_and_preserves_provenance(tmp_path):
    _, _, service, _ = imported(tmp_path)
    results = service.search("Z-offset", source_ids=["ad5x"], limit=1)
    assert len(results) == 1
    assert results[0]["reference"].startswith("telegram:ad5x:")
    assert results[0]["snippet"]
    assert service.search("Z-offset", source_ids=["other"]) == []
    assert service.search("Z-offset", date_from="2025-02-03T10:09:00Z")[0]["message_id"] == "102"
    assert service.search("Z-offset", date_to="2025-02-03T10:01:00Z")[0]["message_id"] == "100"
    with pytest.raises(BridgeError) as caught:
        service.search(" ")
    assert caught.value.code == ErrorCode.INVALID_ARGUMENT


def test_exact_lookup_neighborhood_and_thread_reconstruction_are_bounded(tmp_path):
    store, _, service, _ = imported(tmp_path)
    message = service.message("ad5x", "102")
    assert [item["message_id"] for item in message["neighborhood"]["before"]] == ["100", "101"]
    assert [item["message_id"] for item in message["neighborhood"]["after"]] == ["103"]
    thread = service.thread("ad5x", "100", limit=1, depth=3)
    assert thread["message"]["message_id"] == "100"
    assert [item["message_id"] for item in thread["descendants"]] == ["102"]
    broken = service.thread("ad5x", "101")
    assert broken["ancestors"] == [{"message_id": "999", "missing": True}]
    with store.connect() as connection:
        connection.execute(
            "UPDATE messages SET reply_to_message_id='102' WHERE platform_message_id='100'"
        )
    cyclic = service.thread("ad5x", "100", depth=50)
    assert len(cyclic["ancestors"]) == 1
    assert cyclic["descendants"] == []
    with pytest.raises(BridgeError) as caught:
        service.message("ad5x", "missing")
    assert caught.value.code == ErrorCode.KNOWLEDGE_MESSAGE_NOT_FOUND


def test_malformed_export_is_reported_without_parser_traceback(tmp_path):
    malformed = tmp_path / "bad.json"
    malformed.write_text("{bad", encoding="utf-8")
    with pytest.raises(BridgeError) as caught:
        TelegramJsonImporter(KnowledgeStore(tmp_path / "db.sqlite3")).import_file(malformed, "bad")
    assert caught.value.code == ErrorCode.INVALID_ARGUMENT
    assert caught.value.message == "Malformed Telegram JSON export"
