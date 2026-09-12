from __future__ import annotations

import json

from mcp import types
from mcp.server.mcpserver.utilities.types import Image

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.container import ApplicationContainer


def blender_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    def external_result_response(full, metadata, request_id):
        summary = success(request_id, {"external_result": metadata})
        blocks: list[types.ContentBlock] = [
            types.TextContent(
                type="text",
                text=json.dumps(
                    summary.model_dump(mode="json", exclude_none=True), sort_keys=True
                ),
            )
        ]
        for resource in metadata.get("resources", []):
            if not isinstance(resource, dict) or not resource.get("uri"):
                continue
            blocks.append(
                types.ResourceLink(
                    uri=resource["uri"],
                    name=resource["file_name"],
                    title=resource["file_name"],
                    mimeType=resource["mime_type"],
                    size=resource["size_bytes"],
                    description="Blender Hub result artifact",
                )
            )
        if metadata.get("export_url"):
            blocks.append(
                types.ResourceLink(
                    uri=metadata["export_url"],
                    name=metadata["file_name"],
                    title=metadata["file_name"],
                    mimeType=metadata.get("mime_type", "application/json"),
                    size=metadata["size_bytes"],
                    description="Full Blender Hub tool result",
                )
            )
        return types.CallToolResult(content=blocks, isError=False)

    async def status(ctx, params, request_context):
        return to_mcp_result(
            success(
                request_context.request_id,
                container.desktop_nodes.status(params.arguments["node_id"]),
            )
        )

    async def tools(ctx, params, request_context):
        return to_mcp_result(
            success(
                request_context.request_id,
                container.desktop_nodes.tools(params.arguments["node_id"]),
            )
        )

    async def call(ctx, params, request_context):
        args = params.arguments
        data = await container.desktop_nodes.call(
            args["node_id"],
            args["tool_name"],
            args.get("arguments", {}),
            args.get("journal"),
        )
        reference = data.get("external_result") if isinstance(data, dict) else None
        if isinstance(reference, dict):
            full, metadata = container.desktop_nodes.external_result(reference)
            return external_result_response(full, metadata, request_context.request_id)
        return to_mcp_result(success(request_context.request_id, data))

    async def submit(ctx, params, request_context):
        args = params.arguments
        data = await container.desktop_nodes.submit(
            args["node_id"],
            args["tool_name"],
            args.get("arguments", {}),
            args.get("journal"),
        )
        return to_mcp_result(success(request_context.request_id, data))

    async def operation_status(ctx, params, request_context):
        args = params.arguments
        data = container.desktop_nodes.operation_status(
            args["node_id"], args["operation_id"]
        )
        return to_mcp_result(success(request_context.request_id, data))

    async def operation_result(ctx, params, request_context):
        args = params.arguments
        full, metadata = container.desktop_nodes.operation_result(
            args["node_id"], args["operation_id"]
        )
        return external_result_response(full, metadata, request_context.request_id)

    async def result_view(ctx, params, request_context):
        image_bytes, metadata = container.desktop_nodes.external_image_resource(
            params.arguments["resource_uri"]
        )
        result = to_mcp_result(
            success(request_context.request_id, {"resource": metadata})
        )
        image_format = {
            "image/png": "png",
            "image/jpeg": "jpeg",
            "image/webp": "webp",
        }[metadata["mime_type"]]
        result.content.append(
            Image(data=image_bytes, format=image_format).to_image_content()
        )
        return result

    async def operator_ask(ctx, params, request_context):
        args = params.arguments
        payload = {
            "question": args["question"],
            "choices": args.get("choices", []),
        }
        if args.get("operation_id") is not None:
            payload["operation_id"] = args["operation_id"]
        data = await container.desktop_nodes.call(
            args["node_id"],
            "operator.ask",
            payload,
            {
                "summary": "Blender Hub same-turn operator prompt",
                "mutation": False,
            },
        )
        return to_mcp_result(success(request_context.request_id, data))

    node = {
        "type": "string",
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
    }
    operation_id = {
        "type": "string",
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$",
    }
    journal = {
        "type": "object",
        "properties": {
            "operation_id": operation_id,
            "summary": {"type": "string", "minLength": 1, "maxLength": 300},
            "mutation": {"type": "boolean"},
            "parent_operation_id": operation_id,
            "checkpoint": {"type": "object"},
        },
        "additionalProperties": False,
    }
    common = {
        "type": "object",
        "properties": {"node_id": node},
        "required": ["node_id"],
        "additionalProperties": False,
    }
    invocation = {
        "type": "object",
        "properties": {
            "node_id": node,
            "tool_name": {"type": "string", "minLength": 1, "maxLength": 200},
            "arguments": {"type": "object", "default": {}},
            "journal": journal,
        },
        "required": ["node_id", "tool_name"],
        "additionalProperties": False,
    }
    operation_lookup = {
        "type": "object",
        "properties": {"node_id": node, "operation_id": operation_id},
        "required": ["node_id", "operation_id"],
        "additionalProperties": False,
    }
    result_view_schema = {
        "type": "object",
        "properties": {
            "resource_uri": {"type": "string", "minLength": 1, "maxLength": 2048}
        },
        "required": ["resource_uri"],
        "additionalProperties": False,
    }
    operator_ask_schema = {
        "type": "object",
        "properties": {
            "node_id": node,
            "question": {"type": "string", "minLength": 1, "maxLength": 2000},
            "choices": {
                "type": "array",
                "items": {"type": "string", "minLength": 1, "maxLength": 300},
                "maxItems": 20,
                "default": [],
            },
            "operation_id": operation_id,
        },
        "required": ["node_id", "question"],
        "additionalProperties": False,
    }

    return (
        RegisteredTool(
            types.Tool(
                name="blender_node_status",
                description="Report whether a registered Windows Blender Hub node is online",
                inputSchema=common,
            ),
            status,
            "blender-hub",
        ),
        RegisteredTool(
            types.Tool(
                name="blender_tools",
                description="List namespaced tools dynamically advertised by the Windows Blender Hub",
                inputSchema=common,
            ),
            tools,
            "blender-hub",
        ),
        RegisteredTool(
            types.Tool(
                name="blender_call",
                description="Call one namespaced Blender Hub provider tool synchronously through the outbound Windows node",
                inputSchema=invocation,
            ),
            call,
            "blender-hub",
        ),
        RegisteredTool(
            types.Tool(
                name="blender_submit",
                description="Queue one namespaced Blender Hub provider tool for long-running work and return an operation_id",
                inputSchema=invocation,
            ),
            submit,
            "blender-hub",
        ),
        RegisteredTool(
            types.Tool(
                name="blender_operation_status",
                description="Read a submitted Blender Hub operation state without replaying it",
                inputSchema=operation_lookup,
            ),
            operation_status,
            "blender-hub",
        ),
        RegisteredTool(
            types.Tool(
                name="blender_operation_result",
                description="Return the retained result and artifact links for a completed Blender Hub operation",
                inputSchema=operation_lookup,
            ),
            operation_result,
            "blender-hub",
        ),
        RegisteredTool(
            types.Tool(
                name="blender_result_view",
                description="View one previously returned Blender Hub image resource directly as MCP image content",
                inputSchema=result_view_schema,
            ),
            result_view,
            "blender-hub",
        ),
        RegisteredTool(
            types.Tool(
                name="blender_operator_ask",
                description="Ask the Windows Blender operator a blocking same-turn question; this MCP call returns only after the operator answers, cancels, or the node fails",
                inputSchema=operator_ask_schema,
            ),
            operator_ask,
            "blender-hub",
        ),
    )
