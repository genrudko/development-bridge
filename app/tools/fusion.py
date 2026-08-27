from __future__ import annotations

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.container import ApplicationContainer


def fusion_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    async def status(ctx, params, request_context):
        return to_mcp_result(success(request_context.request_id, container.desktop_nodes.status(params.arguments["node_id"])))

    async def tools(ctx, params, request_context):
        return to_mcp_result(success(request_context.request_id, container.desktop_nodes.tools(params.arguments["node_id"])))

    async def call(ctx, params, request_context):
        args = params.arguments
        data = await container.desktop_nodes.call(args["node_id"], args["tool_name"], args.get("arguments", {}))
        return to_mcp_result(success(request_context.request_id, data))

    node = {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"}
    common = {"type": "object", "properties": {"node_id": node}, "required": ["node_id"], "additionalProperties": False}
    return (
        RegisteredTool(types.Tool(name="fusion_node_status", description="Report whether a registered Windows Fusion node is online", inputSchema=common), status, "fusion-desktop"),
        RegisteredTool(types.Tool(name="fusion_tools", description="List tools dynamically discovered from the node's local Autodesk Fusion MCP", inputSchema=common), tools, "fusion-desktop"),
        RegisteredTool(types.Tool(name="fusion_call", description="Call one dynamically discovered Autodesk Fusion MCP tool through its outbound Windows node", inputSchema={"type": "object", "properties": {"node_id": node, "tool_name": {"type": "string", "minLength": 1, "maxLength": 200}, "arguments": {"type": "object", "default": {}}}, "required": ["node_id", "tool_name"], "additionalProperties": False}), call, "fusion-desktop"),
    )
