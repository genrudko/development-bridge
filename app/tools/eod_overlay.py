from __future__ import annotations

from mcp import types

from app.api.errors import BridgeError, ErrorCode
from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.container import ApplicationContainer


def eod_overlay_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    async def eod_development_overlay_apply(ctx, params, request_context):
        arguments = params.arguments or {}
        if container.eod_overlay is None:
            raise BridgeError(
                ErrorCode.INTERNAL_ERROR,
                "Development overlay is not configured",
            )
        repository = container.projects.repositories.get("eod", "eod")
        data = await container.eod_overlay.apply(
            repository,
            paths=arguments.get("paths"),
        )
        return to_mcp_result(success(request_context.request_id, data))

    async def eod_development_overlay_rollback(ctx, params, request_context):
        if container.eod_overlay is None:
            raise BridgeError(
                ErrorCode.INTERNAL_ERROR,
                "Development overlay is not configured",
            )
        repository = container.projects.repositories.get("eod", "eod")
        data = await container.eod_overlay.rollback(repository)
        return to_mcp_result(success(request_context.request_id, data))

    return (
        RegisteredTool(
            types.Tool(
                name="eod_development_overlay_apply",
                description=(
                    "Snapshot and apply dirty template and static file additions/modifications "
                    "for registered project eod/repo eod to the local container runtime via a "
                    "user-systemd trampoline without modifying the git index or committed tree."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "paths": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 1024,
                            },
                            "maxItems": 64,
                            "description": "Optional list of dirty template/static file paths to apply. Defaults to all dirty eligible files.",
                        },
                    },
                    "additionalProperties": False,
                },
            ),
            eod_development_overlay_apply,
            "v1",
        ),
        RegisteredTool(
            types.Tool(
                name="eod_development_overlay_rollback",
                description=(
                    "Clear active hot-refresh overlay files in the local EOD container runtime "
                    "via the user-systemd trampoline."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
            eod_development_overlay_rollback,
            "v1",
        ),
    )

