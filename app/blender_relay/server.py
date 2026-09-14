from __future__ import annotations

import json
import weakref

from mcp import types
from mcp.server import Server
from pydantic import TypeAdapter, ValidationError

from app.blender_relay.models import thaw_json
from app.blender_relay.service import BlenderRelayService

_CALL_RESULT = TypeAdapter(types.CallToolResult)
_INPUT_REQUIRED = TypeAdapter(types.InputRequiredResult)


def _error(code: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps({"error": code}, separators=(",", ":")))],
        isError=True,
    )


def _adapt_result(relay: BlenderRelayService, payload: dict[str, object]):
    reference = payload.get("external_result")
    metadata = None
    if isinstance(reference, dict):
        payload, metadata = relay.desktop_nodes.external_result(reference)
    if not isinstance(payload, dict):
        raise ValueError("not an MCP result object")
    if payload.get("resultType") == "input_required" and "content" not in payload:
        result = _INPUT_REQUIRED.validate_python(payload)
    else:
        result = _CALL_RESULT.validate_python(payload)
    if metadata is not None and isinstance(result, types.CallToolResult):
        links = []
        for item in metadata.get("resources", []):
            if isinstance(item, dict) and isinstance(item.get("uri"), str):
                links.append(types.ResourceLink(
                    uri=item["uri"], name=str(item.get("file_name", "resource")),
                    title=str(item.get("file_name", "resource")),
                    mimeType=item.get("mime_type") if isinstance(item.get("mime_type"), str) else None,
                    size=item.get("size_bytes") if isinstance(item.get("size_bytes"), int) else None,
                    description="Bridge-owned desktop result resource",
                ))
        if isinstance(metadata.get("export_url"), str):
            links.append(types.ResourceLink(
                uri=metadata["export_url"], name=str(metadata.get("file_name", "result.json")),
                title=str(metadata.get("file_name", "result.json")), mimeType="application/json",
                size=metadata.get("size_bytes") if isinstance(metadata.get("size_bytes"), int) else None,
                description="Bridge-owned full desktop MCP result",
            ))
        result.content.extend(links)
    return result


def create_blender_server(relay: BlenderRelayService) -> Server:
    listed_revisions: weakref.WeakKeyDictionary[object, int] = weakref.WeakKeyDictionary()

    async def list_tools(context, params):
        publication = relay.snapshot()
        listed_revisions[context.session] = publication.surface_revision
        tools = []
        for descriptor in publication.tools:
            evidence = thaw_json(descriptor.publication_metadata)
            tools.append(types.Tool(
                name=descriptor.name,
                title=descriptor.title,
                description=descriptor.description,
                inputSchema=thaw_json(descriptor.input_schema),
                outputSchema=thaw_json(descriptor.output_schema),
                annotations=thaw_json(descriptor.annotations) or None,
                execution=evidence.get("execution"),
                icons=evidence.get("icons"),
                _meta=evidence.get("_meta"),
            ))
        return types.ListToolsResult(tools=tools)

    async def call_tool(context, params):
        publication = relay.snapshot()
        if listed_revisions.get(context.session) != publication.surface_revision:
            return _error("catalog_changed_relist_required")
        try:
            payload = await relay.invoke(params.name, params.arguments or {})
        except (ValidationError, ValueError, TypeError, KeyError):
            return _error("invalid_blender_tool_call")
        except Exception:
            return _error("desktop_relay_unavailable")
        try:
            return _adapt_result(relay, payload)
        except (ValidationError, ValueError, TypeError, KeyError):
            return _error("invalid_desktop_mcp_result")
        except Exception:
            return _error("invalid_desktop_mcp_result")

    return Server("blender-bridge", on_list_tools=list_tools, on_call_tool=call_tool)
