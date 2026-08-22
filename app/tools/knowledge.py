from __future__ import annotations

import base64
from urllib.parse import quote

from mcp import types

from app.api.errors import BridgeError, ErrorCode
from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.container import ApplicationContainer


SOURCE_ID = {"type": "string", "minLength": 1, "maxLength": 200}
MESSAGE_ID = {"type": "string", "minLength": 1, "maxLength": 200}
KNOWLEDGE_ATTACHMENT_INLINE_LIMIT = 4 * 1024 * 1024


def knowledge_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    def service():
        if container.knowledge is None:
            raise BridgeError(ErrorCode.KNOWLEDGE_NOT_CONFIGURED, "Community knowledge store is not configured")
        return container.knowledge

    def telegram_service():
        if container.knowledge is None:
            raise BridgeError(ErrorCode.KNOWLEDGE_NOT_CONFIGURED, "Community knowledge store is not configured")
        if container.telegram_knowledge is None:
            raise BridgeError(
                ErrorCode.TELEGRAM_NOT_CONFIGURED,
                "Telegram MTProto credentials and session path are not configured",
            )
        return container.telegram_knowledge

    def attachment_service():
        if container.knowledge_attachments is None:
            raise BridgeError(
                ErrorCode.KNOWLEDGE_NOT_CONFIGURED,
                "Knowledge attachment storage is not configured",
            )
        return container.knowledge_attachments

    def attachment_export_service():
        if container.knowledge_attachment_exports is None:
            raise BridgeError(
                ErrorCode.KNOWLEDGE_NOT_CONFIGURED,
                "Knowledge attachment storage is not configured",
            )
        return container.knowledge_attachment_exports

    async def attachment_export(ctx, params, request_context):
        arguments = params.arguments
        data = await attachment_export_service().export(
            arguments["source_id"], arguments["message_id"],
            arguments["attachment_id"],
        )
        snapshot, path = attachment_service().snapshot_file(
            arguments["source_id"], arguments["message_id"], arguments["attachment_id"]
        )
        response = to_mcp_result(success(request_context.request_id, data))
        response.content.append(types.ResourceLink(
            uri=data["export_url"],
            name=data["file_name"],
            title=data["file_name"],
            mimeType=data["media_type"],
            size=data["size_bytes"],
            description="Short-lived HTTPS link to the immutable attachment snapshot",
        ))
        if snapshot["size_bytes"] <= KNOWLEDGE_ATTACHMENT_INLINE_LIMIT:
            response.content.append(types.EmbeddedResource(
                type="resource",
                resource=types.BlobResourceContents(
                    uri=data["export_url"],
                    mimeType=data["media_type"],
                    blob=base64.b64encode(path.read_bytes()).decode("ascii"),
                ),
            ))
        return response

    async def attachment_open(ctx, params, request_context):
        arguments = params.arguments
        result = await attachment_service().open(
            arguments["source_id"], arguments["message_id"], arguments["attachment_id"]
        )
        base = container.settings.server.endpoint.rstrip("/") + "/knowledge/attachments"
        result.metadata["download_path"] = base + "/" + "/".join(
            quote(arguments[key], safe="")
            for key in ("source_id", "message_id", "attachment_id")
        )
        response = to_mcp_result(success(request_context.request_id, result.metadata))
        if result.text_preview is not None:
            response.content.append(types.TextContent(type="text", text=result.text_preview))
        for frame in result.images:
            response.content.append(
                types.ImageContent(
                    type="image",
                    data=base64.b64encode(frame.data).decode("ascii"),
                    mimeType=frame.media_type,
                )
            )
        return response

    async def source_add(ctx, params, request_context):
        data = await telegram_service().source_add(params.arguments["url"])
        return to_mcp_result(success(request_context.request_id, data))

    async def source_sync(ctx, params, request_context):
        arguments = params.arguments
        data = await telegram_service().source_sync(
            arguments["source_id"], limit=arguments.get("limit")
        )
        return to_mcp_result(success(request_context.request_id, data))

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
        ("knowledge_attachment_export", "Create a short-lived HTTPS export URL for one attachment snapshot", {
            "source_id": SOURCE_ID,
            "message_id": MESSAGE_ID,
            "attachment_id": {"type": "string", "minLength": 1, "maxLength": 200},
        }, ["source_id", "message_id", "attachment_id"], attachment_export),
        ("knowledge_attachment_open", "Open and cache one corpus-validated community attachment", {
            "source_id": SOURCE_ID,
            "message_id": MESSAGE_ID,
            "attachment_id": {"type": "string", "minLength": 1, "maxLength": 200},
        }, ["source_id", "message_id", "attachment_id"], attachment_open),
        ("knowledge_source_add", "Resolve a public Telegram URL and import one bounded history batch", {
            "url": {"type": "string", "minLength": 1, "maxLength": 500},
        }, ["url"], source_add),
        ("knowledge_source_sync", "Continue bounded history or incremental Telegram synchronization", {
            "source_id": SOURCE_ID,
            "limit": {"type": "integer", "minimum": 1, "maximum": 5000},
        }, ["source_id"], source_sync),
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
