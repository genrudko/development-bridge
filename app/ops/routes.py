from __future__ import annotations

import asyncio
import html
import json
import mimetypes
import time
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from starlette.routing import Route

from app.container import ApplicationContainer
from app.coordinator.routes import RouteRegistry
from app.ops.auth import verify_password
from app.ops.service import OperatorDashboardService
from app.ops.session import (
    COOKIE_NAME,
    LoginRateLimiter,
    create_session_cookie_value,
    resolve_client_ip,
    verify_session_cookie_value,
)
from app.settings import BridgeSettings

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

SECURITY_HEADERS = {
    "Cache-Control": "private, no-store",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def _apply_headers(response: Response) -> Response:
    for k, v in SECURITY_HEADERS.items():
        response.headers[k] = v
    return response


def _snapshot_change_key(data: dict[str, Any]) -> str:
    bridge_part = {k: v for k, v in data.get("bridge", {}).items() if k != "uptime_seconds"}
    system_part = {
        "wake_transport": data.get("system", {}).get("wake_transport"),
        "process_counts": data.get("system", {}).get("process_counts"),
    }
    key_dict = {
        "bridge": bridge_part,
        "route": data.get("route"),
        "progress": data.get("progress"),
        "jobs": data.get("jobs"),
        "executor": data.get("executor"),
        "git": data.get("git"),
        "wake": data.get("wake"),
        "system": system_part,
    }
    return json.dumps(key_dict, sort_keys=True, separators=(",", ":"))


def _terminal_change_key(data: dict[str, Any]) -> str:
    key_dict = {
        "job_id": data.get("job_id"),
        "status": data.get("status"),
        "stdout": data.get("stdout"),
        "stderr": data.get("stderr"),
        "stdout_truncated": data.get("stdout_truncated"),
        "stderr_truncated": data.get("stderr_truncated"),
    }
    return json.dumps(key_dict, sort_keys=True, separators=(",", ":"))


def create_operator_dashboard_routes(
    container: ApplicationContainer,
    settings: BridgeSettings,
) -> list[Route]:
    ops_settings = settings.operator_dashboard
    if not ops_settings.enabled:
        return []

    assert ops_settings.password_hash is not None
    assert ops_settings.session_secret is not None
    password_hash = ops_settings.password_hash.get_secret_value()
    session_secret = ops_settings.session_secret.get_secret_value()
    session_ttl = ops_settings.session_ttl_seconds
    event_interval = ops_settings.event_interval_seconds
    base_path = ops_settings.path.rstrip("/")

    service = OperatorDashboardService(container)
    rate_limiter = LoginRateLimiter(max_attempts=5, window_seconds=600.0)

    def is_authenticated(request: Request) -> bool:
        cookie = request.cookies.get(COOKIE_NAME)
        if not cookie:
            return False
        return verify_session_cookie_value(cookie, session_secret)

    async def root_redirect(request: Request) -> Response:
        return _apply_headers(
            RedirectResponse(url=f"{base_path}/", status_code=307)
        )

    async def login_get(request: Request) -> Response:
        if is_authenticated(request):
            return _apply_headers(
                RedirectResponse(url=f"{base_path}/", status_code=303)
            )
        html_content = (TEMPLATES_DIR / "login.html").read_text(encoding="utf-8")
        error_msg = request.query_params.get("error", "")
        rendered = html_content.replace("{{ base_path }}", base_path)
        rendered = rendered.replace("{% if error %}", "").replace("{% endif %}", "")
        if error_msg:
            rendered = rendered.replace("{{ error }}", html.escape(error_msg))
        else:
            rendered = rendered.replace('<div class="alert-danger">{{ error }}</div>', "")
        return _apply_headers(HTMLResponse(rendered))

    async def login_post(request: Request) -> Response:
        client_host = request.client.host if request.client is not None else "127.0.0.1"
        ip = resolve_client_ip(client_host, request.headers.get("x-forwarded-for"))

        if rate_limiter.is_rate_limited(ip):
            if request.headers.get("accept") == "application/json":
                return _apply_headers(
                    JSONResponse({"error": "Too many failed attempts. Try again later."}, status_code=429)
                )
            html_content = (TEMPLATES_DIR / "login.html").read_text(encoding="utf-8")
            rendered = html_content.replace("{{ base_path }}", base_path)
            rendered = rendered.replace("{% if error %}", "").replace("{% endif %}", "")
            rendered = rendered.replace("{{ error }}", html.escape("Too many failed attempts. Try again later."))
            return _apply_headers(HTMLResponse(rendered, status_code=429))

        password = ""
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body = await request.json()
                password = str(body.get("password") or "")
            except Exception:
                password = ""
        else:
            try:
                form = await request.form()
                password = str(form.get("password") or "")
            except Exception:
                password = ""

        if not password or not verify_password(password, password_hash):
            rate_limiter.record_failure(ip)
            err = "Invalid operator password"
            if request.headers.get("accept") == "application/json":
                return _apply_headers(
                    JSONResponse({"error": err}, status_code=401)
                )
            html_content = (TEMPLATES_DIR / "login.html").read_text(encoding="utf-8")
            rendered = html_content.replace("{{ base_path }}", base_path)
            rendered = rendered.replace("{% if error %}", "").replace("{% endif %}", "")
            rendered = rendered.replace("{{ error }}", html.escape(err))
            return _apply_headers(HTMLResponse(rendered, status_code=401))

        rate_limiter.record_success(ip)
        token = create_session_cookie_value(session_secret, ttl_seconds=session_ttl)

        if request.headers.get("accept") == "application/json":
            resp = _apply_headers(JSONResponse({"authenticated": True}))
        else:
            resp = _apply_headers(
                RedirectResponse(url=f"{base_path}/", status_code=303)
            )

        resp.set_cookie(
            key=COOKIE_NAME,
            value=token,
            max_age=session_ttl,
            path="/",
            httponly=True,
            secure=True,
            samesite="strict",
        )
        return resp

    async def logout_post(request: Request) -> Response:
        resp = _apply_headers(
            RedirectResponse(url=f"{base_path}/login", status_code=303)
        )
        resp.delete_cookie(
            key=COOKIE_NAME,
            path="/",
            httponly=True,
            secure=True,
            samesite="strict",
        )
        return resp

    async def dashboard_get(request: Request) -> Response:
        if not is_authenticated(request):
            return _apply_headers(
                RedirectResponse(url=f"{base_path}/login", status_code=303)
            )
        html_content = (TEMPLATES_DIR / "dashboard.html").read_text(encoding="utf-8")
        rendered = html_content.replace("{{ base_path }}", base_path)
        return _apply_headers(HTMLResponse(rendered))

    async def static_get(request: Request) -> Response:
        rel_path = request.path_params.get("path", "")
        file_path = (STATIC_DIR / rel_path).resolve()
        try:
            file_path.relative_to(STATIC_DIR.resolve())
        except ValueError:
            return _apply_headers(JSONResponse({"error": "Forbidden"}, status_code=403))

        if not file_path.is_file():
            return _apply_headers(JSONResponse({"error": "Not found"}, status_code=404))

        media_type, _ = mimetypes.guess_type(str(file_path))
        return _apply_headers(
            FileResponse(file_path, media_type=media_type or "application/octet-stream")
        )

    async def api_snapshot(request: Request) -> Response:
        if not is_authenticated(request):
            return _apply_headers(JSONResponse({"error": "Unauthorized"}, status_code=401))
        route_id = request.query_params.get("route_id")
        if route_id is not None:
            try:
                RouteRegistry.validate_route_id(route_id)
            except Exception:
                return _apply_headers(JSONResponse({"error": "Invalid route_id"}, status_code=400))
        data = await service.snapshot(route_id)
        return _apply_headers(JSONResponse(data))

    async def api_events(request: Request) -> Response:
        if not is_authenticated(request):
            return _apply_headers(JSONResponse({"error": "Unauthorized"}, status_code=401))

        route_id = request.query_params.get("route_id")
        if route_id is not None:
            try:
                RouteRegistry.validate_route_id(route_id)
            except Exception:
                return _apply_headers(JSONResponse({"error": "Invalid route_id"}, status_code=400))

        async def event_generator():
            try:
                initial_snap = await service.snapshot(route_id)
                last_snap_key = _snapshot_change_key(initial_snap)
                yield f"event: snapshot\ndata: {json.dumps(initial_snap, separators=(',', ':'))}\n\n"

                initial_tail = await service.terminal_tail()
                last_tail_key = _terminal_change_key(initial_tail)
                yield f"event: terminal\ndata: {json.dumps(initial_tail, separators=(',', ':'))}\n\n"

                last_emit = time.time()

                while True:
                    await asyncio.sleep(event_interval)
                    if await request.is_disconnected():
                        break

                    now = time.time()
                    new_snap = await service.snapshot(route_id)
                    new_snap_key = _snapshot_change_key(new_snap)
                    if new_snap_key != last_snap_key:
                        last_snap_key = new_snap_key
                        last_emit = now
                        yield f"event: snapshot\ndata: {json.dumps(new_snap, separators=(',', ':'))}\n\n"

                    new_tail = await service.terminal_tail()
                    new_tail_key = _terminal_change_key(new_tail)
                    if new_tail_key != last_tail_key:
                        last_tail_key = new_tail_key
                        last_emit = now
                        yield f"event: terminal\ndata: {json.dumps(new_tail, separators=(',', ':'))}\n\n"

                    if now - last_emit >= 15.0:
                        last_emit = now
                        yield ": heartbeat\n\n"
            except asyncio.CancelledError:
                pass

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers=dict(SECURITY_HEADERS),
        )

    routes = [
        Route("/", root_redirect, methods=["GET", "HEAD"], name="ops_root_redirect"),
        Route(f"{base_path}", root_redirect, methods=["GET", "HEAD"], name="ops_base_redirect"),
        Route(f"{base_path}/", dashboard_get, methods=["GET", "HEAD"], name="ops_dashboard"),
        Route(f"{base_path}/login", login_get, methods=["GET", "HEAD"], name="ops_login_get"),
        Route(f"{base_path}/login", login_post, methods=["POST"], name="ops_login_post"),
        Route(f"{base_path}/logout", logout_post, methods=["POST", "GET"], name="ops_logout"),
        Route(f"{base_path}/static/{{path:path}}", static_get, methods=["GET", "HEAD"], name="ops_static"),
        Route(f"{base_path}/api/snapshot", api_snapshot, methods=["GET"], name="ops_api_snapshot"),
        Route(f"{base_path}/api/events", api_events, methods=["GET"], name="ops_api_events"),
    ]
    return routes
