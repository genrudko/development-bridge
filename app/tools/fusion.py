from __future__ import annotations

import json
from typing import Any

from mcp import types
from pydantic import TypeAdapter, ValidationError

from app.api.errors import BridgeError, ErrorCode
from app.api.registry import RegisteredTool
from app.api.results import failure, success, to_mcp_result
from app.container import ApplicationContainer
from app.fusion_cad.errors import (
    FusionCadError,
    format_safe_validation_message,
    sanitize_validation_errors,
)
from app.fusion_cad.models import CadResult
from app.fusion_cad.requests import (
    FusionInspectRequest,
    FusionMetadataRequest,
    FusionReadRequest,
    FusionStyleRequest,
    FusionTransactionRequest,
    FusionValidateRequest,
    FusionViewRequest,
)
from app.fusion_cad.schemas import (
    fusion_inspect_schema,
    fusion_metadata_schema,
    fusion_read_schema,
    fusion_style_schema,
    fusion_transaction_schema,
    fusion_validate_schema,
    fusion_view_schema,
)
from app.fusion_cad.service import FusionCadService


def fusion_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    def external_result_response(full, metadata, request_id):
        is_error = bool(
            (
                ("isError" in full and full["isError"] is not False)
                if isinstance(full, dict)
                else False
            )
            or (
                full.get("status") in ("failed", "error")
                if isinstance(full, dict)
                else False
            )
            or ("error" in full if isinstance(full, dict) else False)
            or FusionCadService._is_error_payload(full)
        )
        if is_error:
            err_code, err_msg, err_details = FusionCadService._extract_error_info(full)
            summary = failure(
                request_id, FusionCadError(err_code, err_msg, details=err_details)
            )
        else:
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
                    description="Fusion image artifact",
                )
            )
        if metadata.get("export_url"):
            blocks.append(
                types.ResourceLink(
                    uri=metadata["export_url"],
                    name=metadata["file_name"],
                    title=metadata["file_name"],
                    mimeType="application/json",
                    size=metadata["size_bytes"],
                    description="Full high-resolution Fusion tool result",
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
        if isinstance(data, dict) and FusionCadService._is_error_payload(data):
            err_code, err_msg, err_details = FusionCadService._extract_error_info(data)
            return to_mcp_result(
                failure(
                    request_context.request_id,
                    FusionCadError(err_code, err_msg, details=err_details),
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
        data = container.desktop_nodes.operation_status(
            args["node_id"], args["operation_id"]
        )
        return to_mcp_result(success(request_context.request_id, data))

    async def operation_result(ctx, params, request_context):
        args = params.arguments
        op_status = container.desktop_nodes.operation_status(
            args["node_id"], args["operation_id"]
        )
        full, metadata = container.desktop_nodes.operation_result(
            args["node_id"], args["operation_id"]
        )
        summary = op_status.get("summary")
        if (
            isinstance(summary, str)
            and getattr(container, "fusion_cad", None)
            and container.fusion_cad.is_domain_summary(summary)
        ):
            finalized = container.fusion_cad.finalize_terminal_operation(
                op_status, full
            )
            if (
                isinstance(finalized, dict)
                and isinstance(finalized.get("external_result"), dict)
            ):
                # A binary domain result (e.g. screenshot) was externalized and
                # its ViewRef image bound to the real emitted ResourceLink URI;
                # render the sanitized finalized payload, not the raw node JSON.
                full, metadata = container.desktop_nodes.external_result(
                    finalized["external_result"]
                )
        elif FusionCadService._is_error_payload(full) or op_status.get("status") in (
            "failed",
            "late_failed",
        ):
            err_code, err_msg, err_details = FusionCadService._extract_error_info(full)
            raise FusionCadError(err_code, err_msg, details=err_details)
        return external_result_response(full, metadata, request_context.request_id)

    def make_domain_handler(request_type: Any, tool_name: str):
        adapter = TypeAdapter(request_type)

        async def domain_handler(ctx, params, request_context):
            args = params.arguments or {}
            val_err: BridgeError | None = None
            try:
                req = adapter.validate_python(args)
            except ValidationError as exc:
                safe_msg = format_safe_validation_message(
                    f"Invalid {tool_name} arguments", exc.errors()
                )
                val_err = FusionCadError(
                    ErrorCode.INVALID_ARGUMENT,
                    safe_msg,
                    details={
                        "validation_errors": sanitize_validation_errors(exc.errors())
                    },
                )
            if val_err is not None:
                raise val_err

            result = await container.fusion_cad.execute(req)
            reference = (
                result.get("external_result") if isinstance(result, dict) else None
            )
            if isinstance(reference, dict):
                full, metadata = container.desktop_nodes.external_result(reference)
                container.fusion_cad.decode_domain_result(full)
                return external_result_response(
                    full, metadata, request_context.request_id
                )
            if isinstance(result, CadResult):
                data = result.model_dump(mode="json", exclude_none=True)
                return to_mcp_result(success(request_context.request_id, data))
            if (
                isinstance(result, dict)
                and "operation_id" in result
                and result.get("status") == "queued"
            ):
                return to_mcp_result(success(request_context.request_id, result))
            safe_int_err = FusionCadError(
                ErrorCode.INTERNAL_ERROR,
                f"Unexpected domain result format from {tool_name}",
                details={"tool_name": tool_name},
            )
            raise safe_int_err

        return domain_handler

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
    return (
        RegisteredTool(
            types.Tool(
                name="fusion_node_status",
                description="Report whether a registered Windows Fusion node is online",
                inputSchema=common,
            ),
            status,
            "fusion-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="fusion_tools",
                description="List tools dynamically discovered from the node's local Autodesk Fusion MCP",
                inputSchema=common,
            ),
            tools,
            "fusion-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="fusion_call",
                description="Call one dynamically discovered Autodesk Fusion MCP tool synchronously through its outbound Windows node. Prefer fusion_submit for commands that may run longer than the synchronous timeout.",
                inputSchema=invocation,
            ),
            call,
            "fusion-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="fusion_submit",
                description="Queue one dynamically discovered Autodesk Fusion MCP tool and return immediately with an operation_id for long-running work.",
                inputSchema=invocation,
            ),
            submit,
            "fusion-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="fusion_operation_status",
                description="Read the current state of a submitted Fusion operation without replaying it.",
                inputSchema=operation_lookup,
            ),
            operation_status,
            "fusion-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="fusion_operation_result",
                description="Return the completed result and artifact links for a submitted Fusion operation.",
                inputSchema=operation_lookup,
            ),
            operation_result,
            "fusion-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="fusion_read",
                description="Semantic model reads, snapshots, feature/sketch reads, revisions, and selectors",
                inputSchema=fusion_read_schema(),
            ),
            make_domain_handler(FusionReadRequest, "fusion_read"),
            "fusion-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="fusion_inspect",
                description="Measurements, geometric relations, and clearance inspections",
                inputSchema=fusion_inspect_schema(),
            ),
            make_domain_handler(FusionInspectRequest, "fusion_inspect"),
            "fusion-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="fusion_view",
                description="Camera control, screenshots, visual pick, sections, and named views",
                inputSchema=fusion_view_schema(),
            ),
            make_domain_handler(FusionViewRequest, "fusion_view"),
            "fusion-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="fusion_metadata",
                description="Model metadata, tags, roles, and CAD entity provenance",
                inputSchema=fusion_metadata_schema(),
            ),
            make_domain_handler(FusionMetadataRequest, "fusion_metadata"),
            "fusion-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="fusion_style",
                description="Parametric 3D/sketch text styling, visibility, and appearances",
                inputSchema=fusion_style_schema(),
            ),
            make_domain_handler(FusionStyleRequest, "fusion_style"),
            "fusion-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="fusion_validate",
                description="CAD model hygiene, reference integrity, and mechanical validation",
                inputSchema=fusion_validate_schema(),
            ),
            make_domain_handler(FusionValidateRequest, "fusion_validate"),
            "fusion-desktop",
        ),
        RegisteredTool(
            types.Tool(
                name="fusion_transaction",
                description="Staged transaction lifecycle, preview diff, rollback, and commit",
                inputSchema=fusion_transaction_schema(),
            ),
            make_domain_handler(FusionTransactionRequest, "fusion_transaction"),
            "fusion-desktop",
        ),
    )
