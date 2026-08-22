from __future__ import annotations

from mcp import types

from app.api.errors import BridgeError, ErrorCode
from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.container import ApplicationContainer


SOURCE_ID = {"type": "string", "minLength": 1, "maxLength": 200}
MESSAGE_ID = {"type": "string", "minLength": 1, "maxLength": 200}


def knowledge_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    def service():
        if container.knowledge is None:
            raise BridgeError(ErrorCode.KNOWLEDGE_NOT_CONFIGURED, "Community knowledge store is not configured")
        return container.knowledge

    async def source_list(ctx, params, request_context):
        return to_mcp_result(success(request_context.request_id, {"sources": service().source_list()}))

    async def search(ctx, params, request_context):
        arguments = params.arguments
        results = service().search(
            arguments["query"], source_ids=arguments.get("source_ids"),
            date_from=arguments.get("date_from"), date_to=arguments.get("date_to"),
            limit=arguments.get("limit", 20),
        )
        return to_mcp_result(success(request_context.request_id, {"results": results}))

    async def message(ctx, params, request_context):
        arguments = params.arguments
        return to_mcp_result(success(request_context.request_id, service().message(arguments["source_id"], arguments["message_id"])))

    async def thread(ctx, params, request_context):
        arguments = params.arguments
        data = service().thread(
            arguments["source_id"], arguments["message_id"],
            limit=arguments.get("limit", 50), depth=arguments.get("depth", 10),
        )
        return to_mcp_result(success(request_context.request_id, data))

    definitions = (
        ("knowledge_source_list", "List imported community knowledge sources", {}, [], source_list),
        ("knowledge_search", "Full-text search community messages with provenance", {
            "query": {"type": "string", "minLength": 1, "maxLength": 1000},
            "source_ids": {"type": "array", "items": SOURCE_ID, "minItems": 1, "maxItems": 100, "uniqueItems": True},
            "date_from": {"anyOf": [{"type": "string", "format": "date"}, {"type": "string", "format": "date-time"}]},
            "date_to": {"anyOf": [{"type": "string", "format": "date"}, {"type": "string", "format": "date-time"}]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
        }, ["query"], search),
        ("knowledge_message", "Read one community message with reply parent and bounded context", {
            "source_id": SOURCE_ID, "message_id": MESSAGE_ID,
        }, ["source_id", "message_id"], message),
        ("knowledge_thread", "Reconstruct bounded reply ancestors and descendants", {
            "source_id": SOURCE_ID, "message_id": MESSAGE_ID,
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
            "depth": {"type": "integer", "minimum": 0, "maximum": 50, "default": 10},
        }, ["source_id", "message_id"], thread),
    )
    return tuple(
        RegisteredTool(
            types.Tool(name=name, description=description, inputSchema={
                "type": "object", "properties": properties,
                "required": required, "additionalProperties": False,
            }), handler, "community-knowledge",
        )
        for name, description, properties, required, handler in definitions
    )
