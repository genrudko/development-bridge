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
                    assert len(listed.tools) == 32

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
