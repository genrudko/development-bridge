from __future__ import annotations

import time
from pathlib import Path
from contextlib import asynccontextmanager

from mcp import types
from mcp.server import Server
from mcp.server.subscriptions import ListenHandler

from app.api.context import new_request_context
from app.api.errors import BridgeError, ErrorCode
from app.api.results import failure, success, to_mcp_result
from app.audit import AuditEvent, AuditOutcome
from app.container import ApplicationContainer, build_container
from app.tools.registry import build_tool_registry
from app.tools.probe import note_resources_list, note_resources_read, note_tools_list, subscription_bus


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

    bridge_server = Server(
        application.settings.server.name,
        lifespan=lifespan,
        on_subscriptions_listen=ListenHandler(subscription_bus()),
    )
    bridge_server.extensions["io.modelcontextprotocol/ui"] = {
        "mimeTypes": ["text/html;profile=mcp-app"]
    }

    async def list_tools(ctx, params):
        note_tools_list()
        return types.ListToolsResult(tools=list(registry.definitions))

    ui_uri = "ui://x-test/external-trigger-v1.html"
    ui_html = Path(__file__).with_name("x_ui.html").read_text(encoding="utf-8")
    widget_meta = {
        "ui": {
            "csp": {
                "connectDomains": ["https://mcp.vigilante.website"],
                "resourceDomains": ["https://unpkg.com"],
            },
            "domain": "https://mcp.vigilante.website",
        },
        "openai/widgetCSP": {
            "connect_domains": ["https://mcp.vigilante.website"],
            "resource_domains": ["https://unpkg.com"],
        },
        "openai/widgetDomain": "https://mcp.vigilante.website",
    }

    async def list_resources(ctx, params):
        note_resources_list()
        return types.ListResourcesResult(resources=[types.Resource(
            name="X UI Message Probe", uri=ui_uri,
            description="MCP App ui/message async probe",
            mimeType="text/html;profile=mcp-app",
            _meta=widget_meta,
        )])

    async def read_resource(ctx, params):
        note_resources_read()
        if str(params.uri) != ui_uri:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Unknown resource")
        return types.ReadResourceResult(contents=[types.TextResourceContents(
            uri=ui_uri, mimeType="text/html;profile=mcp-app", text=ui_html,
            _meta=widget_meta,
        )])

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
            if params.name == "sampling_probe" and arguments.get("mode") == "during_call":
                responses = params.input_responses or {}
                if "sample" in responses:
                    response = responses["sample"]
                    data = {
                        "mode": "mrtr_sampling",
                        "status": "completed",
                        "request_state": params.request_state,
                        "sample": response.model_dump(mode="json", by_alias=True, exclude_none=True),
                    }
                    return to_mcp_result(success(request_context.request_id, data))
                return types.InputRequiredResult(
                    input_requests={
                        "sample": types.CreateMessageRequest(
                            params=types.CreateMessageRequestParams(
                                messages=[types.SamplingMessage(
                                    role="user",
                                    content=types.TextContent(type="text", text="Reply with exactly MRTR_SAMPLING_OK and nothing else."),
                                )],
                                max_tokens=32,
                            )
                        )
                    },
                    request_state="mrtr-sampling-probe-v1",
                )
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
