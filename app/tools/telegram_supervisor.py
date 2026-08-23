from __future__ import annotations

from mcp import types

from app.api.errors import BridgeError, ErrorCode
from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.container import ApplicationContainer


def telegram_supervisor_tools(
    container: ApplicationContainer,
) -> tuple[RegisteredTool, ...]:
    def service():
        if container.telegram_supervisor is None:
            raise BridgeError(
                ErrorCode.TELEGRAM_NOT_CONFIGURED,
                "Telegram supervisor is not configured",
            )
        return container.telegram_supervisor

    async def status(ctx, params, request_context):
        return to_mcp_result(
            success(request_context.request_id, await service().status())
        )

    async def send(ctx, params, request_context):
        return to_mcp_result(
            success(
                request_context.request_id,
                await service().send(params.arguments["text"]),
            )
        )

    return (
        RegisteredTool(
            types.Tool(
                name="telegram_supervisor_status",
                description="Show bound Telegram supervisor and X state",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
            status,
            "telegram-supervisor",
        ),
        RegisteredTool(
            types.Tool(
                name="telegram_send",
                description="Send a reply to the bound Telegram supervisor chat",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "minLength": 1, "maxLength": 3500}
                    },
                    "required": ["text"],
                    "additionalProperties": False,
                },
            ),
            send,
            "telegram-supervisor",
        ),
    )
