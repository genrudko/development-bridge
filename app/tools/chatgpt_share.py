from __future__ import annotations

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.container import ApplicationContainer


def chatgpt_share_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    async def read(ctx, params, request_context):
        arguments = params.arguments
        data = await container.chatgpt_share.read(
            arguments["url"], mode=arguments.get("mode", "recent"),
            limit=arguments.get("limit"), query=arguments.get("query"),
            max_matches=arguments.get("max_matches", 20),
        )
        return to_mcp_result(success(request_context.request_id, data))

    return (
        RegisteredTool(
            types.Tool(
                name="chatgpt_share_read",
                description="Read visible text from a cookie-free public ChatGPT share in recent/search/full mode; private shares are unsupported",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "minLength": 1, "maxLength": 500},
                        "mode": {"type": "string", "enum": ["recent", "search", "full"], "default": "recent"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 40},
                        "query": {"type": "string", "minLength": 1, "maxLength": 1000},
                        "max_matches": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                    },
                    "required": ["url"],
                    "additionalProperties": False,
                },
            ),
            read,
            "chatgpt-share",
        ),
    )
