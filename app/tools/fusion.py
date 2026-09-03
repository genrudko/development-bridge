from __future__ import annotations

import json

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.container import ApplicationContainer


def fusion_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    def external_result_response(full, metadata, request_id):
        summary = success(request_id, {"external_result": metadata})
        blocks: list[types.ContentBlock] = [
            types.TextContent(
                type="text",
                text=json.dumps(summary.model_dump(mode="json", exclude_none=True), sort_keys=True),
            )
        ]
        for resource in metadata.get("resources", []):
            if not isinstance(resource, dict) or not resource.get("uri"):
                continue
            blocks.append(types.ResourceLink(
                uri=resource["uri"], name=resource["file_name"], title=resource["file_name"],
                mimeType=resource["mime_type"], size=resource["size_bytes"],
                description="Fusion image artifact",
            ))
        if metadata.get("export_url"):
            blocks.append(types.ResourceLink(
                uri=metadata["export_url"], name=metadata["file_name"], title=metadata["file_name"],
                mimeType="application/json", size=metadata["size_bytes"],
                description="Full high-resolution Fusion tool result",
            ))
        return types.CallToolResult(content=blocks, isError=bool(full.get("isError", False)))

    async def status(ctx, params, request_context):
        return to_mcp_result(success(request_context.request_id, container.desktop_nodes.status(params.arguments["node_id"])))

    async def tools(ctx, params, request_context):
        return to_mcp_result(success(request_context.request_id, container.desktop_nodes.tools(params.arguments["node_id"])))

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
            args["node_id"], args["tool_name"], args.get("arguments", {}), args.get("journal")
        )
        return to_mcp_result(success(request_context.request_id, data))

    async def operation_status(ctx, params, request_context):
        args = params.arguments
        data = container.desktop_nodes.operation_status(args["node_id"], args["operation_id"])
        return to_mcp_result(success(request_context.request_id, data))

    async def operation_result(ctx, params, request_context):
        args = params.arguments
        full, metadata = container.desktop_nodes.operation_result(args["node_id"], args["operation_id"])
        return external_result_response(full, metadata, request_context.request_id)

    node = {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"}
    operation_id = {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$"}
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
    common = {"type": "object", "properties": {"node_id": node}, "required": ["node_id"], "additionalProperties": False}
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
    return (
        RegisteredTool(types.Tool(name="fusion_node_status", description="Report whether a registered Windows Fusion node is online", inputSchema=common), status, "fusion-desktop"),
        RegisteredTool(types.Tool(name="fusion_tools", description="List tools dynamically discovered from the node's local Autodesk Fusion MCP", inputSchema=common), tools, "fusion-desktop"),
        RegisteredTool(types.Tool(name="fusion_call", description="Call one dynamically discovered Autodesk Fusion MCP tool synchronously through its outbound Windows node. Prefer fusion_submit for commands that may run longer than the synchronous timeout.", inputSchema=invocation), call, "fusion-desktop"),
        RegisteredTool(types.Tool(name="fusion_submit", description="Queue one dynamically discovered Autodesk Fusion MCP tool and return immediately with an operation_id for long-running work.", inputSchema=invocation), submit, "fusion-desktop"),
        RegisteredTool(types.Tool(name="fusion_operation_status", description="Read the current state of a submitted Fusion operation without replaying it.", inputSchema=operation_lookup), operation_status, "fusion-desktop"),
        RegisteredTool(types.Tool(name="fusion_operation_result", description="Return the completed result and artifact links for a submitted Fusion operation.", inputSchema=operation_lookup), operation_result, "fusion-desktop"),
    )
