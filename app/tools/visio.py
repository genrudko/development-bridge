from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from mcp import types
from mcp.server.mcpserver.utilities.types import Image

from app.api.errors import BridgeError, ErrorCode
from app.api.registry import RegisteredTool
from app.api.results import failure, success, to_mcp_result
from app.container import ApplicationContainer


VISIO_MANAGED_UPDATE_TOOL = "__openai_visio_managed_update"
VISIO_MANAGED_EXTENSION_VERSION = "2026.10.03.20"
VISIO_MANAGED_EXTENSION_PATH = (
    Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_managed_extension.py"
)
VISIO_CONSOLE_SOURCE_PATH = (
    Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_bridge_console.pyw"
)

VISIO_READ_ONLY_TOOLS = frozenset({
    "list_open_documents",
    "list_pages",
    "list_shapes",
    "get_shape_info",
    "get_connections",
    "get_page_summary",
    "read_shape_data",
    "list_stencils",
    "list_masters",
    "list_diagram_types",
    "get_diagram_standard",
    "inspect_shape_state_model",
    "read_shape_cells",
    "batch_read_shape_cells",
    "inspect_master_state_model",
    "get_page_setup",
    "get_vtd_state",
    "render_page_png",
    "read_connection_points",
    "operator_notes_peek",
    "open_document",
    "open_stencil",
})
VISIO_BLOCKED_TOOLS = frozenset({"save_document", VISIO_MANAGED_UPDATE_TOOL})


def _validate_visio_invocation(arguments: dict[str, Any]) -> None:
    tool_name = str(arguments["tool_name"])
    if tool_name in VISIO_BLOCKED_TOOLS:
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "In-place Visio save is disabled; use save_document_as inside the approved workspace",
            details={"tool_name": tool_name},
        )
    if tool_name in VISIO_READ_ONLY_TOOLS:
        return
    journal = arguments.get("journal")
    if not isinstance(journal, dict) or journal.get("mutation") is not True:
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "Visio mutation requires journal.mutation=true",
            details={"tool_name": tool_name},
        )


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
    def external_result_response(full, metadata, request_id):
        upstream_error = _payload_error(full)
        is_error = upstream_error is not None
        if is_error:
            summary = failure(
                request_id,
                BridgeError(ErrorCode.INTERNAL_ERROR, upstream_error or "Visio snapshot failed"),
            )
        else:
            summary = success(request_id, {"external_result": metadata})
        blocks: list[types.ContentBlock] = [
            types.TextContent(
                type="text",
                text=json.dumps(
                    summary.model_dump(mode="json", exclude_none=True),
                    ensure_ascii=False,
                    sort_keys=True,
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
                    description="Visio rendered page image",
                )
            )
        return types.CallToolResult(content=blocks, isError=is_error)

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

    async def invoke(
        request_context,
        *,
        node_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        journal_data: dict[str, Any] | None = None,
    ):
        invocation = {
            "node_id": node_id,
            "tool_name": tool_name,
            "arguments": arguments or {},
        }
        if journal_data is not None:
            invocation["journal"] = journal_data
        _validate_visio_invocation(invocation)

        data = await container.desktop_nodes.call(
            node_id,
            tool_name,
            arguments or {},
            journal_data,
        )

        upstream_error = _payload_error(data)
        if upstream_error is not None:
            return to_mcp_result(
                failure(
                    request_context.request_id,
                    BridgeError(
                        ErrorCode.INTERNAL_ERROR,
                        upstream_error,
                        details={"tool_name": tool_name},
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
                            details={"tool_name": tool_name},
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

    async def call(ctx, params, request_context):
        args = params.arguments
        return await invoke(
            request_context,
            node_id=args["node_id"],
            tool_name=args["tool_name"],
            arguments=args.get("arguments", {}),
            journal_data=args.get("journal"),
        )

    async def list_open_documents_explicit(ctx, params, request_context):
        return await invoke(
            request_context,
            node_id=params.arguments["node_id"],
            tool_name="list_open_documents",
        )

    async def list_diagram_types_explicit(ctx, params, request_context):
        return await invoke(
            request_context,
            node_id=params.arguments["node_id"],
            tool_name="list_diagram_types",
        )

    async def snapshot_explicit(ctx, params, request_context):
        args = params.arguments
        invocation = {
            "node_id": args["node_id"],
            "tool_name": "render_page_png",
            "arguments": {
                "doc_name": args.get("doc_name", ""),
                "page": args.get("page", ""),
            },
        }
        _validate_visio_invocation(invocation)
        data = await container.desktop_nodes.call(
            args["node_id"],
            "render_page_png",
            invocation["arguments"],
            None,
        )
        upstream_error = _payload_error(data)
        if upstream_error is not None:
            return to_mcp_result(
                failure(
                    request_context.request_id,
                    BridgeError(
                        ErrorCode.INTERNAL_ERROR,
                        upstream_error,
                        details={"tool_name": "render_page_png"},
                    ),
                )
            )
        reference = data.get("external_result") if isinstance(data, dict) else None
        if not isinstance(reference, dict):
            return to_mcp_result(
                failure(
                    request_context.request_id,
                    BridgeError(
                        ErrorCode.INTERNAL_ERROR,
                        "Visio snapshot was not externalized as an image resource",
                        details={"tool_name": "render_page_png"},
                    ),
                )
            )
        full, metadata = container.desktop_nodes.external_result(reference)
        return external_result_response(full, metadata, request_context.request_id)

    async def result_view_explicit(ctx, params, request_context):
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

    async def operator_notes_explicit(ctx, params, request_context):
        args = params.arguments
        return await invoke(
            request_context,
            node_id=args["node_id"],
            tool_name="operator_notes_peek",
            arguments={"limit": args.get("limit", 20)},
        )

    async def operator_ack_explicit(ctx, params, request_context):
        args = params.arguments
        return await invoke(
            request_context,
            node_id=args["node_id"],
            tool_name="operator_notes_ack",
            arguments={"note_ids_json": json.dumps(args["note_ids"], ensure_ascii=False)},
            journal_data={
                "mutation": True,
                "summary": "Acknowledge operator notes delivered through Visio Bridge Console",
            },
        )

    async def operator_reply_explicit(ctx, params, request_context):
        args = params.arguments
        return await invoke(
            request_context,
            node_id=args["node_id"],
            tool_name="operator_reply_send",
            arguments={
                "text": args["text"],
                "note_ids_json": json.dumps(args.get("note_ids", []), ensure_ascii=False),
            },
            journal_data={
                "mutation": True,
                "summary": "Send a reply to Visio Bridge Console operator chat",
            },
        )

    async def console_install_explicit(ctx, params, request_context):
        return await invoke(
            request_context,
            node_id=params.arguments["node_id"],
            tool_name="install_bridge_console",
            journal_data={
                "mutation": True,
                "summary": "Install or update the server-pinned Visio Bridge Console",
            },
        )

    async def managed_update_explicit(ctx, params, request_context):
        node_id = params.arguments["node_id"]
        raw = VISIO_MANAGED_EXTENSION_PATH.read_bytes()
        console_b64 = base64.b64encode(VISIO_CONSOLE_SOURCE_PATH.read_bytes())
        raw = raw.replace(b"__CONSOLE_SOURCE_B64__", console_b64)
        digest = hashlib.sha256(raw).hexdigest()
        data = await container.desktop_nodes.call(
            node_id,
            VISIO_MANAGED_UPDATE_TOOL,
            {
                "version": VISIO_MANAGED_EXTENSION_VERSION,
                "file_name": "visio_managed_extension.py",
                "content_b64": base64.b64encode(raw).decode("ascii"),
                "sha256": digest,
            },
            {
                "mutation": True,
                "summary": (
                    "Apply server-pinned managed Visio extension "
                    + VISIO_MANAGED_EXTENSION_VERSION
                ),
            },
        )
        upstream_error = _payload_error(data)
        if upstream_error is not None:
            return to_mcp_result(
                failure(
                    request_context.request_id,
                    BridgeError(
                        ErrorCode.INTERNAL_ERROR,
                        upstream_error,
                        details={"tool_name": VISIO_MANAGED_UPDATE_TOOL},
                    ),
                )
            )
        return to_mcp_result(
            success(
                request_context.request_id,
                {
                    "version": VISIO_MANAGED_EXTENSION_VERSION,
                    "sha256": digest,
                    "result": data,
                },
            )
        )

    async def submit(ctx, params, request_context):
        args = params.arguments
        _validate_visio_invocation(args)
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

    snapshot_schema = {
        "type": "object",
        "properties": {
            "node_id": node,
            "doc_name": {"type": "string", "maxLength": 260, "default": ""},
            "page": {"type": "string", "maxLength": 200, "default": ""},
        },
        "required": ["node_id"],
        "additionalProperties": False,
    }
    resource_view_schema = {
        "type": "object",
        "properties": {
            "resource_uri": {"type": "string", "minLength": 1, "maxLength": 2048},
        },
        "required": ["resource_uri"],
        "additionalProperties": False,
    }

    operator_notes_schema = {
        "type": "object",
        "properties": {
            "node_id": node,
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
        },
        "required": ["node_id"],
        "additionalProperties": False,
    }
    note_id_schema = {
        "type": "string",
        "pattern": "^note-[0-9a-f]{32}$",
    }
    operator_ack_schema = {
        "type": "object",
        "properties": {
            "node_id": node,
            "note_ids": {"type": "array", "items": note_id_schema, "maxItems": 100},
        },
        "required": ["node_id", "note_ids"],
        "additionalProperties": False,
    }
    operator_reply_schema = {
        "type": "object",
        "properties": {
            "node_id": node,
            "text": {"type": "string", "minLength": 1, "maxLength": 8000},
            "note_ids": {"type": "array", "items": note_id_schema, "maxItems": 100, "default": []},
        },
        "required": ["node_id", "text"],
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
                name="visio_list_open_documents",
                description="List open documents in the live attached Microsoft Visio instance.",
                inputSchema=common,
            ),
            list_open_documents_explicit,
            "visio-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="visio_list_diagram_types",
                description="List diagram types supported by the local Microsoft Visio MCP.",
                inputSchema=common,
            ),
            list_diagram_types_explicit,
            "visio-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="visio_snapshot",
                description="Render the current or selected Visio page and expose it as an image resource for visual inspection.",
                inputSchema=snapshot_schema,
            ),
            snapshot_explicit,
            "visio-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="visio_result_view",
                description="Resolve a Visio snapshot image resource URI and return the actual image content.",
                inputSchema=resource_view_schema,
            ),
            result_view_explicit,
            "visio-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="visio_operator_notes",
                description="Read pending operator messages from the local Visio Bridge Console side-channel without acknowledging them.",
                inputSchema=operator_notes_schema,
            ),
            operator_notes_explicit,
            "visio-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="visio_operator_ack",
                description="Acknowledge operator messages after they have been read or acted upon.",
                inputSchema=operator_ack_schema,
            ),
            operator_ack_explicit,
            "visio-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="visio_operator_reply",
                description="Send a short reply back to the Visio Bridge Console operator chat.",
                inputSchema=operator_reply_schema,
            ),
            operator_reply_explicit,
            "visio-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="visio_console_install",
                description="Install or update the server-pinned Visio Bridge Console desktop utility on the Windows node.",
                inputSchema=common,
            ),
            console_install_explicit,
            "visio-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="visio_managed_update",
                description="Apply the server-pinned managed Visio extension bundle to the Windows node. No arbitrary code or path input is accepted.",
                inputSchema=common,
            ),
            managed_update_explicit,
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
