from __future__ import annotations

import asyncio

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
async def test_agent_routes_accept_generic_profile_register_and_heartbeat():
    transport = httpx2.ASGITransport(app=app_with("secret"))
    headers = {"Authorization": "Bearer secret"}
    async with httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        registered = await client.post(
            "/mcp/desktop-nodes/blender-hub/register", headers=headers,
            json={"ready": True, "protocol_profile": "mcp-v1", "tools": [{"name": "dcc.search"}]},
        )
        assert registered.status_code == 200
        assert registered.json()["ready"] is True
        assert registered.json()["protocol_profile"] == "mcp-v1"
        assert registered.json()["fusion_available"] is False

        heartbeat = await client.post(
            "/mcp/desktop-nodes/blender-hub/heartbeat", headers=headers,
            json={"ready": False, "protocol_profile": "mcp-v1"},
        )
        assert heartbeat.status_code == 200
        assert heartbeat.json()["ready"] is False
        assert heartbeat.json()["session_generation"] == registered.json()["session_generation"] + 1


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"ready": "true", "protocol_profile": "mcp-v1", "tools": []},
    {"ready": True, "protocol_profile": "unknown-v1", "tools": []},
    {"ready": True, "fusion_available": False, "protocol_profile": "fusion-v1", "tools": []},
    {"protocol_profile": "mcp-v1", "tools": []},
])
async def test_agent_register_route_rejects_malformed_profile_combinations(body):
    transport = httpx2.ASGITransport(app=app_with("secret"))
    async with httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.post(
            "/mcp/desktop-nodes/desk/register",
            headers={"Authorization": "Bearer secret"}, json=body,
        )
        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_ARGUMENT"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["register", "heartbeat"])
@pytest.mark.parametrize(
    "telemetry",
    [
        ["not", "an", "object"],
        {"result_delivery_degraded": "yes", "result_outbox_count": 1},
        {"result_delivery_degraded": False, "result_outbox_count": 10001},
    ],
)
async def test_agent_routes_bound_malformed_telemetry_as_invalid_argument(
    operation, telemetry,
):
    transport = httpx2.ASGITransport(
        app=app_with("secret"), raise_app_exceptions=False,
    )
    headers = {"Authorization": "Bearer secret"}
    async with httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        if operation == "heartbeat":
            registered = await client.post(
                "/mcp/desktop-nodes/desk/register", headers=headers,
                json={"fusion_available": True, "tools": [{"name": "ping"}]},
            )
            assert registered.status_code == 200
        response = await client.post(
            f"/mcp/desktop-nodes/desk/{operation}", headers=headers,
            json={"fusion_available": True, "tools": [{"name": "ping"}], "telemetry": telemetry},
        )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_agent_routes_are_hidden_without_token():
    transport = httpx2.ASGITransport(app=app_with())
    async with httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        assert (await client.post("/mcp/desktop-nodes/desk/register", json={})).status_code == 404
        assert (await client.post("/mcp/desktop-nodes/desk/operator/status", json={})).status_code == 404


@pytest.mark.asyncio
async def test_operator_routes_allow_localhost_and_deny_remote_clients():
    app = app_with("secret")
    headers = {"Authorization": "Bearer secret"}
    local_transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=local_transport, base_url="http://127.0.0.1") as client:
        await client.post("/mcp/desktop-nodes/desk/register", headers=headers, json={"fusion_available": True, "tools": [{"name": "ping"}]})
        status = await client.post("/mcp/desktop-nodes/desk/operator/status", headers=headers)
        assert status.status_code == 200
        assert status.json()["node_id"] == "desk"
        tools = await client.post("/mcp/desktop-nodes/desk/operator/tools", headers=headers)
        assert tools.status_code == 200
        assert tools.json()["tools"] == [{"name": "ping"}]

    remote_transport = httpx2.ASGITransport(app=app, client=("192.0.2.10", 1234))
    async with httpx2.AsyncClient(transport=remote_transport, base_url="http://bridge") as client:
        denied = await client.post("/mcp/desktop-nodes/desk/operator/status", headers=headers)
        assert denied.status_code == 403


@pytest.mark.asyncio
async def test_operator_call_roundtrip_with_fake_agent():
    app = app_with("secret")
    headers = {"Authorization": "Bearer secret"}
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        await client.post("/mcp/desktop-nodes/desk/register", headers=headers, json={"fusion_available": True, "tools": [{"name": "ping"}]})
        operator_call = asyncio.create_task(client.post(
            "/mcp/desktop-nodes/desk/operator/call",
            headers=headers,
            json={"tool_name": "ping", "arguments": {"value": 7}},
        ))
        claimed = await client.post("/mcp/desktop-nodes/desk/claim?wait=1", headers=headers)
        command = claimed.json()["command"]
        assert command["tool_name"] == "ping"
        assert command["arguments"] == {"value": 7}
        submitted = await client.post(
            "/mcp/desktop-nodes/desk/result",
            headers=headers,
            json={"command_id": command["command_id"], "result": {"ok": True}},
        )
        assert submitted.status_code == 200
        response = await operator_call
        assert response.status_code == 200
        assert response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_operator_call_preserves_unicode_arguments_and_result():
    app = app_with("secret")
    headers = {"Authorization": "Bearer secret"}
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        await client.post(
            "/mcp/desktop-nodes/desk/register",
            headers=headers,
            json={"fusion_available": True, "tools": [{"name": "fusion_mcp_execute"}]},
        )
        arguments = {
            "script": "print('Привет, Fusion — расписание пыток 😈')",
            "label": "РАСПИСАНИЕ ПЫТОК",
        }
        operator_call = asyncio.create_task(client.post(
            "/mcp/desktop-nodes/desk/operator/call",
            headers=headers,
            json={"tool_name": "fusion_mcp_execute", "arguments": arguments},
        ))
        claimed = await client.post("/mcp/desktop-nodes/desk/claim?wait=1", headers=headers)
        command = claimed.json()["command"]
        assert command["arguments"] == arguments

        result = {
            "content": [{"type": "text", "text": "Готово: кириллица не повреждена ✅"}],
            "isError": False,
        }
        await client.post(
            "/mcp/desktop-nodes/desk/result",
            headers=headers,
            json={"command_id": command["command_id"], "result": result},
        )
        response = await operator_call
        assert response.status_code == 200
        assert response.json() == result
