from __future__ import annotations

import json
from typing import Any

from mcp import types

from app.api.errors import BridgeError, ErrorCode
from app.api.registry import RegisteredTool
from app.api.results import failure, success, to_mcp_result
from app.container import ApplicationContainer


def _payload_error(value: Any) -> str | None:
    """Recognize Visio MCP errors even when the upstream tool returned isError=false."""
    if not isinstance(value, dict):
        return None

    if value.get("isError") is True:
        return "Visio MCP reported a tool error"

    content = value.get("content")
    if not isinstance(content, list):
        return None

    for block in content:
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        text = block.get("text")
        if not isinstance(text, str):
            continue
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict) and parsed.get("error"):
            return str(parsed["error"])

    return None


def visio_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
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

        upstream_error = _payload_error(data)
        if upstream_error is not None:
            return to_mcp_result(
                failure(
                    request_context.request_id,
                    BridgeError(
                        ErrorCode.INTERNAL_ERROR,
                        upstream_error,
                        details={"tool_name": args["tool_name"]},
                    ),
                )
            )

        reference = data.get("external_result") if isinstance(data, dict) else None
        if isinstance(reference, dict):
            full, metadata = container.desktop_nodes.external_result(reference)
            upstream_error = _payload_error(full)
            if upstream_error is not None:
                return to_mcp_result(
                    failure(
                        request_context.request_id,
                        BridgeError(
                            ErrorCode.INTERNAL_ERROR,
                            upstream_error,
                            details={"tool_name": args["tool_name"]},
                        ),
                    )
                )
            return to_mcp_result(
                success(
                    request_context.request_id,
                    {"result": full, "artifact": metadata},
                )
            )

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
        return to_mcp_result(
            success(
                request_context.request_id,
                container.desktop_nodes.operation_status(
                    args["node_id"], args["operation_id"]
                ),
            )
        )

    async def operation_result(ctx, params, request_context):
        args = params.arguments
        full, metadata = container.desktop_nodes.operation_result(
            args["node_id"], args["operation_id"]
        )
        upstream_error = _payload_error(full)
        if upstream_error is not None:
            return to_mcp_result(
                failure(
                    request_context.request_id,
                    BridgeError(
                        ErrorCode.INTERNAL_ERROR,
                        upstream_error,
                        details={"operation_id": args["operation_id"]},
                    ),
                )
            )
        return to_mcp_result(
            success(
                request_context.request_id,
                {"result": full, "artifact": metadata},
            )
        )

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
        "properties": {
            "node_id": node,
            "operation_id": operation_id,
        },
        "required": ["node_id", "operation_id"],
        "additionalProperties": False,
    }

    return (
        RegisteredTool(
            types.Tool(
                name="visio_node_status",
                description="Report whether a registered Windows Visio node is online.",
                inputSchema=common,
            ),
            status,
            "visio-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="visio_tools",
                description="List tools dynamically discovered from the node's local Microsoft Visio MCP.",
                inputSchema=common,
            ),
            tools,
            "visio-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="visio_call",
                description="Call one dynamically discovered Microsoft Visio MCP tool synchronously through its outbound Windows node.",
                inputSchema=invocation,
            ),
            call,
            "visio-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="visio_submit",
                description="Queue one dynamically discovered Microsoft Visio MCP tool and return an operation_id for asynchronous work.",
                inputSchema=invocation,
            ),
            submit,
            "visio-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="visio_operation_status",
                description="Read the current state of a submitted Visio operation without replaying it.",
                inputSchema=operation_lookup,
            ),
            operation_status,
            "visio-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="visio_operation_result",
                description="Return the completed result for a submitted Visio operation.",
                inputSchema=operation_lookup,
            ),
            operation_result,
            "visio-desktop",
        ),
    )
