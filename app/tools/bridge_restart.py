from __future__ import annotations

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.container import ApplicationContainer


def bridge_restart_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    async def bridge_restart(ctx, params, request_context):
        data = await container.bridge_restart.schedule()
        return to_mcp_result(success(request_context.request_id, data))

    return (
        RegisteredTool(
            types.Tool(
                name="bridge_restart",
                description=(
                    "Schedule guarded idle-only self-restart via a user-systemd trampoline and narrow sudoers bootstrap; reconnect and verify afterward"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
            bridge_restart,
            "v1",
        ),
    )
