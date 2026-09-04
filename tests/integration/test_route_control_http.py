from __future__ import annotations

import httpx2
import pytest

from app.container import build_container
from app.runtime import create_server
from app.settings import BridgeSettings
from app.transport import create_streamable_http_app


def create_test_app(tmp_path):
    settings = BridgeSettings.model_validate(
        {
            "server": {"public_base_url": "https://bridge.example.com"},
            "coordinator": {"route_registry_path": tmp_path / "routes.json"},
        }
    )
    container = build_container(settings)
    # Bootstrap test route
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-initial",
        "telegram-bridge-g0",
        "Development Bridge Infra",
    )
    app = create_streamable_http_app(create_server(container), settings, container)
    return app, container, settings


@pytest.mark.asyncio
async def test_get_bind_accepts_redirect_url_without_mutating_active_route(tmp_path):
    app, container, _settings = create_test_app(tmp_path)
    prepared = container.route_control.prepare_bind("bridge", session_id="test-sess")
    op_id = prepared["operation_id"]
    diag_id = prepared["diagnostic_id"]

    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://bridge.example.com") as client:
        return_target = "https://chatgpt.com/g/g-p-infra/c/conv-new-123"
        resp = await client.get(f"/mcp/x/route-control/bind/{op_id}?redirectUrl={return_target}")

        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert resp.headers["cache-control"] == "private, no-store"
        assert "default-src 'self'" in resp.headers["content-security-policy"]
        assert "connect-src 'self'" in resp.headers["content-security-policy"]
        assert resp.headers.get("referrer-policy") == "no-referrer"
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"

        html_text = resp.text
        # Invariant: Safe diagnostic ID and route ID are present
        assert diag_id in html_text
        assert "bridge" in html_text
        # Invariant: No raw physical target, conversation ID, or project ID in visible body
        assert "conv-new-123" not in html_text
        assert "conv-initial" not in html_text
        assert "g-p-infra" not in html_text

        # Invariant: Active route in registry MUST remain UNCHANGED at gen 0
        current = container.route_registry.resolve("bridge")
        assert current["conversation_id"] == "conv-initial"
        assert current["generation"] == 0

        # Candidate is recorded
        pending = container.route_registry.pending_current_bind("bridge")
        assert pending is not None
        assert pending["candidate_url"] == return_target


@pytest.mark.asyncio
async def test_post_commit_mutates_route_and_is_single_use(tmp_path):
    app, container, _settings = create_test_app(tmp_path)
    prepared = container.route_control.prepare_bind("bridge", session_id="test-sess")
    op_id = prepared["operation_id"]
    diag_id = prepared["diagnostic_id"]
    return_target = "https://chatgpt.com/g/g-p-infra/c/conv-new-123"

    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://bridge.example.com") as client:
        # GET landing first to store candidate
        get_resp = await client.get(f"/mcp/x/route-control/bind/{op_id}?redirectUrl={return_target}")
        assert get_resp.status_code == 200

        # POST commit via JSON API (used by frontend auto-commit fetch)
        commit_resp = await client.post(
            f"/mcp/x/route-control/bind/{op_id}/commit",
            headers={"Accept": "application/json"},
        )
        assert commit_resp.status_code == 200
        data = commit_resp.json()
        assert data["ok"] is True
        assert data["route_id"] == "bridge"
        assert data["state"] == "bound"
        assert data["generation"] == 1
        assert data["changed"] is True
        assert data["diagnostic_id"] == diag_id
        assert data["pending_wakes"] == "not_checked"

        # Active route in registry is updated
        updated = container.route_registry.resolve("bridge")
        assert updated["conversation_id"] == "conv-new-123"
        assert updated["generation"] == 1
        assert updated["binding_state"] == "bound"

        # Trace is ok
        trace = container.route_control_trace_store.sanitized(diag_id)
        assert trace["status"] == "ok"

        # Single-use: Replay commit fails closed
        replay_resp = await client.post(
            f"/mcp/x/route-control/bind/{op_id}/commit",
            headers={"Accept": "application/json"},
        )
        assert replay_resp.status_code in {400, 409}
        assert replay_resp.json()["ok"] is False

        # Trace history remains ok and not corrupted
        trace_after = container.route_control_trace_store.sanitized(diag_id)
        assert trace_after["status"] == "ok"


@pytest.mark.asyncio
async def test_post_commit_form_html_rendering(tmp_path):
    app, container, _settings = create_test_app(tmp_path)
    prepared = container.route_control.prepare_bind("bridge", session_id="test-sess")
    op_id = prepared["operation_id"]
    diag_id = prepared["diagnostic_id"]
    return_target = "https://chatgpt.com/g/g-p-infra/c/conv-new-123"

    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://bridge.example.com") as client:
        # GET landing
        await client.get(f"/mcp/x/route-control/bind/{op_id}?redirectUrl={return_target}")

        # Standard form POST (non-JSON)
        form_resp = await client.post(f"/mcp/x/route-control/bind/{op_id}/commit")
        assert form_resp.status_code == 200
        assert "text/html" in form_resp.headers["content-type"]
        html = form_resp.text
        assert "✅" in html
        assert "Chat linked" in html
        assert "Generation:" in html
        assert "1" in html
        assert "Pending wake:" in html
        assert "not_checked" in html
        assert diag_id in html
        assert f"/mcp/x/route-control/return/{diag_id}" in html

        # No raw tokens or physical IDs in body
        assert "conv-new-123" not in html
        assert "g-p-infra" not in html


@pytest.mark.asyncio
async def test_same_target_rebind_warning_treatment(tmp_path):
    app, container, _settings = create_test_app(tmp_path)
    prepared = container.route_control.prepare_bind("bridge", session_id="test-sess")
    op_id = prepared["operation_id"]
    same_target = "https://chatgpt.com/g/g-p-infra/c/conv-initial"

    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://bridge.example.com") as client:
        await client.get(f"/mcp/x/route-control/bind/{op_id}?redirectUrl={same_target}")

        commit_resp = await client.post(
            f"/mcp/x/route-control/bind/{op_id}/commit",
            headers={"Accept": "application/json"},
        )
        assert commit_resp.status_code == 200
        data = commit_resp.json()
        assert data["ok"] is True
        assert data["state"] == "already_bound"
        assert data["changed"] is False
        assert data["generation"] == 0

    # Fresh operation for HTML form submission test
    prepared2 = container.route_control.prepare_bind("bridge", session_id="test-sess-2")
    op_id2 = prepared2["operation_id"]
    diag_id2 = prepared2["diagnostic_id"]
    async with httpx2.AsyncClient(transport=transport, base_url="https://bridge.example.com") as client:
        await client.get(f"/mcp/x/route-control/bind/{op_id2}?redirectUrl={same_target}")
        form_resp = await client.post(f"/mcp/x/route-control/bind/{op_id2}/commit")
        assert form_resp.status_code == 200
        html = form_resp.text
        assert "⚠️" in html or "already linked" in html
        assert "Generation:" in html
        assert diag_id2 in html


@pytest.mark.asyncio
async def test_get_bind_missing_redirect_url_yields_failure_page(tmp_path):
    app, container, _settings = create_test_app(tmp_path)
    prepared = container.route_control.prepare_bind("bridge", session_id="test-sess")
    op_id = prepared["operation_id"]
    diag_id = prepared["diagnostic_id"]

    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://bridge.example.com") as client:
        resp = await client.get(f"/mcp/x/route-control/bind/{op_id}")
        assert resp.status_code == 400
        assert "text/html" in resp.headers["content-type"]
        html = resp.text
        assert "❌" in html
        assert "Chat could not be linked" in html
        assert "Conversation identification" in html
        assert "Existing binding was not changed" in html
        assert diag_id in html

        # Route is unchanged
        assert container.route_registry.resolve("bridge")["generation"] == 0


@pytest.mark.asyncio
async def test_get_bind_malformed_target_yields_failure_page(tmp_path):
    app, container, _settings = create_test_app(tmp_path)
    prepared = container.route_control.prepare_bind("bridge", session_id="test-sess")
    op_id = prepared["operation_id"]
    diag_id = prepared["diagnostic_id"]

    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://bridge.example.com") as client:
        resp = await client.get(f"/mcp/x/route-control/bind/{op_id}?redirectUrl=https://evil.com/phishing")
        assert resp.status_code == 400
        assert "text/html" in resp.headers["content-type"]
        html = resp.text
        assert "❌" in html
        assert "Chat could not be linked" in html
        assert "Target validation" in html
        assert diag_id in html


@pytest.mark.asyncio
async def test_get_bind_invalid_token_yields_failure_page(tmp_path):
    app, _container, _settings = create_test_app(tmp_path)

    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://bridge.example.com") as client:
        resp = await client.get("/mcp/x/route-control/bind/invalid-token?redirectUrl=https://chatgpt.com/g/g-p-infra/c/conv-123")
        assert resp.status_code == 400
        assert "text/html" in resp.headers["content-type"]
        html = resp.text
        assert "❌" in html
        assert "Chat could not be linked" in html


@pytest.mark.asyncio
async def test_cross_project_rebind_rejected(tmp_path):
    app, container, _settings = create_test_app(tmp_path)
    prepared = container.route_control.prepare_bind("bridge", session_id="test-sess", allow_project_change=False)
    op_id = prepared["operation_id"]
    diag_id = prepared["diagnostic_id"]
    cross_target = "https://chatgpt.com/g/g-p-other/c/conv-cross"

    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://bridge.example.com") as client:
        resp = await client.get(f"/mcp/x/route-control/bind/{op_id}?redirectUrl={cross_target}")
        assert resp.status_code in {400, 409}
        assert "text/html" in resp.headers["content-type"]
        html = resp.text
        assert "❌" in html
        assert "Project policy check" in html
        assert diag_id in html

        # Active route is unchanged
        assert container.route_registry.resolve("bridge")["conversation_id"] == "conv-initial"


@pytest.mark.asyncio
async def test_return_endpoint_performs_server_side_redirect(tmp_path):
    app, container, _settings = create_test_app(tmp_path)
    prepared = container.route_control.prepare_bind("bridge", session_id="test-sess")
    op_id = prepared["operation_id"]
    diag_id = prepared["diagnostic_id"]
    return_target = "https://chatgpt.com/g/g-p-infra/c/conv-return-target?query=1&utm_source=chatgpt#section"

    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://bridge.example.com") as client:
        # GET landing records candidate and return target in raw trace
        await client.get(f"/mcp/x/route-control/bind/{op_id}?redirectUrl={return_target}")

        # Follow return endpoint without following redirect
        return_resp = await client.get(
            f"/mcp/x/route-control/return/{diag_id}",
            follow_redirects=False,
        )
        assert return_resp.status_code in {302, 303, 307}
        # Invariant: Query parameters and fragments must be stripped via parsed canonical route_url
        assert return_resp.headers["location"] == "https://chatgpt.com/g/g-p-infra/c/conv-return-target"
        assert return_resp.headers["cache-control"] == "private, no-store"
        assert return_resp.headers.get("referrer-policy") == "no-referrer"
        assert return_resp.headers.get("x-content-type-options") == "nosniff"


@pytest.mark.asyncio
async def test_return_endpoint_unknown_diagnostic_id(tmp_path):
    app, _container, _settings = create_test_app(tmp_path)

    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://bridge.example.com") as client:
        resp = await client.get("/mcp/x/route-control/return/bind-nonexistent", follow_redirects=False)
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_no_leakage_in_body_or_headers(tmp_path):
    app, container, _settings = create_test_app(tmp_path)
    prepared = container.route_control.prepare_bind("bridge", session_id="test-sess")
    op_id = prepared["operation_id"]
    return_target = "https://chatgpt.com/g/g-p-infra/c/conv-sensitive-secret"

    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://bridge.example.com") as client:
        # GET landing
        get_resp = await client.get(f"/mcp/x/route-control/bind/{op_id}?redirectUrl={return_target}")
        assert get_resp.status_code == 200

        # Check response headers for leakage
        for val in get_resp.headers.values():
            assert "conv-sensitive-secret" not in val
            assert "g-p-infra" not in val
            assert op_id not in val

        # Check HTML body
        assert "conv-sensitive-secret" not in get_resp.text
        assert "g-p-infra" not in get_resp.text

        # POST commit (JSON)
        json_resp = await client.post(
            f"/mcp/x/route-control/bind/{op_id}/commit",
            headers={"Accept": "application/json"},
        )
        assert json_resp.status_code == 200
        json_text = json_resp.text
        assert "conv-sensitive-secret" not in json_text
        assert "g-p-infra" not in json_text
        assert op_id not in json_text


@pytest.mark.asyncio
async def test_get_bind_landing_on_already_completed_operation(tmp_path):
    app, container, _settings = create_test_app(tmp_path)
    prepared = container.route_control.prepare_bind("bridge", session_id="test-sess")
    op_id = prepared["operation_id"]
    diag_id = prepared["diagnostic_id"]
    return_target = "https://chatgpt.com/g/g-p-infra/c/conv-new-123"

    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://bridge.example.com") as client:
        # GET landing
        await client.get(f"/mcp/x/route-control/bind/{op_id}?redirectUrl={return_target}")
        # Commit
        await client.post(f"/mcp/x/route-control/bind/{op_id}/commit", headers={"Accept": "application/json"})

        # Subsequent GET to landing endpoint shows clean completed success page
        subsequent_get = await client.get(f"/mcp/x/route-control/bind/{op_id}?redirectUrl={return_target}")
        assert subsequent_get.status_code == 200
        assert "text/html" in subsequent_get.headers["content-type"]
        html = subsequent_get.text
        assert "✅" in html
        assert "Chat linked" in html
        assert "Generation:" in html
        assert "1" in html
        assert diag_id in html
        assert f"/mcp/x/route-control/return/{diag_id}" in html


@pytest.mark.asyncio
async def test_widget_meta_contains_redirect_domains(tmp_path):
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    from app.tools.compact import BRIDGE_DASHBOARD_UI_URI
    from app.tools.coordinator import COORDINATOR_UI_URI

    settings = BridgeSettings.model_validate(
        {
            "server": {
                "public_base_url": "https://bridge.example.com",
                "tool_surface": "compact",
            },
            "coordinator": {"route_registry_path": tmp_path / "routes.json"},
        }
    )
    container = build_container(settings)
    app = create_streamable_http_app(create_server(container), settings, container)

    async with app.router.lifespan_context(app), httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client, streamable_http_client(
        "http://127.0.0.1/mcp", http_client=client
    ) as streams, ClientSession(
        *streams
    ) as session:
        await session.initialize()

        # Check list_resources metadata scoping
        res_list = await session.list_resources()
        res_by_uri = {str(r.uri): getattr(r, "meta", None) or (getattr(r, "model_extra", {}) or {}).get("_meta") for r in res_list.resources}

        # Coordinator resource in list_resources has redirect domains
        coord_list_meta = res_by_uri.get(COORDINATOR_UI_URI)
        assert coord_list_meta is not None
        assert coord_list_meta["ui"]["csp"]["redirectDomains"] == ["https://bridge.example.com"]
        assert coord_list_meta["openai/widgetCSP"]["redirect_domains"] == ["https://bridge.example.com"]

        # Dashboard resource in list_resources does NOT inherit redirect domains
        dash_list_meta = res_by_uri.get(BRIDGE_DASHBOARD_UI_URI)
        assert dash_list_meta is not None
        assert "redirectDomains" not in dash_list_meta["ui"]["csp"]
        assert "redirect_domains" not in dash_list_meta["openai/widgetCSP"]

        # Coordinator resource in read_resource has redirect domains
        resource = await session.read_resource(COORDINATOR_UI_URI)
        contents = resource.contents[0]
        meta = getattr(contents, "meta", None) or (getattr(contents, "model_extra", {}) or {}).get("_meta")
        assert meta is not None
        assert meta["ui"]["csp"]["redirectDomains"] == ["https://bridge.example.com"]
        assert meta["openai/widgetCSP"]["redirect_domains"] == ["https://bridge.example.com"]

        # Dashboard resource in read_resource does NOT inherit redirect domains
        dash_resource = await session.read_resource(BRIDGE_DASHBOARD_UI_URI)
        dash_contents = dash_resource.contents[0]
        dash_meta = getattr(dash_contents, "meta", None) or (getattr(dash_contents, "model_extra", {}) or {}).get("_meta")
        assert dash_meta is not None
        assert "redirectDomains" not in dash_meta["ui"]["csp"]
        assert "redirect_domains" not in dash_meta["openai/widgetCSP"]


def create_test_app_with_jobs(tmp_path):
    from tests.fixtures.repositories import create_git_repository

    repo_path = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate(
        {
            "server": {"public_base_url": "https://bridge.example.com"},
            "coordinator": {"route_registry_path": tmp_path / "routes.json"},
            "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
            "projects": [
                {
                    "id": "project",
                    "name": "Test Project",
                    "repositories": [
                        {
                            "id": "repository",
                            "path": repo_path,
                            "capabilities": {"execute": True},
                            "tasks": [
                                {
                                    "id": "task",
                                    "name": "Task",
                                    "executable": "/bin/echo",
                                    "arguments": ["done"],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )
    container = build_container(settings)
    if container.jobs and container.jobs.store:
        container.jobs.store.initialize()
    container.route_registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-infra/c/conv-initial",
        "telegram-bridge-g0",
        "Development Bridge Infra",
    )
    app = create_streamable_http_app(create_server(container), settings, container)
    return app, container, settings


@pytest.mark.asyncio
async def test_route_control_endpoints_require_component_authorization(tmp_path):
    app, container, _settings = create_test_app(tmp_path)
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://bridge.example.com") as client:
        # 1. Missing authorization
        r1 = await client.get("/mcp/x/route-control/status?route_id=bridge")
        assert r1.status_code == 401

        r2 = await client.post("/mcp/x/route-control/unbind", json={"route_id": "bridge"})
        assert r2.status_code == 401

        r3 = await client.post("/mcp/x/route-control/cancel-wakes", json={"route_id": "bridge"})
        assert r3.status_code == 401

        r4 = await client.post("/mcp/x/route-control/unbind-and-cancel", json={"route_id": "bridge"})
        assert r4.status_code == 401

        # 2. Forged / invalid token
        headers_forged = {"Authorization": "Bearer forged_control_token_123"}
        r_forged = await client.get("/mcp/x/route-control/status?route_id=bridge", headers=headers_forged)
        assert r_forged.status_code == 401

        # 3. Valid token issued by service
        descriptor = container.route_control.issue_control_descriptor("bridge")
        valid_token = descriptor["control_token"]
        headers_valid = {"Authorization": f"Bearer {valid_token}"}

        r_valid = await client.get("/mcp/x/route-control/status?route_id=bridge", headers=headers_valid)
        assert r_valid.status_code == 200
        assert r_valid.json()["ok"] is True
        assert r_valid.json()["route_id"] == "bridge"

        # 4. Stale token after route generation changes
        container.route_registry.takeover(
            "bridge", "https://chatgpt.com/g/g-p-infra/c/conv-gen1", "Bridge Gen 1"
        )
        r_stale = await client.get("/mcp/x/route-control/status?route_id=bridge", headers=headers_valid)
        assert r_stale.status_code == 409


@pytest.mark.asyncio
async def test_route_control_status_endpoint_returns_safe_counts_and_no_leakage(tmp_path):
    app, container, _settings = create_test_app_with_jobs(tmp_path)
    descriptor = container.route_control.issue_control_descriptor("bridge")
    token = descriptor["control_token"]
    headers = {"Authorization": f"Bearer {token}"}

    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://bridge.example.com") as client:
        r = await client.get("/mcp/x/route-control/status?route_id=bridge", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["route_id"] == "bridge"
        assert data["state"] == "bound"
        assert data["pending_coordinator_wakes"] == 0
        assert data["pending_durable_waiters"] == 0

        # Arm coordinator wake
        await container.coordinator.arm("wake 1", channel_id="telegram-bridge-g0", delay_seconds=10)

        # Register durable waiter
        repo = container.projects.repositories.get("project", "repository")
        job = await container.jobs.start_task(repo, "task", "req-1")
        await container.jobs.wake_on_jobs_durable(
            repo,
            (job.job_id,),
            "all_terminal",
            "coordinator",
            {"route_id": "bridge", "generation": 0, "channel_id": "telegram-bridge-g0"},
        )

        # Status now reflects pending counts
        r_armed = await client.get("/mcp/x/route-control/status?route_id=bridge", headers=headers)
        data_armed = r_armed.json()
        assert data_armed["pending_coordinator_wakes"] == 1
        assert data_armed["pending_durable_waiters"] == 1

        # Body must NOT leak physical chat target, conv id, project id
        body_text = r_armed.text
        assert "conv-initial" not in body_text
        assert "g-p-infra" not in body_text
        assert "https://chatgpt.com" not in body_text


@pytest.mark.asyncio
async def test_route_control_cancel_wakes_endpoint(tmp_path):
    app, container, _settings = create_test_app_with_jobs(tmp_path)
    await container.coordinator.arm("wake 1", channel_id="telegram-bridge-g0", delay_seconds=10)
    repo = container.projects.repositories.get("project", "repository")
    job = await container.jobs.start_task(repo, "task", "req-1")
    await container.jobs.wake_on_jobs_durable(
        repo,
        (job.job_id,),
        "all_terminal",
        "coordinator",
        {"route_id": "bridge", "generation": 0, "channel_id": "telegram-bridge-g0"},
    )

    descriptor = container.route_control.issue_control_descriptor("bridge")
    token = descriptor["control_token"]
    headers = {"Authorization": f"Bearer {token}"}

    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://bridge.example.com") as client:
        r = await client.post("/mcp/x/route-control/cancel-wakes", json={"route_id": "bridge"}, headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["cancelled_coordinator_wakes"] == 1
        assert data["cancelled_durable_waiters"] == 1
        assert data["safe_status"]["pending_coordinator_wakes"] == 0
        assert data["safe_status"]["pending_durable_waiters"] == 0


@pytest.mark.asyncio
async def test_route_control_unbind_endpoint_refuses_when_wakes_pending(tmp_path):
    app, container, _settings = create_test_app_with_jobs(tmp_path)
    await container.coordinator.arm("wake 1", channel_id="telegram-bridge-g0", delay_seconds=10)

    descriptor = container.route_control.issue_control_descriptor("bridge")
    token = descriptor["control_token"]
    headers = {"Authorization": f"Bearer {token}"}

    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://bridge.example.com") as client:
        # Unbind must refuse with 409 and PENDING_WAKES
        r = await client.post("/mcp/x/route-control/unbind", json={"route_id": "bridge"}, headers=headers)
        assert r.status_code == 409
        data = r.json()
        assert data["ok"] is False
        assert data["code"] == "POLICY_VIOLATION"
        assert data["details"]["error_code"] == "PENDING_WAKES"
        assert data["safe_status"]["state"] == "bound"


@pytest.mark.asyncio
async def test_route_control_unbind_and_cancel_endpoint(tmp_path):
    app, container, _settings = create_test_app_with_jobs(tmp_path)
    await container.coordinator.arm("wake 1", channel_id="telegram-bridge-g0", delay_seconds=10)
    repo = container.projects.repositories.get("project", "repository")
    job = await container.jobs.start_task(repo, "task", "req-1")
    await container.jobs.wake_on_jobs_durable(
        repo,
        (job.job_id,),
        "all_terminal",
        "coordinator",
        {"route_id": "bridge", "generation": 0, "channel_id": "telegram-bridge-g0"},
    )

    descriptor = container.route_control.issue_control_descriptor("bridge")
    token = descriptor["control_token"]
    headers = {"Authorization": f"Bearer {token}"}

    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://bridge.example.com") as client:
        r = await client.post(
            "/mcp/x/route-control/unbind-and-cancel", json={"route_id": "bridge"}, headers=headers
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["state"] == "unbound"
        assert data["cancelled_coordinator_wakes"] == 1
        assert data["cancelled_durable_waiters"] == 1
        assert data["safe_status"]["state"] == "unbound"
        assert data["safe_status"]["pending_coordinator_wakes"] == 0
        assert data["safe_status"]["pending_durable_waiters"] == 0


@pytest.mark.asyncio
async def test_route_control_endpoints_leakage_scan(tmp_path):
    app, container, _settings = create_test_app_with_jobs(tmp_path)
    descriptor = container.route_control.issue_control_descriptor("bridge")
    token = descriptor["control_token"]
    headers = {"Authorization": f"Bearer {token}"}

    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://bridge.example.com") as client:
        r_status = await client.get("/mcp/x/route-control/status?route_id=bridge", headers=headers)
        r_cancel = await client.post("/mcp/x/route-control/cancel-wakes", json={"route_id": "bridge"}, headers=headers)
        r_unbind = await client.post("/mcp/x/route-control/unbind", json={"route_id": "bridge"}, headers=headers)

        for resp in (r_status, r_cancel, r_unbind):
            text = resp.text
            assert "conv-initial" not in text
            assert "g-p-infra" not in text
            assert "https://chatgpt.com" not in text
            assert token not in text
