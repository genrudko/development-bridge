from __future__ import annotations

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.container import ApplicationContainer


RESTART_CONTINUATION_MESSAGE = (
    "Bridge restart completed; reconnect to the active logical route and continue the pending work."
)


def bridge_restart_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    async def bridge_restart(ctx, params, request_context):
        route = container.route_registry.resolve()
        continuation = None

        async def checkpoint() -> None:
            nonlocal continuation
            if route is None:
                return
            continuation = await container.coordinator.arm(
                RESTART_CONTINUATION_MESSAGE,
                channel_id=route["channel_id"],
                delay_seconds=3.0,
                conflict="coalesce",
            )

        data = await container.bridge_restart.schedule(
            checkpoint=checkpoint if route is not None else None
        )
        if route is not None and continuation is not None:
            data["continuation"] = {
                "route_id": route["route_id"],
                "channel_id": route["channel_id"],
                "state": continuation["state"],
            }
        return to_mcp_result(success(request_context.request_id, data))

    return (
        RegisteredTool(
            types.Tool(
                name="bridge_restart",
                description=(
                    "Schedule guarded idle-only self-restart via a user-systemd trampoline; "
                    "the active logical route gets a durable post-restart continuation wake"
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
