from __future__ import annotations

import time
from contextlib import asynccontextmanager

from mcp import types
from mcp.server import Server

from app.api.context import new_request_context
from app.api.errors import BridgeError, ErrorCode
from app.api.results import failure, to_mcp_result
from app.audit import AuditEvent, AuditOutcome
from app.container import ApplicationContainer, build_container
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

    async def list_tools(ctx, params):
        return types.ListToolsResult(tools=list(registry.definitions))

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
    return bridge_server
