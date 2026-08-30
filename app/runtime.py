from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import types
from mcp.server import Server

from app.api.context import new_request_context
from app.api.errors import BridgeError, ErrorCode
from app.api.results import failure, to_mcp_result
from app.audit import AuditEvent, AuditOutcome
from app.container import ApplicationContainer, build_container
from app.tools.coordinator import COORDINATOR_UI_URI, COORDINATOR_UI_URIS
from app.tools.compact import (
    BRIDGE_DASHBOARD_STATE_URI,
    BRIDGE_DASHBOARD_UI_LEGACY_URI,
    BRIDGE_DASHBOARD_UI_URI,
    dashboard_snapshot,
    exposed_tool_definitions,
)
from app.tools.registry import build_tool_registry


def create_server(container: ApplicationContainer | None = None) -> Server:
    application = container or build_container()
    registry = build_tool_registry(application)

    @asynccontextmanager
    async def lifespan(server):
        await application.jobs.start()
        if application.telegram_supervisor is not None:
            await application.telegram_supervisor.start()
        try:
            yield application
        finally:
            if application.telegram_supervisor is not None:
                await application.telegram_supervisor.stop()
            await application.jobs.stop()

    bridge_server = Server(application.settings.server.name, lifespan=lifespan)
    bridge_server.extensions["io.modelcontextprotocol/ui"] = {
        "mimeTypes": ["text/html;profile=mcp-app"]
    }

    connect_domains = []
    if application.settings.server.public_base_url is not None:
        connect_domains.append(str(application.settings.server.public_base_url).rstrip("/"))
    widget_meta = {
        "ui": {
            "csp": {
                "connectDomains": connect_domains,
                "resourceDomains": ["https://unpkg.com"],
            }
        },
        "openai/widgetCSP": {
            "connect_domains": connect_domains,
            "resource_domains": ["https://unpkg.com"],
        },
    }
    if application.settings.server.public_base_url is not None:
        domain = str(application.settings.server.public_base_url).rstrip("/")
        widget_meta["ui"]["domain"] = domain
        widget_meta["openai/widgetDomain"] = domain
    ui_html = (Path(__file__).parent / "coordinator" / "x_ui.html").read_text(
        encoding="utf-8"
    )
    dashboard_html = (Path(__file__).parent / "dashboard" / "status_ui.html").read_text(encoding="utf-8")
    coordinator_path = application.settings.server.endpoint.rstrip("/") + "/x/coordinator/"
    public_base = application.settings.server.public_base_url
    coordinator_url = (
        str(public_base).rstrip("/") + coordinator_path
        if public_base is not None
        else coordinator_path
    )
    ui_html = ui_html.replace("__COORDINATOR_ENDPOINT__", json.dumps(coordinator_url))

    async def list_tools(ctx, params):
        exposed = exposed_tool_definitions(registry, application.settings.server.tool_surface)
        return types.ListToolsResult(tools=list(exposed))

    async def initialized(ctx, params):
        await ctx.session.send_tool_list_changed()

    async def list_resources(ctx, params):
        resources = [
            types.Resource(
                name=(
                    "Development Bridge Coordinator"
                    if uri == COORDINATOR_UI_URI
                    else "Development Bridge Coordinator (legacy)"
                ),
                uri=uri,
                description="Mounted MCP App for delayed coordinator wake messages",
                mimeType="text/html;profile=mcp-app",
                _meta=widget_meta,
            )
            for uri in COORDINATOR_UI_URIS
        ]
        if application.settings.server.tool_surface == "compact":
            resources.extend((
                types.Resource(
                    name="Development Bridge Dashboard",
                    uri=BRIDGE_DASHBOARD_UI_URI,
                    description="Compact user-facing Bridge health and work-progress dashboard",
                    mimeType="text/html;profile=mcp-app",
                    _meta=widget_meta,
                ),
                types.Resource(
                    name="Development Bridge Dashboard State",
                    uri=BRIDGE_DASHBOARD_STATE_URI,
                    description="Lightweight live dashboard state for the mounted MCP App",
                    mimeType="application/json",
                ),
            ))
        return types.ListResourcesResult(resources=resources)

    async def read_resource(ctx, params):
        requested_uri = str(params.uri)
        if requested_uri in {BRIDGE_DASHBOARD_UI_URI, BRIDGE_DASHBOARD_UI_LEGACY_URI} and application.settings.server.tool_surface == "compact":
            text = dashboard_html
            mime_type = "text/html;profile=mcp-app"
            meta = widget_meta
        elif requested_uri == BRIDGE_DASHBOARD_STATE_URI and application.settings.server.tool_surface == "compact":
            text = json.dumps(dashboard_snapshot(application, registry), ensure_ascii=False)
            mime_type = "application/json"
            meta = None
        elif requested_uri in COORDINATOR_UI_URIS:
            text = ui_html
            mime_type = "text/html;profile=mcp-app"
            meta = widget_meta
        else:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Unknown resource")
        return types.ReadResourceResult(
            contents=[
                types.TextResourceContents(
                    uri=requested_uri,
                    mimeType=mime_type,
                    text=text,
                    _meta=meta,
                )
            ]
        )

    async def handle_tool(ctx, params):
        request_context = new_request_context()
        started = time.perf_counter()
        registered = registry.get(params.name)
        if registered is None:
            error = BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "Unknown tool",
                details={"tool": params.name},
            )
            return to_mcp_result(failure(request_context.request_id, error))

        arguments = params.arguments or {}
        outcome = AuditOutcome.SUCCESS
        error_code = None
        try:
            return await registered.handler(ctx, params, request_context)
        except BridgeError as error:
            outcome = AuditOutcome.ERROR
            error_code = error.code.value
            return to_mcp_result(failure(request_context.request_id, error))
        except Exception:
            outcome = AuditOutcome.ERROR
            error_code = ErrorCode.INTERNAL_ERROR.value
            error = BridgeError(ErrorCode.INTERNAL_ERROR, "Internal Bridge error")
            return to_mcp_result(failure(request_context.request_id, error))
        finally:
            await application.audit.emit(
                AuditEvent(
                    request_id=request_context.request_id,
                    tool=params.name,
                    outcome=outcome,
                    duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                    project_id=arguments.get("project_id"),
                    repository_id=arguments.get("repository_id"),
                    error_code=error_code,
                )
            )

    bridge_server.add_notification_handler(
        "notifications/initialized", types.NotificationParams, initialized
    )
    bridge_server.add_request_handler(
        "tools/list", types.PaginatedRequestParams, list_tools
    )
    bridge_server.add_request_handler(
        "tools/call", types.CallToolRequestParams, handle_tool
    )
    bridge_server.add_request_handler(
        "resources/list", types.PaginatedRequestParams, list_resources
    )
    bridge_server.add_request_handler(
        "resources/read", types.ReadResourceRequestParams, read_resource
    )
    return bridge_server
