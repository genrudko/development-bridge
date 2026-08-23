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
from app.tools.coordinator import COORDINATOR_UI_URI
from app.tools.registry import build_tool_registry


def create_server(container: ApplicationContainer | None = None) -> Server:
    application = container or build_container()
    registry = build_tool_registry(application)

    @asynccontextmanager
    async def lifespan(server):
        await application.jobs.start()
        try:
            yield application
        finally:
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
    coordinator_path = application.settings.server.endpoint.rstrip("/") + "/x/coordinator/"
    public_base = application.settings.server.public_base_url
    coordinator_url = (
        str(public_base).rstrip("/") + coordinator_path
        if public_base is not None
        else coordinator_path
    )
    ui_html = ui_html.replace("__COORDINATOR_ENDPOINT__", json.dumps(coordinator_url))

    async def list_tools(ctx, params):
        return types.ListToolsResult(tools=list(registry.definitions))

    async def list_resources(ctx, params):
        return types.ListResourcesResult(
            resources=[
                types.Resource(
                    name="Development Bridge Coordinator",
                    uri=COORDINATOR_UI_URI,
                    description="Mounted MCP App for delayed coordinator wake messages",
                    mimeType="text/html;profile=mcp-app",
                    _meta=widget_meta,
                )
            ]
        )

    async def read_resource(ctx, params):
        if str(params.uri) != COORDINATOR_UI_URI:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Unknown resource")
        return types.ReadResourceResult(
            contents=[
                types.TextResourceContents(
                    uri=COORDINATOR_UI_URI,
                    mimeType="text/html;profile=mcp-app",
                    text=ui_html,
                    _meta=widget_meta,
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
