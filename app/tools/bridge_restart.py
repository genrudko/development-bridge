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
        arguments = params.arguments or {}
        requested_channel = arguments.get("channel_id")
        route = container.route_registry.resolve()
        channel_id = (
            container.coordinator.validate_channel(requested_channel)
            if requested_channel is not None
            else (route["channel_id"] if route is not None else None)
        )
        continuation = None

        async def checkpoint() -> None:
            nonlocal continuation
            if channel_id is None:
                return
            continuation = await container.coordinator.arm(
                RESTART_CONTINUATION_MESSAGE,
                channel_id=channel_id,
                delay_seconds=3.0,
                conflict="coalesce",
            )

        data = await container.bridge_restart.schedule(
            checkpoint=checkpoint if channel_id is not None else None
        )
        if channel_id is not None and continuation is not None:
            data["continuation"] = {
                "channel_id": channel_id,
                "state": continuation["state"],
            }
            if requested_channel is None and route is not None:
                data["continuation"]["route_id"] = route["route_id"]
        return to_mcp_result(success(request_context.request_id, data))

    return (
        RegisteredTool(
            types.Tool(
                name="bridge_restart",
                description=(
                    "Schedule guarded idle-only self-restart via a user-systemd trampoline; "
                    "optionally wake an explicit coordinator channel, otherwise the active "
                    "logical route gets the post-restart continuation"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "channel_id": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 64,
                            "pattern": "^[A-Za-z0-9_-]{1,64}$",
                        }
                    },
                    "additionalProperties": False,
                },
            ),
            bridge_restart,
            "v1",
        ),
    )
