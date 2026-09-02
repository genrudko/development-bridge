from __future__ import annotations

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.container import ApplicationContainer


RESTART_CONTINUATION_MESSAGE = (
    "Bridge restart completed; reconnect to the bound logical route and continue the pending work."
)


def _session_id(ctx) -> str | None:
    session = getattr(ctx, "session", None)
    connection = getattr(session, "_connection", None)
    value = getattr(connection, "session_id", None)
    return str(value) if value else None


def bridge_restart_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    async def bridge_restart(ctx, params, request_context):
        arguments = params.arguments or {}
        requested_channel = arguments.get("channel_id")
        requested_route = arguments.get("route_id")
        route = None
        channel_id = None
        if requested_route is not None:
            route = container.route_registry.resolve(str(requested_route))
            if route is None:
                from app.api.errors import BridgeError, ErrorCode
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {requested_route}")
            channel_id = str(route["channel_id"])
            if requested_channel is not None and requested_channel != channel_id:
                from app.api.errors import BridgeError, ErrorCode
                raise BridgeError(ErrorCode.POLICY_VIOLATION, "route_id and channel_id refer to different destinations")
        elif requested_channel is not None:
            channel_id = container.coordinator.validate_channel(requested_channel)
            route = container.route_registry.route_for_channel(channel_id)
        else:
            binding = container.coordinator.session_binding(_session_id(ctx))
            if binding is not None and binding.get("route_id") is not None:
                route = container.route_registry.resolve(str(binding["route_id"]))
                if route is not None:
                    from app.api.errors import BridgeError, ErrorCode
                    bound_generation = binding.get("generation")
                    current_generation = int(route.get("generation", 0))
                    if bound_generation is not None and int(bound_generation) != current_generation:
                        raise BridgeError(
                            ErrorCode.POLICY_VIOLATION,
                            "This physical chat is bound to a stale route generation; restart continuation suppressed",
                            retryable=True,
                        )
                    if str(binding.get("channel_id")) != str(route["channel_id"]):
                        raise BridgeError(
                            ErrorCode.POLICY_VIOLATION,
                            "This physical chat channel is stale for the bound logical route",
                            retryable=True,
                        )
                    channel_id = str(binding["channel_id"])
            elif binding is not None:
                channel_id = str(binding["channel_id"])
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
            if route is not None and route.get("route_id") is not None:
                data["continuation"]["route_id"] = route["route_id"]
        elif channel_id is None:
            data["continuation_suppressed"] = "no_session_or_explicit_destination"
        return to_mcp_result(success(request_context.request_id, data))

    return (
        RegisteredTool(
            types.Tool(
                name="bridge_restart",
                description=(
                    "Schedule guarded idle-only self-restart via a user-systemd trampoline; "
                    "optionally target a route/channel; otherwise only the current MCP session binding "
                    "receives the post-restart continuation (unbound sessions restart without a wake)"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "route_id": {
                            "type": "string",
                            "pattern": "^[a-z][a-z0-9-]{0,30}$",
                        },
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
