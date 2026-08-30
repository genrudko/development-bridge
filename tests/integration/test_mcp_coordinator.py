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

@pytest.mark.asyncio
async def test_compact_dashboard_live_state_resource(tmp_path):
    from app.tools.compact import BRIDGE_DASHBOARD_STATE_URI, BRIDGE_DASHBOARD_UI_URI

    settings = BridgeSettings.model_validate({
        "server": {"tool_surface": "compact"},
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "ad5x",
        "https://chatgpt.com/c/00000000-0000-0000-0000-000000000001",
        "telegram-ad5x-g1",
        "AD5X",
    )
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
                    uris = {str(item.uri) for item in resources.resources}
                    assert BRIDGE_DASHBOARD_UI_URI in uris
                    assert BRIDGE_DASHBOARD_STATE_URI in uris

                    listed = await session.list_tools()
                    names = {tool.name for tool in listed.tools}
                    assert len(names) == 14
                    assert "work_progress_update" not in names

                    mounted = await session.call_tool("coordinator_x_mount", {"route_id": "ad5x"})
                    assert mounted.structured_content["route_id"] == "ad5x"
                    updated = await session.call_tool("bridge_call", {
                        "tool_name": "work_progress_update",
                        "arguments": {
                            "title": "Live dashboard",
                            "total": 5,
                            "completed": 2,
                            "status": "working",
                            "current": "Integration test",
                        },
                    })
                    assert json.loads(updated.content[0].text)["ok"] is True

                    state = await session.read_resource(BRIDGE_DASHBOARD_STATE_URI)
                    payload = json.loads(state.contents[0].text)
                    assert payload["progress"]["title"] == "Live dashboard"
                    assert payload["progress"]["percent"] == 40

                    ui = await session.read_resource(BRIDGE_DASHBOARD_UI_URI)
                    assert "readServerResource" in ui.contents[0].text
                    assert BRIDGE_DASHBOARD_STATE_URI in ui.contents[0].text

@pytest.mark.asyncio
async def test_coordinator_session_binding_prevents_cross_chat_defaults(tmp_path):
    settings = BridgeSettings.model_validate({
        "server": {"tool_surface": "compact"},
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "ad5x",
        "https://chatgpt.com/c/00000000-0000-0000-0000-000000000011",
        "telegram-ad5x-g1",
        "AD5X",
    )
    container.route_registry.bootstrap(
        "eod",
        "https://chatgpt.com/c/00000000-0000-0000-0000-000000000022",
        "telegram-eod-g1",
        "EOD",
    )
    app = create_streamable_http_app(create_server(container), settings, container)
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            async def mount_and_continue(route_id, message):
                async with streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams:
                    async with ClientSession(*streams) as session:
                        await session.initialize()
                        mounted = await session.call_tool("coordinator_x_mount", {"route_id": route_id})
                        assert mounted.structured_content["route_id"] == route_id
                        continued = await session.call_tool("bridge_call", {
                            "tool_name": "coordinator_continue",
                            "arguments": {"message": message, "delay_seconds": 0},
                        })
                        return json.loads(continued.content[0].text)["data"]

            ad5x, eod = await __import__('asyncio').gather(
                mount_and_continue("ad5x", "A"), mount_and_continue("eod", "B")
            )
            assert ad5x["channel_id"] == "telegram-ad5x-g1"
            assert eod["channel_id"] == "telegram-eod-g1"
            assert container.coordinator._pending["telegram-ad5x-g1"].message == "A"
            assert container.coordinator._pending["telegram-eod-g1"].message == "B"


@pytest.mark.asyncio
async def test_unbound_session_coordinator_continue_fails_closed(tmp_path):
    settings = BridgeSettings.model_validate({
        "server": {"tool_surface": "compact"},
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "ad5x",
        "https://chatgpt.com/c/00000000-0000-0000-0000-000000000033",
        "telegram-ad5x-g1",
        "AD5X",
    )
    app = create_streamable_http_app(create_server(container), settings, container)
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            async with streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    result = await session.call_tool("bridge_call", {
                        "tool_name": "coordinator_continue",
                        "arguments": {"message": "must not leak", "delay_seconds": 0},
                    })
                    payload = json.loads(result.content[0].text)
                    assert payload["ok"] is False
                    assert payload["error"]["code"] == "POLICY_VIOLATION"
                    assert (await container.coordinator.status("telegram-ad5x-g1"))["state"] == "idle"

@pytest.mark.asyncio
async def test_durable_route_waiter_follows_current_generation_at_delivery(tmp_path):
    from app.jobs.models import JobRecord, JobStatus

    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "ad5x",
        "https://chatgpt.com/c/00000000-0000-0000-0000-000000000041",
        "telegram-ad5x-g0",
        "AD5X",
    )
    pending = container.route_registry.prepare_rollover("ad5x")
    container.route_registry.record_rollover_candidate(
        "ad5x",
        pending["token"],
        "https://chatgpt.com/c/00000000-0000-0000-0000-000000000042",
    )
    committed = container.route_registry.commit_rollover("ad5x", pending["token"])
    assert committed["channel_id"] == "telegram-ad5x-g1"

    job = JobRecord(
        job_id="job_00000000000000000000000000000001",
        project_id="development-bridge",
        repository_id="development-bridge",
        task_id="test",
        request_id="req_test",
        status=JobStatus.SUCCEEDED,
        created_at="2026-08-30T00:00:00+00:00",
    )
    handler = container.jobs._durable_terminal_handlers["coordinator"]
    await handler({"route_id": "ad5x", "message": "done"}, (job,), "all_terminal")
    assert "telegram-ad5x-g0" not in container.coordinator._pending
    assert "telegram-ad5x-g1" in container.coordinator._pending
    assert "message=done" in container.coordinator._pending["telegram-ad5x-g1"].message


@pytest.mark.asyncio
async def test_stale_physical_session_cannot_implicitly_wake_successor(tmp_path):
    settings = BridgeSettings.model_validate({
        "server": {"tool_surface": "compact"},
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "ad5x",
        "https://chatgpt.com/c/00000000-0000-0000-0000-000000000051",
        "telegram-ad5x-g0",
        "AD5X",
    )
    app = create_streamable_http_app(create_server(container), settings, container)
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            async with streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    mounted = await session.call_tool("coordinator_x_mount", {"route_id": "ad5x"})
                    assert mounted.structured_content["generation"] == 0

                    pending = container.route_registry.prepare_rollover("ad5x")
                    container.route_registry.record_rollover_candidate(
                        "ad5x", pending["token"],
                        "https://chatgpt.com/c/00000000-0000-0000-0000-000000000052",
                    )
                    committed = container.route_registry.commit_rollover("ad5x", pending["token"])
                    assert committed["generation"] == 1

                    result = await session.call_tool("bridge_call", {
                        "tool_name": "coordinator_continue",
                        "arguments": {"message": "must stay in old chat", "delay_seconds": 0},
                    })
                    payload = json.loads(result.content[0].text)
                    assert payload["ok"] is False
                    assert payload["error"]["code"] == "POLICY_VIOLATION"
                    assert "stale route generation" in payload["error"]["message"]
                    assert (await container.coordinator.status("telegram-ad5x-g0"))["state"] == "idle"
                    assert (await container.coordinator.status("telegram-ad5x-g1"))["state"] == "idle"
