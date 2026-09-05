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
                    assert "route_control" in resource.contents[0].text
                    assert "openExternal" in resource.contents[0].text
                    assert "DBRIDGE_ROUTE_BIND_" not in resource.contents[0].text
                    assert 'request("discover"' not in resource.contents[0].text
                    assert "openLink" not in resource.contents[0].text
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
                    assert "observerOnly" in resource.contents[0].text
                    assert "control_version: 2" in resource.contents[0].text
                    legacy = await session.read_resource(COORDINATOR_UI_URIS[1])
                    assert str(legacy.contents[0].uri) == COORDINATOR_UI_URIS[1]
                    assert legacy.contents[0].text == resource.contents[0].text
                    mounted = await session.call_tool(
                        "coordinator_x_mount", {"channel_id": "chat-42"}
                    )
                    assert mounted.meta["ui"]["resourceUri"] == COORDINATOR_UI_URI
                    assert mounted.meta["ui/resourceUri"] == COORDINATOR_UI_URI
                    assert mounted.meta["openai/outputTemplate"] == COORDINATOR_UI_URI
                    assert mounted.structured_content["channel_id"] == "chat-42"
                    assert mounted.structured_content["trigger_url"] == "https://bridge.example/mcp/x/coordinator/"
                    delivery_lease = mounted.structured_content["delivery_lease"]
                    assert isinstance(delivery_lease, str) and len(delivery_lease) >= 10
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
            status = await client.get(f"/mcp/x/coordinator/status?channel_id=chat-42&delivery_lease={delivery_lease}")
            assert status.headers["access-control-allow-origin"] == "*"
            claim = await client.post(f"/mcp/x/coordinator/claim?channel_id=chat-42&delivery_lease={delivery_lease}")
            assert claim.headers["access-control-allow-origin"] == "*"
            assert claim.json()["message"] == "resume"
            assert (
                await container.coordinator.ack(
                    "chat-42", claim.json()["claim_id"], delivery_lease=delivery_lease
                )
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
async def test_external_trigger_rejects_unbound_route_channel(tmp_path):
    settings = load_settings(environ={
        "DEVELOPMENT_BRIDGE_X_TRIGGER_TOKEN": "secret",
        "DEVELOPMENT_BRIDGE_ROUTE_REGISTRY_PATH": str(tmp_path / "routes.json"),
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-current",
        "telegram-bridge-g0",
    )
    container.route_registry.unbind("bridge", expected_generation=0)
    app = create_streamable_http_app(create_server(container), settings, container)

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.post(
            "/mcp/x/coordinator/trigger",
            headers={"Authorization": "Bearer secret"},
            json={"channel_id": "telegram-bridge-g0", "message": "stale wake"},
        )

    assert response.status_code == 409
    assert (await container.coordinator.status("telegram-bridge-g0"))["state"] == "idle"


@pytest.mark.asyncio
async def test_external_trigger_rejects_registered_pending_route_channel(tmp_path):
    settings = load_settings(environ={
        "DEVELOPMENT_BRIDGE_X_TRIGGER_TOKEN": "secret",
        "DEVELOPMENT_BRIDGE_ROUTE_REGISTRY_PATH": str(tmp_path / "routes.json"),
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-current",
        "telegram-bridge-g0",
    )
    pending = container.route_registry.prepare_rollover("bridge")
    app = create_streamable_http_app(create_server(container), settings, container)

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.post(
            "/mcp/x/coordinator/trigger",
            headers={"Authorization": "Bearer secret"},
            json={"channel_id": pending["channel_id"], "message": "premature wake"},
        )

    assert response.status_code == 409
    assert (await container.coordinator.status(pending["channel_id"]))["state"] == "idle"


@pytest.mark.asyncio
async def test_external_trigger_arms_route_channel_under_route_lock(tmp_path):
    settings = load_settings(environ={
        "DEVELOPMENT_BRIDGE_X_TRIGGER_TOKEN": "secret",
        "DEVELOPMENT_BRIDGE_ROUTE_REGISTRY_PATH": str(tmp_path / "routes.json"),
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-current",
        "telegram-bridge-g0",
    )
    route_lock = container.route_registry.route_lock("bridge")
    original_arm = container.coordinator.arm
    lock_observations = []

    async def observe_lock(*args, **kwargs):
        lock_observations.append(route_lock.locked())
        return await original_arm(*args, **kwargs)

    container.coordinator.arm = observe_lock
    app = create_streamable_http_app(create_server(container), settings, container)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.post(
            "/mcp/x/coordinator/trigger",
            headers={"Authorization": "Bearer secret"},
            json={"channel_id": "telegram-bridge-g0", "message": "current wake"},
        )

    assert response.status_code == 202
    assert lock_observations == [True]


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
    route_lock = container.route_registry.route_lock("ad5x")
    lock_observations = []
    original_candidate = container.route_registry.record_rollover_candidate
    original_commit = container.route_registry.commit_rollover

    def observe_candidate(*args, **kwargs):
        lock_observations.append(("candidate", route_lock.locked()))
        return original_candidate(*args, **kwargs)

    def observe_commit(*args, **kwargs):
        lock_observations.append(("commit", route_lock.locked()))
        return original_commit(*args, **kwargs)

    container.route_registry.record_rollover_candidate = observe_candidate
    container.route_registry.commit_rollover = observe_commit
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
    assert lock_observations == [("candidate", True), ("commit", True)]

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
                    assert len(names) == 15
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
    # Legacy unpinned payload (missing generation and channel_id) must be a safe no-op
    await handler({"route_id": "ad5x", "message": "done"}, (job,), "all_terminal")
    assert "telegram-ad5x-g0" not in container.coordinator._pending
    assert "telegram-ad5x-g1" not in container.coordinator._pending
    assert container.coordinator._pending == {}


@pytest.mark.asyncio
async def test_durable_legacy_waiter_rejects_registered_pending_route_channel(tmp_path):
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
    job = JobRecord(
        job_id="job_00000000000000000000000000000002",
        project_id="development-bridge",
        repository_id="development-bridge",
        task_id="test",
        request_id="req_test",
        status=JobStatus.SUCCEEDED,
        created_at="2026-08-30T00:00:00+00:00",
    )
    handler = container.jobs._durable_terminal_handlers["coordinator"]

    await handler(
        {"channel_id": pending["channel_id"], "message": "done"},
        (job,),
        "all_terminal",
    )

    assert container.coordinator._pending == {}



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
                    old_delivery_lease = mounted.structured_content["delivery_lease"]

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
                    assert (
                        await container.coordinator.status(
                            "telegram-ad5x-g0", delivery_lease=old_delivery_lease
                        )
                    )["state"] == "idle"
                    assert (await container.coordinator.status("telegram-ad5x-g1"))["state"] == "idle"


@pytest.mark.asyncio
async def test_new_mount_invalidates_old_physical_chat_delivery_lease(tmp_path):
    settings = BridgeSettings.model_validate({
        "server": {"tool_surface": "compact"},
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "ad5x",
        "https://chatgpt.com/c/00000000-0000-0000-0000-000000000061",
        "telegram-ad5x-g0",
        "AD5X",
    )
    app = create_streamable_http_app(create_server(container), settings, container)
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            async def mount_once():
                async with streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams:
                    async with ClientSession(*streams) as session:
                        await session.initialize()
                        result = await session.call_tool("coordinator_x_mount", {"route_id": "ad5x"})
                        return result.structured_content["delivery_lease"]

            old_lease = await mount_once()
            new_lease = await mount_once()
            assert old_lease != new_lease

            await container.coordinator.arm("wake-current-chat", channel_id="telegram-ad5x-g0", delay_seconds=0)
            old = await client.post(
                f"/mcp/x/coordinator/claim?channel_id=telegram-ad5x-g0&delivery_lease={old_lease}"
            )
            assert old.json()["claimed"] is False
            assert old.json()["state"] == "standby"
            legacy = await client.post(
                "/mcp/x/coordinator/claim?channel_id=telegram-ad5x-g0"
            )
            assert legacy.json()["claimed"] is True
            assert (await container.coordinator.ack(
                "telegram-ad5x-g0", legacy.json()["claim_id"]
            ))["acknowledged"] is True
            container.coordinator._global_cooldown_until = 0
            container.coordinator._cooldown_until["telegram-ad5x-g0"] = 0
            await container.coordinator.arm(
                "wake-current-chat-again", channel_id="telegram-ad5x-g0", delay_seconds=0
            )
            current = await client.post(
                f"/mcp/x/coordinator/claim?channel_id=telegram-ad5x-g0&delivery_lease={new_lease}"
            )
            assert current.json()["claimed"] is True


@pytest.mark.asyncio
async def test_current_chat_discovery_endpoint_delegates_to_wake_service(tmp_path):
    settings = BridgeSettings.model_validate({
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/conv-old",
        "telegram-bridge-g4",
    )
    pending = container.route_registry.prepare_current_bind("bridge", session_id="session-1")

    class FakeDiscoveryService:
        async def start(self):
            return None

        async def stop(self):
            return None

        async def discover_and_bind_current_route(self, route_id, token):
            assert route_id == "bridge"
            assert token == pending["token"]
            return {
                "route_id": "bridge",
                "conversation_id": "conv-new",
                "channel_id": "telegram-bridge-g5",
                "generation": 5,
                "changed": True,
            }

    object.__setattr__(container, "coordinator_wake_delivery", FakeDiscoveryService())
    app = create_streamable_http_app(create_server(container), settings, container)
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            response = await client.post(
                "/mcp/x/coordinator/discover",
                json={"route_id": "bridge", "token": pending["token"]},
            )
            assert response.status_code == 200
            assert response.json()["conversation_id"] == "conv-new"
            assert response.headers["access-control-allow-origin"] == "*"
            preflight = await client.options(
                "/mcp/x/coordinator/discover",
                headers={
                    "Origin": "https://chatgpt.com",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            assert preflight.status_code == 204
            assert preflight.headers["access-control-allow-origin"] == "*"
            assert "POST" in preflight.headers["access-control-allow-methods"]
            assert "Content-Type" in preflight.headers["access-control-allow-headers"]


@pytest.mark.asyncio
async def test_bind_current_does_not_prebind_session_to_stale_generation(tmp_path):
    settings = BridgeSettings.model_validate({
        "server": {"public_base_url": "https://bridge.example"},
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/conv-old",
        "telegram-bridge-g4",
    )
    app = create_streamable_http_app(create_server(container), settings, container)
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1") as client,
        streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()
        result = await session.call_tool("coordinator_route_bind_current", {"route_id": "bridge"})
        payload = json.loads(result.content[0].text)["data"]
        assert payload["state"] == "bind_pending"
        assert payload["route_id"] == "bridge"
        assert payload["generation"] == 0
        assert container.coordinator._session_bindings == {}

        # Component-only meta contains the opaque operation url
        route_control = result.meta.get("route_control")
        assert route_control is not None
        assert route_control["action"] == "bind"
        assert route_control["route_id"] == "bridge"
        op_id = route_control["operation_id"]
        assert op_id.startswith("bind_")
        assert route_control["operation_url"] == f"https://bridge.example/mcp/x/route-control/bind/{op_id}"
        assert route_control["diagnostic_id"].startswith("bind-")

        # Structured content and model text are strictly safe
        assert result.structured_content == {
            "route_id": "bridge",
            "state": "bind_pending",
            "generation": 0,
        }
        assert "channel_id" not in result.structured_content
        assert "trigger_url" not in result.structured_content
        assert "delivery_lease" not in result.structured_content
        assert "route_state" not in result.structured_content
        assert "route_discovery" not in result.structured_content
        assert "operation_url" not in result.structured_content
        assert result.meta["ui"]["resourceUri"] == COORDINATOR_UI_URI
        assert result.meta["ui/resourceUri"] == COORDINATOR_UI_URI
        assert result.meta["openai/outputTemplate"] == COORDINATOR_UI_URI
        assert op_id not in result.content[0].text
        assert "conv-old" not in result.content[0].text
        assert route_control["operation_url"] not in result.content[0].text


@pytest.mark.asyncio
async def test_bind_current_preserves_existing_route_delivery_lease(tmp_path):
    settings = BridgeSettings.model_validate({
        "server": {"public_base_url": "https://bridge.example"},
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/conv-old",
        "telegram-bridge-g4",
    )
    app = create_streamable_http_app(create_server(container), settings, container)
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1") as client,
    ):
        # Session 1 mounts the route
        async with (
            streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams1,
            ClientSession(*streams1) as session1,
        ):
            await session1.initialize()
            mounted = await session1.call_tool("coordinator_x_mount", {"route_id": "bridge"})
            lease_1 = mounted.structured_content["delivery_lease"]
            assert lease_1 is not None
            before_lease_record = dict(container.coordinator.delivery_lease("telegram-bridge-g4"))
            assert before_lease_record["lease_id"] == lease_1

            # Session 2 invokes bind_current for the same route
            async with (
                streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams2,
                ClientSession(*streams2) as session2,
            ):
                await session2.initialize()
                bind_result = await session2.call_tool("coordinator_route_bind_current", {"route_id": "bridge"})
                assert bind_result.structured_content == {
                    "route_id": "bridge",
                    "state": "bind_pending",
                    "generation": 0,
                }
                assert "channel_id" not in bind_result.structured_content
                assert "delivery_lease" not in bind_result.structured_content

                # Failed prep from session 2 also does not mutate lease
                failed_bind = await session2.call_tool("coordinator_route_bind_current", {"route_id": "nonexistent"})
                assert failed_bind.is_error is True

            # Delivery lease for telegram-bridge-g4 is unchanged
            after_lease_record = container.coordinator.delivery_lease("telegram-bridge-g4")
            assert after_lease_record == before_lease_record
            assert after_lease_record["lease_id"] == lease_1

            # Session 1's delivery lease is still active and can claim wakes
            status = await client.get(
                f"/mcp/x/coordinator/status?channel_id=telegram-bridge-g4&delivery_lease={lease_1}"
            )
            assert status.json()["state"] == "idle"
            assert "delivery_lease_required" not in status.json()

            await container.coordinator.arm("wake-preserved", channel_id="telegram-bridge-g4", delay_seconds=0)
            claim = await client.post(
                f"/mcp/x/coordinator/claim?channel_id=telegram-bridge-g4&delivery_lease={lease_1}"
            )
            assert claim.json()["claimed"] is True
            assert claim.json()["message"] == "wake-preserved"


@pytest.mark.asyncio
async def test_coordinator_widget_html_contract_and_forbidden_apis(tmp_path):
    settings = BridgeSettings.model_validate({
        "server": {"public_base_url": "https://bridge.example"},
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
    })
    container = build_container(settings)
    app = create_streamable_http_app(create_server(container), settings, container)
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1") as client,
        streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()
        resource = await session.read_resource(COORDINATOR_UI_URI)
        html = resource.contents[0].text

        # Out-of-band openExternal must be present
        assert "window.openai?.openExternal" in html or "window.openai.openExternal" in html
        assert "window.openai.openExternal({ href: operationUrl, redirectUrl: true })" in html
        assert "actionBtn.onclick" in html
        assert "handleRouteControl" in html

        # Missing host API guard
        assert "openExternal недоступен" in html or "Не поддерживается" in html

        # Forbidden APIs / fallback mechanisms
        assert "openLink" not in html
        assert "DBRIDGE_ROUTE_BIND_" not in html
        assert 'request("discover"' not in html

        # Wake delivery messaging is preserved
        assert "### ⚡ Bridge · задача завершена" in html
        assert "app.sendMessage" in html
        assert "app.updateModelContext" in html

        # Safe widget route-control status and actions
        assert "route-controls" in html
        assert "rc-status" in html
        assert "rc-cancel-wake" in html
        assert "rc-unbind" in html
        assert "rc-unbind-cancel" in html
        assert "confirmDestructiveAction" in html
        assert "Authorization" in html and "Bearer" in html
        assert "refreshRouteControlStatus" in html
        assert "applySafeStatus" in html

        failure_branch = html.split("if (!resp.ok) {", 1)[1].split("\n    }\n    if (data.safe_status)", 1)[0]
        assert "if (data.safe_status)" in failure_branch
        assert "applySafeStatus(data.safe_status, errorMessage)" in failure_branch
        assert "await refreshRouteControlStatus(errorMessage)" in failure_branch
        assert failure_branch.index("applySafeStatus(data.safe_status, errorMessage)") < failure_branch.rindex("return;")


@pytest.mark.asyncio
async def test_coordinator_route_control_status_hidden_tool(tmp_path):
    settings = BridgeSettings.model_validate(
        {
            "server": {"public_base_url": "https://bridge.example"},
            "coordinator": {"route_registry_path": tmp_path / "routes.json"},
            "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
        }
    )
    container = build_container(settings)
    if container.jobs and container.jobs.store:
        container.jobs.store.initialize()
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-old",
        "telegram-bridge-g0",
        "Development Bridge Infra",
    )
    app = create_streamable_http_app(create_server(container), settings, container)

    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1") as client,
        streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()
        result = await session.call_tool("coordinator_route_control_status", {"route_id": "bridge"})
        data = json.loads(result.content[0].text)["data"]
        assert data["route_id"] == "bridge"
        assert data["state"] == "bound"
        assert data["generation"] == 0
        assert data["pending_coordinator_wakes"] == 0
        assert data["pending_durable_waiters"] == 0

        # Structured content matches safe data
        assert result.structured_content == data

        # Component-only meta contains control authorization
        rc = result.meta.get("route_control")
        assert rc is not None
        assert rc["route_id"] == "bridge"
        assert "control_token" in rc
        assert "endpoints" in rc
        assert rc["endpoints"]["status"] == "https://bridge.example/mcp/x/route-control/status"
        assert rc["endpoints"]["unbind"] == "https://bridge.example/mcp/x/route-control/unbind"
        assert rc["endpoints"]["cancel_wakes"] == "https://bridge.example/mcp/x/route-control/cancel-wakes"
        assert rc["endpoints"]["unbind_and_cancel"] == "https://bridge.example/mcp/x/route-control/unbind-and-cancel"

        # Model text and structured content must NOT leak physical target or control token
        text = result.content[0].text
        assert "conv-old" not in text
        assert "g-p-infra" not in text
        assert "https://chatgpt.com" not in text
        assert rc["control_token"] not in text


@pytest.mark.asyncio
async def test_coordinator_route_control_diagnostic_hidden_tool(tmp_path):
    settings = BridgeSettings.model_validate(
        {
            "server": {"public_base_url": "https://bridge.example"},
            "coordinator": {"route_registry_path": tmp_path / "routes.json"},
        }
    )
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-old",
        "telegram-bridge-g0",
        "Development Bridge Infra",
    )
    app = create_streamable_http_app(create_server(container), settings, container)

    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1") as client,
        streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()

        # Prepare a bind to generate a diagnostic trace
        bind_res = await session.call_tool("coordinator_route_bind_current", {"route_id": "bridge"})
        diag_id = bind_res.meta["route_control"]["diagnostic_id"]

        # Call diagnostic tool
        diag_res = await session.call_tool(
            "coordinator_route_control_diagnostic", {"diagnostic_id": diag_id}
        )
        data = json.loads(diag_res.content[0].text)["data"]
        assert data["diagnostic_id"] == diag_id
        assert data["operation_type"] == "bind"
        assert "stages" in data

        # Sanitized trace must NOT leak physical target or tokens
        text = diag_res.content[0].text
        assert "conv-old" not in text
        assert "g-p-infra" not in text
        assert "https://chatgpt.com" not in text

        # Non-existent diagnostic returns error
        failed_diag = await session.call_tool(
            "coordinator_route_control_diagnostic", {"diagnostic_id": "diag-non-existent-999"}
        )
        assert failed_diag.is_error is True
        assert "not found" in failed_diag.content[0].text.lower()


@pytest.mark.asyncio
async def test_coordinator_route_list_sanitization(tmp_path):
    settings = BridgeSettings.model_validate(
        {
            "server": {"public_base_url": "https://bridge.example"},
            "coordinator": {"route_registry_path": tmp_path / "routes.json"},
        }
    )
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-bridge",
        "telegram-bridge-g0",
        "Development Bridge Infra",
    )
    container.route_registry.bootstrap(
        "ad5xwork",
        "https://chatgpt.com/g/g-p-ad5x/c/conv-ad5x",
        "telegram-ad5xwork-g0",
        "AD5X Work",
    )
    app = create_streamable_http_app(create_server(container), settings, container)

    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1") as client,
        streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()
        res = await session.call_tool("coordinator_route_list", {})
        data = json.loads(res.content[0].text)["data"]
        routes = {r["route_id"]: r for r in data["routes"]}

        assert "bridge" in routes
        assert routes["bridge"]["binding_state"] == "bound"
        assert routes["bridge"]["generation"] == 0
        assert "project_id" not in routes["bridge"]

        assert "ad5xwork" in routes
        assert routes["ad5xwork"]["binding_state"] == "bound"
        assert routes["ad5xwork"]["generation"] == 0
        assert "project_id" not in routes["ad5xwork"]

        # No project/GPT physical identifiers in output text
        text = res.content[0].text
        assert "g-p-infra" not in text
        assert "g-p-ad5x" not in text
        assert "conv-bridge" not in text
        assert "conv-ad5x" not in text


@pytest.mark.asyncio
async def test_resolve_destination_rejects_unbound_routes(tmp_path):
    settings = BridgeSettings.model_validate(
        {
            "server": {"public_base_url": "https://bridge.example"},
            "coordinator": {"route_registry_path": tmp_path / "routes.json"},
        }
    )
    container = build_container(settings)
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-bridge",
        "telegram-bridge-g0",
        "Development Bridge Infra",
    )
    # Explicitly unbind route
    container.route_registry.unbind("bridge", expected_generation=0)

    app = create_streamable_http_app(create_server(container), settings, container)

    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1") as client,
        streamable_http_client("http://127.0.0.1/mcp", http_client=client) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()

        # coordinator_x_mount must reject unbound route
        res1 = await session.call_tool("coordinator_x_mount", {"route_id": "bridge"})
        assert res1.is_error is True
        assert "unbound" in res1.content[0].text.lower()

        # coordinator_continue must reject unbound route
        res2 = await session.call_tool("coordinator_continue", {"route_id": "bridge", "message": "hello"})
        assert res2.is_error is True
        assert "unbound" in res2.content[0].text.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("unbind_first", [True, False])
async def test_rollover_bootstrap_delivery_serializes_with_unbind(tmp_path, unbind_first):
    import asyncio
    from dataclasses import replace

    from app.coordinator.wake_delivery import CoordinatorWakeDeliveryService
    from app.coordinator.wake_transport import WakeDeliveryResult, WakeProbeResult

    settings = BridgeSettings.model_validate({"coordinator": {"route_registry_path": tmp_path / "routes.json"}})
    container = build_container(settings)
    routes = container.route_registry
    routes.bootstrap("bridge", "https://chatgpt.com/g/g-p-infra/c/old", "telegram-bridge-g0")
    pending = routes.prepare_rollover("bridge")
    routes.record_rollover_candidate("bridge", pending["token"], "https://chatgpt.com/g/g-p-infra/c/new")
    routes.commit_rollover("bridge", pending["token"])
    entered, release = asyncio.Event(), asyncio.Event()
    sent = []
    class Transport:
        name = "test"
        async def probe(self, target):
            entered.set()
            await release.wait()
            return WakeProbeResult(ready=True)
        async def deliver(self, request):
            sent.append(request)
            return WakeDeliveryResult(disposition="delivered")
    delivery = CoordinatorWakeDeliveryService(container.coordinator, routes, transport=Transport(), enabled=True)
    container = replace(container, coordinator_wake_delivery=delivery)
    app = create_streamable_http_app(create_server(container), settings, container)
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test") as client:
        async def bootstrap():
            return await client.post("/mcp/x/coordinator/rollover/bootstrap", json={"route_id": "bridge", "token": pending["token"]})
        if unbind_first:
            async with routes.route_lock("bridge"):
                task = asyncio.create_task(bootstrap())
                await asyncio.sleep(0)
                routes.unbind("bridge", expected_generation=1)
            response = await task
            assert response.status_code in {400, 409}
            assert sent == []
            assert routes._load()["last_rollover"]["bridge"]["bootstrap_sent"] is False
        else:
            task = asyncio.create_task(bootstrap())
            # A bounded event wait also reports an unsupported endpoint without hanging.
            probe = asyncio.create_task(entered.wait())
            done, _ = await asyncio.wait({task, probe}, return_when=asyncio.FIRST_COMPLETED)
            if task in done:
                probe.cancel()
                response = await task
                assert response.status_code == 200, response.text
            async def unbind():
                async with routes.route_lock("bridge"):
                    routes.unbind("bridge", expected_generation=1)
            mutation = asyncio.create_task(unbind())
            await asyncio.sleep(0)
            blocked = not mutation.done()
            release.set()
            response = await task
            await mutation
            await probe
            assert blocked
            assert response.status_code == 200
            assert response.json()["state"] == "complete"
            assert len(sent) == 1
            assert "coordinator_route_context_get" in sent[0].prompt
            assert pending["token"] not in sent[0].prompt
            assert pending["token"] not in sent[0].continuation_id
            assert sent[0].target.channel_id == "telegram-bridge-g1"
            assert routes._load()["last_rollover"]["bridge"]["bootstrap_sent"] is True


@pytest.mark.asyncio
async def test_browser_host_commit_requires_server_bootstrap_transport_before_mutation(tmp_path):
    settings = BridgeSettings.model_validate({"coordinator": {"route_registry_path": tmp_path / "routes.json"}})
    container = build_container(settings)
    routes = container.route_registry
    routes.bootstrap("bridge", "https://chatgpt.com/g/g-p-infra/c/old", "telegram-bridge-g0")
    pending = routes.prepare_rollover("bridge")
    routes.record_rollover_candidate("bridge", pending["token"], "https://chatgpt.com/g/g-p-infra/c/new")
    app = create_streamable_http_app(create_server(container), settings, container)
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/mcp/x/coordinator/rollover/commit", json={
            "route_id": "bridge", "token": pending["token"], "require_bootstrap_transport": True,
        })
        assert response.status_code == 409
        assert routes.resolve("bridge")["generation"] == 0
        assert routes.resolve("bridge")["conversation_id"] == "old"
        aborted = await client.post("/mcp/x/coordinator/rollover/abort", json={"route_id": "bridge", "token": pending["token"]})
        assert aborted.json()["aborted"] is True
        assert routes.pending_rollover("bridge") is None


@pytest.mark.asyncio
async def test_external_trigger_rejects_active_source_channel_during_pending_rollover(tmp_path):
    settings = load_settings(environ={"DEVELOPMENT_BRIDGE_X_TRIGGER_TOKEN": "secret", "DEVELOPMENT_BRIDGE_ROUTE_REGISTRY_PATH": str(tmp_path / "routes-rollover-freeze.json")})
    container = build_container(settings)
    container.route_registry.bootstrap("bridge", "https://chatgpt.com/g/g-p-infra/c/conv-current", "telegram-bridge-g0")
    container.route_registry.prepare_rollover("bridge")
    app = create_streamable_http_app(create_server(container), settings, container)
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        response = await client.post("/mcp/x/coordinator/trigger", headers={"Authorization": "Bearer secret"}, json={"channel_id": "telegram-bridge-g0", "message": "must freeze source"})
    assert response.status_code == 409
    assert (await container.coordinator.status("telegram-bridge-g0"))["state"] == "idle"
