from __future__ import annotations

import base64
import json
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

import httpx2
import pytest
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.container import build_container
from app.knowledge import KnowledgeStore, TelegramJsonImporter
from app.knowledge.exports import (
    AttachmentExportRegistry,
    KnowledgeAttachmentExportService,
)
from app.knowledge.telegram import TelegramAttachment
from app.runtime import create_server
from app.settings import BridgeSettings
from app.transport import create_streamable_http_app
from tests.fixtures.telegram_adapter import FakeTelegramAdapter, message as telegram_message


FIXTURE = Path(__file__).parents[1] / "fixtures" / "telegram_export.json"
PNG = b"\x89PNG\r\n\x1a\n" + b"test-image-bytes"


@pytest.mark.asyncio
async def test_full_mcp_session_exercises_all_knowledge_tools(tmp_path):
    database = tmp_path / "knowledge.sqlite3"
    TelegramJsonImporter(KnowledgeStore(database)).import_file(FIXTURE, "ad5x")
    settings = BridgeSettings.model_validate({
        "server": {"name": "knowledge-test"},
        "knowledge": {"database_path": database},
    })
    container = build_container(settings)
    app = create_streamable_http_app(create_server(container), settings, container)

    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            async with streamable_http_client(
                "http://127.0.0.1/mcp", http_client=client
            ) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    assert len(listed.tools) == 81

                    sources = await session.call_tool("knowledge_source_list", {})
                    source_payload = json.loads(sources.content[0].text)
                    assert source_payload["data"]["sources"][0]["source_id"] == "ad5x"

                    searched = await session.call_tool("knowledge_search", {
                        "query": "Z-offset", "source_ids": ["ad5x"], "limit": 2,
                    })
                    results = json.loads(searched.content[0].text)["data"]["results"]
                    assert results[0]["reference"].startswith("telegram:ad5x:")

                    message = await session.call_tool("knowledge_message", {
                        "source_id": "ad5x", "message_id": "102",
                    })
                    message_payload = json.loads(message.content[0].text)["data"]
                    assert message_payload["reply_parent"]["message_id"] == "100"

                    thread = await session.call_tool("knowledge_thread", {
                        "source_id": "ad5x", "message_id": "100", "limit": 10, "depth": 5,
                    })
                    thread_payload = json.loads(thread.content[0].text)["data"]
                    assert thread_payload["descendants"][0]["message_id"] == "102"


@pytest.mark.asyncio
async def test_unconfigured_knowledge_store_returns_structured_error(tmp_path):
    settings = BridgeSettings()
    container = build_container(settings)
    app = create_streamable_http_app(create_server(container), settings, container)
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            async with streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    result = await session.call_tool("knowledge_source_list", {})
    payload = json.loads(result.content[0].text)
    assert result.is_error is True
    assert payload["error"]["code"] == "KNOWLEDGE_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_full_link_first_mcp_flow_adds_syncs_and_queries_telegram(
    tmp_path, monkeypatch
):
    database = tmp_path / "knowledge.sqlite3"
    messages = [telegram_message(value) for value in range(1, 6)]
    messages[-1] = replace(messages[-1], attachments=(TelegramAttachment("document", {
        "telegram_media_id": "cfg-5", "mime_type": "text/plain",
        "file_name": "printer.cfg", "size": 17,
    }),))
    adapter = FakeTelegramAdapter(
        messages, attachment_bytes={"document-cfg-5": b"z_offset: -1.25\n"}
    )
    settings = BridgeSettings.model_validate({
        "server": {
            "name": "telegram-knowledge-test",
            "public_base_url": "https://downloads.example",
        },
        "knowledge": {
            "database_path": database,
            "attachment_directory": tmp_path / "attachments",
            "telegram": {"sync_batch_size": 2, "recent_window_size": 2},
        },
    })
    container = build_container(settings, telegram_adapter=adapter)
    export_clock = {"value": 100.0}
    container = replace(
        container,
        knowledge_attachment_exports=KnowledgeAttachmentExportService(
            container.knowledge_attachments,
            AttachmentExportRegistry(
                600, monotonic=lambda: export_clock["value"]
            ),
            str(settings.server.public_base_url),
            settings.server.endpoint,
        ),
    )
    app = create_streamable_http_app(create_server(container), settings, container)

    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            async with streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    added = await session.call_tool(
                        "knowledge_source_add", {"url": "https://t.me/AD5X_Community"}
                    )
                    added_data = json.loads(added.content[0].text)["data"]
                    source_id = added_data["source_id"]
                    assert added_data["sync"]["has_more"] is True

                    while True:
                        synced = await session.call_tool(
                            "knowledge_source_sync", {"source_id": source_id}
                        )
                        sync_data = json.loads(synced.content[0].text)["data"]
                        if not sync_data["has_more"]:
                            break

                    searched = await session.call_tool(
                        "knowledge_search", {"query": "Z-offset", "source_ids": [source_id]}
                    )
                    results = json.loads(searched.content[0].text)["data"]["results"]
                    assert len(results) == 5

                    exact = await session.call_tool(
                        "knowledge_message", {"source_id": source_id, "message_id": "5"}
                    )
                    exact_data = json.loads(exact.content[0].text)["data"]
                    assert exact_data["reply_parent"]["message_id"] == "4"
                    attachment_id = exact_data["attachments"][0]["attachment_id"]
                    assert adapter.download_calls == []

                    exported = await session.call_tool("knowledge_attachment_export", {
                        "source_id": source_id, "message_id": "5",
                        "attachment_id": attachment_id,
                    })
                    exported_data = json.loads(exported.content[0].text)["data"]
                    assert exported_data["export_url"].startswith(
                        "https://downloads.example/mcp/knowledge/exports/"
                    )
                    assert isinstance(exported.content[1], types.ResourceLink)
                    assert exported.content[1].uri == exported_data["export_url"]
                    assert exported.content[1].name == exported_data["file_name"]
                    assert exported.content[1].title == exported_data["file_name"]
                    assert exported.content[1].mime_type == exported_data["media_type"]
                    assert exported.content[1].size == exported_data["size_bytes"]
                    assert isinstance(exported.content[2], types.EmbeddedResource)
                    assert isinstance(
                        exported.content[2].resource, types.BlobResourceContents
                    )
                    assert exported.content[2].resource.uri == exported_data["export_url"]
                    assert exported.content[2].resource.mime_type == exported_data["media_type"]
                    assert base64.b64decode(exported.content[2].resource.blob) == (
                        b"z_offset: -1.25\n"
                    )
                    assert str(tmp_path) not in json.dumps(exported_data)
                    assert len(adapter.download_calls) == 1
                    export_path = urlparse(exported_data["export_url"]).path

                    first_get = await client.get(export_path)
                    repeated_get = await client.get(export_path)
                    export_head = await client.head(export_path)
                    assert first_get.content == repeated_get.content == b"z_offset: -1.25\n"
                    assert export_head.status_code == 200
                    assert first_get.headers["content-type"].startswith("text/plain")
                    assert int(first_get.headers["content-length"]) == len(b"z_offset: -1.25\n")
                    assert "printer.cfg" in first_get.headers["content-disposition"]
                    assert first_get.headers["etag"] == f'"{exported_data["sha256"]}"'
                    assert first_get.headers["cache-control"] == "private, no-store"
                    assert (await client.get("/mcp/knowledge/exports/random-token")).status_code == 404
                    assert (await client.get(export_path + "/different-attachment")).status_code == 404

                    second_export = await session.call_tool("knowledge_attachment_export", {
                        "source_id": source_id, "message_id": "5",
                        "attachment_id": attachment_id,
                    })
                    second_data = json.loads(second_export.content[0].text)["data"]
                    assert second_data["export_url"] != exported_data["export_url"]
                    assert second_data["sha256"] == exported_data["sha256"]
                    assert isinstance(second_export.content[1], types.ResourceLink)
                    assert isinstance(second_export.content[2], types.EmbeddedResource)
                    assert len(adapter.download_calls) == 1

                    monkeypatch.setattr(
                        "app.tools.knowledge.KNOWLEDGE_ATTACHMENT_INLINE_LIMIT", 1
                    )
                    oversized_export = await session.call_tool(
                        "knowledge_attachment_export", {
                            "source_id": source_id, "message_id": "5",
                            "attachment_id": attachment_id,
                        }
                    )
                    assert len(oversized_export.content) == 2
                    assert isinstance(oversized_export.content[1], types.ResourceLink)
                    assert len(adapter.download_calls) == 1

                    export_clock["value"] = 701.0
                    assert (await client.get(export_path)).status_code == 404

                    opened = await session.call_tool("knowledge_attachment_open", {
                        "source_id": source_id, "message_id": "5",
                        "attachment_id": attachment_id,
                    })
                    opened_data = json.loads(opened.content[0].text)["data"]
                    assert opened_data["cached"] is True
                    assert opened.content[1].text == "z_offset: -1.25\n"
                    assert len(adapter.download_calls) == 1

                    raw = await client.get(opened_data["download_path"])
                    assert raw.content == b"z_offset: -1.25\n"
                    assert raw.headers["content-type"].startswith("text/plain")
                    assert raw.headers["etag"] == f'"{opened_data["sha256"]}"'
                    head = await client.head(opened_data["download_path"])
                    assert head.status_code == 200
                    assert int(head.headers["content-length"]) == len(raw.content)

                    reopened = await session.call_tool("knowledge_attachment_open", {
                        "source_id": source_id, "message_id": "5",
                        "attachment_id": attachment_id,
                    })
                    assert reopened.is_error is False
                    assert len(adapter.download_calls) == 1

                    thread = await session.call_tool(
                        "knowledge_thread", {"source_id": source_id, "message_id": "4"}
                    )
                    thread_data = json.loads(thread.content[0].text)["data"]
                    assert thread_data["descendants"][0]["message_id"] == "5"


@pytest.mark.asyncio
async def test_configured_corpus_without_telegram_transport_returns_structured_error(tmp_path):
    settings = BridgeSettings.model_validate({
        "knowledge": {"database_path": tmp_path / "knowledge.sqlite3"}
    })
    container = build_container(settings)
    app = create_streamable_http_app(create_server(container), settings, container)
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            async with streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "knowledge_source_add", {"url": "https://t.me/ad5x_community"}
                    )
    payload = json.loads(result.content[0].text)
    assert payload["error"]["code"] == "TELEGRAM_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_attachment_open_returns_real_mcp_image_content(tmp_path):
    image_message = replace(telegram_message(5), attachments=(TelegramAttachment("photo", {
        "telegram_media_id": "photo-5", "mime_type": "image/png", "file_name": "view.png",
    }),))
    invalid_image_message = replace(telegram_message(6), attachments=(TelegramAttachment("photo", {
        "telegram_media_id": "photo-6", "mime_type": "image/png", "file_name": "broken.png",
    }),))
    adapter = FakeTelegramAdapter(
        [image_message, invalid_image_message], attachment_bytes={
            "photo-photo-5": PNG, "photo-photo-6": b"not a png",
        }
    )
    settings = BridgeSettings.model_validate({
        "knowledge": {
            "database_path": tmp_path / "knowledge.sqlite3",
            "attachment_directory": tmp_path / "attachments",
        },
    })
    container = build_container(settings, telegram_adapter=adapter)
    app = create_streamable_http_app(create_server(container), settings, container)
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            async with streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    added = await session.call_tool(
                        "knowledge_source_add", {"url": "https://t.me/ad5x_community"}
                    )
                    source_id = json.loads(added.content[0].text)["data"]["source_id"]
                    opened = await session.call_tool("knowledge_attachment_open", {
                        "source_id": source_id, "message_id": "5",
                        "attachment_id": "photo-photo-5",
                    })
                    invalid = await session.call_tool("knowledge_attachment_open", {
                        "source_id": source_id, "message_id": "6",
                        "attachment_id": "photo-photo-6",
                    })
                    invalid_data = json.loads(invalid.content[0].text)["data"]
                    raw = await client.get(invalid_data["download_path"])
    assert opened.content[1].type == "image"
    assert opened.content[1].mime_type == "image/png"
    assert len(invalid.content) == 1
    assert invalid_data["media_type_mismatch"] is True
    assert raw.content == b"not a png"
