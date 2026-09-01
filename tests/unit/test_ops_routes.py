import pytest
from starlette.testclient import TestClient

from app.container import build_container
from app.ops.auth import hash_password
from app.ops.session import COOKIE_NAME, create_session_cookie_value
from app.runtime import create_server
from app.settings import BridgeSettings, load_settings
from app.transport import create_streamable_http_app


@pytest.fixture
def disabled_app(tmp_path):
    settings = load_settings(environ={
        "DEVELOPMENT_BRIDGE_OPERATOR_DASHBOARD_ENABLED": "false",
    })
    container = build_container(settings)
    server = create_server(container)
    return create_streamable_http_app(server, settings, container)


@pytest.fixture
def enabled_app(tmp_path):
    password_hash = hash_password("CorrectPassword123")
    settings = load_settings(environ={
        "DEVELOPMENT_BRIDGE_OPERATOR_DASHBOARD_ENABLED": "true",
        "DEVELOPMENT_BRIDGE_OPERATOR_DASHBOARD_PASSWORD_HASH": password_hash,
        "DEVELOPMENT_BRIDGE_OPERATOR_DASHBOARD_SESSION_SECRET": "test-secret-key-12345",
        "DEVELOPMENT_BRIDGE_OPERATOR_DASHBOARD_PATH": "/ops",
    })
    container = build_container(settings)
    server = create_server(container)
    return create_streamable_http_app(server, settings, container), settings


def test_disabled_dashboard_returns_404(disabled_app):
    client = TestClient(disabled_app)
    assert client.get("/").status_code == 404
    assert client.get("/ops/").status_code == 404
    assert client.get("/ops/login").status_code == 404
    assert client.get("/ops/api/snapshot").status_code == 404
    assert client.get("/ops/api/events").status_code == 404


def test_enabled_dashboard_root_redirect_and_headers(enabled_app):
    app, _ = enabled_app
    client = TestClient(app)
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 303, 307)
    assert resp.headers["location"] == "/ops/"
    assert resp.headers["cache-control"] == "private, no-store"
    assert "default-src 'self'" in resp.headers["content-security-policy"]


def test_unauthenticated_ops_redirects_to_login(enabled_app):
    app, _ = enabled_app
    client = TestClient(app)
    resp = client.get("/ops/", follow_redirects=False)
    assert resp.status_code in (302, 303, 307)
    assert resp.headers["location"] == "/ops/login"


def test_unauthenticated_api_returns_401(enabled_app):
    app, _ = enabled_app
    client = TestClient(app)
    resp = client.get("/ops/api/snapshot")
    assert resp.status_code == 401
    assert resp.headers["cache-control"] == "private, no-store"


def test_login_flow_and_session_cookie(enabled_app):
    app, settings = enabled_app
    client = TestClient(app)

    # 1. Login page GET
    resp = client.get("/ops/login")
    assert resp.status_code == 200
    assert "password" in resp.text
    assert resp.headers["cache-control"] == "private, no-store"
    assert "default-src 'self'" in resp.headers["content-security-policy"]

    # 2. Bad password POST
    bad_resp = client.post("/ops/login", data={"password": "WrongPassword"})
    assert bad_resp.status_code == 401
    assert COOKIE_NAME not in client.cookies

    # 3. Good password POST
    good_resp = client.post("/ops/login", data={"password": "CorrectPassword123"}, follow_redirects=False)
    assert good_resp.status_code in (302, 303, 307)
    assert good_resp.headers["location"] == "/ops/"
    assert COOKIE_NAME in good_resp.cookies
    cookie = good_resp.cookies[COOKIE_NAME]
    assert cookie is not None

    # 4. Access /ops/ with cookie
    client.cookies.set(COOKIE_NAME, cookie)
    dash_resp = client.get("/ops/")
    assert dash_resp.status_code == 200
    assert "Development Bridge" in dash_resp.text

    # 5. Access /ops/api/snapshot with cookie
    api_resp = client.get("/ops/api/snapshot")
    assert api_resp.status_code == 200
    data = api_resp.json()
    assert data["bridge"]["name"] == "development-bridge"
    assert "jobs" in data
    assert "system" in data

    # 6. Logout
    logout_resp = client.post("/ops/logout", follow_redirects=False)
    assert logout_resp.status_code in (302, 303, 307, 200)


def test_login_rate_limiting_after_5_failures(enabled_app):
    app, _ = enabled_app
    client = TestClient(app)

    for i in range(5):
        resp = client.post("/ops/login", data={"password": f"BadPass{i}"})
        assert resp.status_code == 401

    # 6th attempt is rate-limited
    resp6 = client.post("/ops/login", data={"password": "BadPass6"})
    assert resp6.status_code == 429
