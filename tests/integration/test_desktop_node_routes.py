from __future__ import annotations

import httpx2
import pytest

from app.container import build_container
from app.runtime import create_server
from app.settings import BridgeSettings
from app.transport import create_streamable_http_app


def app_with(token=None, max_request_bytes=262144):
    settings = BridgeSettings.model_validate({"desktop_nodes": {"token": token, "max_request_bytes": max_request_bytes}})
    container = build_container(settings)
    return create_streamable_http_app(create_server(container), settings, container)


@pytest.mark.asyncio
async def test_agent_routes_auth_registration_and_bounds():
    transport = httpx2.ASGITransport(app=app_with("secret", 4096))
    async with httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        assert (await client.post("/mcp/desktop-nodes/desk/register", json={})).status_code == 401
        headers = {"Authorization": "Bearer secret"}
        registered = await client.post("/mcp/desktop-nodes/desk/register", headers=headers, json={"fusion_available": True, "tools": [{"name": "ping"}]})
        assert registered.status_code == 200
        assert registered.json()["online"] is True
        oversized = await client.post("/mcp/desktop-nodes/desk/register", headers=headers, content=b"{" + b" " * 5000 + b"}")
        assert oversized.status_code == 413
        invalid_id = await client.post("/mcp/desktop-nodes/bad!/register", headers=headers, json={"tools": []})
        assert invalid_id.status_code == 400
        assert invalid_id.json()["code"] == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_agent_routes_are_hidden_without_token():
    transport = httpx2.ASGITransport(app=app_with())
    async with httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        assert (await client.post("/mcp/desktop-nodes/desk/register", json={})).status_code == 404
