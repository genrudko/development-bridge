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


def test_logout_deletes_cookie_with_host_prefix_security_attributes(enabled_app):
    app, _ = enabled_app
    client = TestClient(app)
    resp = client.post("/ops/logout", follow_redirects=False)
    assert resp.status_code in (302, 303, 307)
    set_cookie = resp.headers.get("set-cookie", "")
    assert COOKIE_NAME in set_cookie
    # RFC 6265bis __Host- cookie requirements: Secure, Path=/, HttpOnly, SameSite=Strict
    cookie_lower = set_cookie.lower()
    assert "path=/" in cookie_lower
    assert "secure" in cookie_lower
    assert "httponly" in cookie_lower
    assert "samesite=strict" in cookie_lower


def test_login_error_query_param_is_html_escaped(enabled_app):
    app, _ = enabled_app
    client = TestClient(app)
    xss_payload = '<script>alert("xss")</script>'
    resp = client.get(f"/ops/login?error={xss_payload}")
    assert resp.status_code == 200
    assert "<script>" not in resp.text
    assert "&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;" in resp.text or "&lt;script&gt;" in resp.text


def test_custom_dashboard_path_configures_all_urls():
    password_hash = hash_password("CorrectPassword123")
    settings = load_settings(environ={
        "DEVELOPMENT_BRIDGE_OPERATOR_DASHBOARD_ENABLED": "true",
        "DEVELOPMENT_BRIDGE_OPERATOR_DASHBOARD_PASSWORD_HASH": password_hash,
        "DEVELOPMENT_BRIDGE_OPERATOR_DASHBOARD_SESSION_SECRET": "test-secret-key-12345",
        "DEVELOPMENT_BRIDGE_OPERATOR_DASHBOARD_PATH": "/custom-ops",
    })
    container = build_container(settings)
    server = create_server(container)
    app = create_streamable_http_app(server, settings, container)
    client = TestClient(app)

    # 1. Root redirect
    resp = client.get("/", follow_redirects=False)
    assert resp.headers["location"] == "/custom-ops/"

    # 2. Login page
    login_page = client.get("/custom-ops/login")
    assert login_page.status_code == 200
    assert 'action="/custom-ops/login"' in login_page.text
    assert 'href="/custom-ops/static/style.css"' in login_page.text

    # 3. Login POST redirect
    login_resp = client.post("/custom-ops/login", data={"password": "CorrectPassword123"}, follow_redirects=False)
    assert login_resp.status_code in (302, 303, 307)
    assert login_resp.headers["location"] == "/custom-ops/"
    cookie = login_resp.cookies[COOKIE_NAME]

    # 4. Dashboard page
    client.cookies.set(COOKIE_NAME, cookie)
    dash_page = client.get("/custom-ops/")
    assert dash_page.status_code == 200
    assert 'action="/custom-ops/logout"' in dash_page.text
    assert 'href="/custom-ops/static/style.css"' in dash_page.text
    assert 'src="/custom-ops/static/app.js"' in dash_page.text
    assert 'data-base-path="/custom-ops"' in dash_page.text

    # 5. Logout POST redirect
    logout_resp = client.post("/custom-ops/logout", follow_redirects=False)
    assert logout_resp.status_code in (302, 303, 307)
    assert logout_resp.headers["location"] == "/custom-ops/login"


def test_api_snapshot_and_events_reject_invalid_route_id(enabled_app):
    app, _ = enabled_app
    cookie = create_session_cookie_value("test-secret-key-12345")
    client = TestClient(app, cookies={COOKIE_NAME: cookie})

    # Invalid route_id with slash or special chars
    resp_snap = client.get("/ops/api/snapshot?route_id=bad/route/id")
    assert resp_snap.status_code == 400
    assert "error" in resp_snap.json()

    resp_events = client.get("/ops/api/events?route_id=bad/route/id")
    assert resp_events.status_code == 400
