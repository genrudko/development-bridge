from __future__ import annotations

import json

import httpx2
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.container import build_container
from app.runtime import create_server
from app.settings import BridgeSettings, load_settings
from app.tools.coordinator import COORDINATOR_UI_URI, COORDINATOR_UI_URIS
from app.transport import create_streamable_http_app


@pytest.mark.asyncio
async def test_resource_mount_routing_and_internal_continue(tmp_path):
    settings = BridgeSettings.model_validate(
        {
            "server": {"public_base_url": "https://bridge.example"},
            "coordinator": {"route_registry_path": tmp_path / "routes.json"},
        }
    )
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
                    resources = await session.list_resources()
                    assert [str(item.uri) for item in resources.resources] == list(COORDINATOR_UI_URIS)
                    resource = await session.read_resource(COORDINATOR_UI_URI)
                    assert "app.sendMessage" in resource.contents[0].text
                    assert "app.sendSizeChanged" in resource.contents[0].text
                    assert "Bridge" in resource.contents[0].text
                    assert "Готов" in resource.contents[0].text
                    assert "Coordinator: ${channelId}" not in resource.contents[0].text
                    assert 'new URL("https://bridge.example/mcp/x/coordinator/"' in resource.contents[0].text
                    assert "if (!ackResponse.ok)" in resource.contents[0].text
                    assert "### ⚡ Bridge · задача завершена" in resource.contents[0].text
                    assert "app.updateModelContext" in resource.contents[0].text
                    assert "<!-- development-bridge" not in resource.contents[0].text
                    assert "payload_json=" in resource.contents[0].text
                    assert "batched_messages" in resource.contents[0].text
                    assert "call coordinator_ack" in resource.contents[0].text
                    assert "Bridge ref:" in resource.contents[0].text
                    assert "development-bridge/control-v1" in resource.contents[0].text
                    assert "development-bridge/control-ack-v1" in resource.contents[0].text
                    assert "handledControlOperations" in resource.contents[0].text
                    assert "CONTROL_OPS_KEY" in resource.contents[0].text
                    assert "localStorage.setItem" in resource.contents[0].text
                    assert "__developmentBridgeControlV1" in resource.contents[0].text
                    legacy = await session.read_resource(COORDINATOR_UI_URIS[1])
                    assert str(legacy.contents[0].uri) == COORDINATOR_UI_URIS[1]
                    assert legacy.contents[0].text == resource.contents[0].text
                    mounted = await session.call_tool(
                        "coordinator_x_mount", {"channel_id": "chat-42"}
                    )
                    assert mounted.meta["ui"]["resourceUri"] == COORDINATOR_UI_URI
                    assert mounted.meta["ui/resourceUri"] == COORDINATOR_UI_URI
                    assert mounted.meta["openai/outputTemplate"] == COORDINATOR_UI_URI
                    assert mounted.structured_content == {
                        "channel_id": "chat-42",
                        "trigger_url": "https://bridge.example/mcp/x/coordinator/",
                    }
                    armed = await container.coordinator.arm_resilient(
                        "compat", channel_id="chat-42", delay_seconds=0
                    )
                    compat = await session.call_tool(
                        "coordinator_x_mount", {"channel_id": armed["continuation_id"]}
                    )
                    assert json.loads(compat.content[0].text)["data"]["acknowledged"] is True
                    continued = await session.call_tool(
                        "coordinator_continue",
                        {"channel_id": "chat-42", "message": "resume", "delay_seconds": 0},
                    )
                    assert json.loads(continued.content[0].text)["data"]["state"] == "pending"
                    listed = await session.list_tools()
                    mount_tool = next(tool for tool in listed.tools if tool.name == "coordinator_x_mount")
                    assert mount_tool.meta["ui"]["resourceUri"] == COORDINATOR_UI_URI
                    assert mount_tool.meta["ui/resourceUri"] == COORDINATOR_UI_URI
                    assert mount_tool.meta["openai/outputTemplate"] == COORDINATOR_UI_URI
                    continue_tool = next(
                        tool for tool in listed.tools if tool.name == "coordinator_continue"
                    )
                    assert continue_tool.input_schema["required"] == ["message"]
            status = await client.get("/mcp/x/coordinator/status?channel_id=chat-42")
            assert status.headers["access-control-allow-origin"] == "*"
            claim = await client.post("/mcp/x/coordinator/claim?channel_id=chat-42")
            assert claim.headers["access-control-allow-origin"] == "*"
            assert claim.json()["message"] == "resume"
            assert (
                await container.coordinator.ack("chat-42", claim.json()["claim_id"])
            )["acknowledged"] is True
            container.coordinator._global_cooldown_until = 0
            container.coordinator._cooldown_until["chat-42"] = 0
            resilient = await container.coordinator.arm_resilient(
                "observed", channel_id="observed-42", delay_seconds=0
            )
            preflight_status = await client.get(
                "/mcp/x/coordinator/status?channel_id=observed-42"
            )
            assert preflight_status.json()["state"] == "browser_preflight"
            assert (
                await client.post("/mcp/x/coordinator/claim?channel_id=observed-42")
            ).json()["claimed"] is False
            authorized = await client.post(
                "/mcp/x/coordinator/preflight/authorize",
                params={
                    "channel_id": "observed-42",
                    "continuation_id": resilient["continuation_id"],
                },
            )
            assert authorized.status_code == 200
            assert authorized.json()["authorized"] is True
            observed_claim = await client.post(
                "/mcp/x/coordinator/claim?channel_id=observed-42"
            )
            transport = await client.post(
                "/mcp/x/coordinator/ack",
                params={
                    "channel_id": "observed-42",
                    "claim_id": observed_claim.json()["claim_id"],
                },
            )
            assert transport.json()["transport_delivered"] is True
            observed = await client.post(
                "/mcp/x/coordinator/observed",
                params={
                    "channel_id": "observed-42",
                    "continuation_id": resilient["continuation_id"],
                },
            )
            assert observed.headers["access-control-allow-origin"] == "*"
            assert observed.json()["observed"] is True


@pytest.mark.asyncio
async def test_external_trigger_is_unavailable_unset_and_token_protected(tmp_path):
    unset = build_container(BridgeSettings.model_validate({"coordinator": {"route_registry_path": tmp_path / "unset-routes.json"}}))
    unset_app = create_streamable_http_app(create_server(unset), unset.settings, unset)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=unset_app), base_url="http://127.0.0.1"
    ) as client:
        assert (await client.post("/mcp/x/coordinator/trigger", json={"message": "x"})).status_code == 404

    settings = load_settings(environ={"DEVELOPMENT_BRIDGE_X_TRIGGER_TOKEN": "secret", "DEVELOPMENT_BRIDGE_ROUTE_REGISTRY_PATH": str(tmp_path / "routes.json")})
    container = build_container(settings)
    app = create_streamable_http_app(create_server(container), settings, container)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        assert (await client.post("/mcp/x/coordinator/trigger", json={"message": "x"})).status_code == 401
        missing_message = await client.post(
            "/mcp/x/coordinator/trigger",
            headers={"X-Development-Bridge-Trigger-Token": "secret"},
            json={"channel_id": "external"},
        )
        assert missing_message.status_code == 400
        armed = await client.post(
            "/mcp/x/coordinator/trigger",
            headers={"Authorization": "Bearer secret"},
            json={"channel_id": "external", "message": "wake", "delay": 0},
        )
        assert armed.status_code == 202
        assert (await client.post("/mcp/x/coordinator/claim?channel_id=external")).json()["message"] == "wake"


@pytest.mark.asyncio
async def test_rollover_control_keeps_active_route_until_commit(tmp_path):
    settings = BridgeSettings.model_validate(
        {"coordinator": {"route_registry_path": tmp_path / "routes.json"}}
    )
    container = build_container(settings)
    container.route_registry.bootstrap(
        "ad5x", "https://chatgpt.com/g/g-p-project/c/conv-a",
        "telegram-ad5x-g5",
    )
    prepared = container.route_registry.prepare_rollover("ad5x")
    app = create_streamable_http_app(create_server(container), settings, container)
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            candidate = await client.post(
                "/mcp/x/coordinator/rollover/candidate",
                json={
                    "route_id": "ad5x", "token": prepared["token"],
                    "url": "https://chatgpt.com/g/g-p-project/c/conv-b",
                },
            )
            assert candidate.status_code == 200
            assert candidate.json()["state"] == "candidate"
            assert container.route_registry.resolve("ad5x")["conversation_id"] == "conv-a"
            committed = await client.post(
                "/mcp/x/coordinator/rollover/commit",
                json={"route_id": "ad5x", "token": prepared["token"]},
            )
            assert committed.status_code == 200
            assert committed.json()["conversation_id"] == "conv-b"
            assert container.route_registry.resolve("ad5x")["conversation_id"] == "conv-b"
