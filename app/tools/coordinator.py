from __future__ import annotations

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.container import ApplicationContainer

COORDINATOR_UI_URI = "ui://development-bridge/coordinator-x-v1.html"


def coordinator_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    async def mount(ctx, params, request_context):
        channel_id = container.coordinator.validate_channel(
            (params.arguments or {}).get("channel_id", "coordinator")
        )
        result = to_mcp_result(
            success(
                request_context.request_id,
                {
                    "channel_id": channel_id,
                    "state": "mounted",
                    "external_trigger_enabled": (
                        container.settings.server.x_trigger_token is not None
                    ),
                },
            )
        )
        trigger_path = container.settings.server.endpoint.rstrip("/") + "/x/coordinator/"
        public_base = container.settings.server.public_base_url
        trigger_url = (
            str(public_base).rstrip("/") + trigger_path if public_base is not None else trigger_path
        )
        result.structured_content = {
            "channel_id": channel_id,
            "trigger_url": trigger_url,
        }
        result.meta = {"ui/resourceUri": COORDINATOR_UI_URI}
        return result

    async def continue_(ctx, params, request_context):
        arguments = params.arguments or {}
        data = await container.coordinator.arm(
            arguments["message"],
            channel_id=arguments.get("channel_id", "coordinator"),
            delay_seconds=arguments.get("delay_seconds", 12),
            conflict=arguments.get("conflict", "coalesce"),
        )
        return to_mcp_result(success(request_context.request_id, data))

    common_meta = {"ui/resourceUri": COORDINATOR_UI_URI}
    return (
        RegisteredTool(
            types.Tool(
                name="coordinator_x_mount",
                description="Mount the coordinator wake listener in this chat",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "channel_id": {
                            "type": "string",
                            "pattern": "^[A-Za-z0-9_-]{1,64}$",
                            "default": "coordinator",
                        }
                    },
                    "additionalProperties": False,
                },
                _meta=common_meta,
            ),
            mount,
            "coordinator-x",
        ),
        RegisteredTool(
            types.Tool(
                name="coordinator_continue",
                description="Arm one bounded delayed wake/checkpoint for a mounted channel",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "channel_id": {
                            "type": "string",
                            "pattern": "^[A-Za-z0-9_-]{1,64}$",
                            "default": "coordinator",
                        },
                        "message": {"type": "string", "minLength": 1, "maxLength": 4000},
                        "delay_seconds": {
                            "type": "number", "minimum": 0, "maximum": 300,
                            "default": 12,
                        },
                        "conflict": {
                            "type": "string", "enum": ["coalesce", "reject"],
                            "default": "coalesce",
                        },
                    },
                    "required": ["message"],
                    "additionalProperties": False,
                },
            ),
            continue_,
            "coordinator-x",
        ),
    )
