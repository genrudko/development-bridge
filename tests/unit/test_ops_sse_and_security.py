import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from starlette.testclient import TestClient

from app.container import build_container
from app.jobs.models import JobRecord, JobStatus
from app.ops.auth import hash_password
from app.ops.routes import create_operator_dashboard_routes
from app.ops.session import COOKIE_NAME, create_session_cookie_value
from app.runtime import create_server
from app.settings import BridgeSettings
from app.transport import create_streamable_http_app


@pytest.fixture
def enabled_setup(tmp_path):
    password_hash = hash_password("CorrectPassword123")
    session_secret = "test-secret-key-12345"
    settings = BridgeSettings.model_validate({
        "managed_repositories": {"root": tmp_path / "managed"},
        "coordinator": {"route_registry_path": tmp_path / "routes.json"},
        "jobs": {
            "database_path": tmp_path / "jobs.sqlite3",
            "artifact_directory": tmp_path / "artifacts",
        },
        "operator_dashboard": {
            "enabled": True,
            "password_hash": password_hash,
            "session_secret": session_secret,
            "event_interval_seconds": 0.1,
        }
    })
    container = build_container(settings)
    if container.jobs.store is not None:
        container.jobs.store.initialize()
    server = create_server(container)
    app = create_streamable_http_app(server, settings, container)
    cookie_value = create_session_cookie_value(session_secret)
    return app, container, settings, cookie_value


def test_static_assets_security(enabled_setup):
    app, _, _, cookie = enabled_setup
    client = TestClient(app)

    # Valid static CSS
    resp_css = client.get("/ops/static/style.css")
    assert resp_css.status_code == 200
    assert "text/css" in resp_css.headers["content-type"]
    assert resp_css.headers["cache-control"] == "private, no-store"

    # Valid static JS
    resp_js = client.get("/ops/static/app.js")
    assert resp_js.status_code == 200
    assert "javascript" in resp_js.headers["content-type"]

    # Nonexistent static file -> 404
    resp_404 = client.get("/ops/static/nonexistent.png")
    assert resp_404.status_code == 404

    # Directory traversal attempt -> 403 or 404
    resp_traversal = client.get("/ops/static/../../etc/passwd")
    assert resp_traversal.status_code in (403, 404)


@pytest.mark.asyncio
async def test_sse_initial_events_and_disconnect(enabled_setup):
    _, container, settings, cookie = enabled_setup
    routes = create_operator_dashboard_routes(container, settings)
    events_route = [r for r in routes if r.name == "ops_api_events"][0]

    state = {"disconnected": False}
    request = MagicMock()
    request.cookies = {COOKIE_NAME: cookie}
    request.query_params = {}
    async def fake_disconnected():
        return state["disconnected"]
    request.is_disconnected = fake_disconnected

    response = await events_route.endpoint(request)
    assert response.status_code == 200
    assert response.media_type == "text/event-stream"
    assert response.headers["Cache-Control"] == "private, no-store"

    gen = response.body_iterator
    # 1. Initial snapshot event
    evt1 = await anext(gen)
    assert evt1.startswith("event: snapshot\ndata: ")
    snap_data = json.loads(evt1.split("data: ", 1)[1].strip())
    assert snap_data["bridge"]["name"] == "development-bridge"

    # 2. Initial terminal event
    evt2 = await anext(gen)
    assert evt2.startswith("event: terminal\ndata: ")
    tail_data = json.loads(evt2.split("data: ", 1)[1].strip())
    assert tail_data["status"] == "idle"

    # 3. Disconnect
    state["disconnected"] = True
    try:
        await anext(gen)
        pytest.fail("Generator did not stop on disconnect")
    except StopAsyncIteration:
        pass


@pytest.mark.asyncio
async def test_sse_emits_changed_output_on_job_progress(enabled_setup):
    _, container, settings, cookie = enabled_setup
    routes = create_operator_dashboard_routes(container, settings)
    events_route = [r for r in routes if r.name == "ops_api_events"][0]

    state = {"disconnected": False}
    request = MagicMock()
    request.cookies = {COOKIE_NAME: cookie}
    request.query_params = {}
    async def fake_disconnected():
        return state["disconnected"]
    request.is_disconnected = fake_disconnected

    response = await events_route.endpoint(request)
    gen = response.body_iterator

    # Consume initial snapshot & terminal
    await anext(gen)
    await anext(gen)

    # Now create a running job and append output in store
    job, _ = container.jobs.store.create(
        project_id="p", repository_id="r", task_id="t", request_id="req", idempotency_key=None
    )
    container.jobs.store.start(job.job_id)
    container.jobs.store.append_output(job.job_id, "stdout", b"step 1 done\n", 1024)

    # Next iteration in SSE will detect changed snapshot and changed terminal
    evt3 = await anext(gen)
    assert "event: " in evt3

    state["disconnected"] = True
    await gen.aclose()


@pytest.mark.asyncio
async def test_sse_does_not_emit_on_pure_uptime_ticks_and_sends_heartbeat(enabled_setup, monkeypatch):
    _, container, settings, _ = enabled_setup
    sim_time = [100000.0]

    def mock_time():
        t = sim_time[0]
        sim_time[0] += 5.0
        return t

    monkeypatch.setattr("app.ops.routes.time.time", mock_time)
    monkeypatch.setattr("app.ops.service.time.time", mock_time)
    monkeypatch.setattr("app.ops.metrics.time.time", mock_time)
    monkeypatch.setattr("app.ops.session.time.time", mock_time)

    cookie = create_session_cookie_value(settings.operator_dashboard.session_secret.get_secret_value())
    routes = create_operator_dashboard_routes(container, settings)
    events_route = [r for r in routes if r.name == "ops_api_events"][0]

    state = {"disconnected": False}
    request = MagicMock()
    request.cookies = {COOKIE_NAME: cookie}
    request.query_params = {}
    async def fake_disconnected():
        return state["disconnected"]
    request.is_disconnected = fake_disconnected

    response = await events_route.endpoint(request)
    assert response.status_code == 200
    gen = response.body_iterator

    # 1. Initial snapshot & terminal
    evt1 = await anext(gen)
    assert evt1.startswith("event: snapshot")
    evt2 = await anext(gen)
    assert evt2.startswith("event: terminal")

    # 2. Idle progression: next event should be a heartbeat comment after idle interval
    evt_idle = await anext(gen)
    assert evt_idle == ": heartbeat\n\n"

    state["disconnected"] = True
    await gen.aclose()
