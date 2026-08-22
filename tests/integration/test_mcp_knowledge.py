from __future__ import annotations

import json
from pathlib import Path

import httpx2
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.container import build_container
from app.knowledge import KnowledgeStore, TelegramJsonImporter
from app.runtime import create_server
from app.settings import BridgeSettings
from app.transport import create_streamable_http_app
from tests.fixtures.telegram_adapter import FakeTelegramAdapter, message as telegram_message


FIXTURE = Path(__file__).parents[1] / "fixtures" / "telegram_export.json"


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
                    assert len(listed.tools) == 34

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
async def test_full_link_first_mcp_flow_adds_syncs_and_queries_telegram(tmp_path):
    database = tmp_path / "knowledge.sqlite3"
    adapter = FakeTelegramAdapter([telegram_message(value) for value in range(1, 6)])
    settings = BridgeSettings.model_validate({
        "server": {"name": "telegram-knowledge-test"},
        "knowledge": {
            "database_path": database,
            "telegram": {"sync_batch_size": 2, "recent_window_size": 2},
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
