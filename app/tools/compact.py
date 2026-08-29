from __future__ import annotations

import os
import re
import shutil
import time
from types import SimpleNamespace
from typing import Any

from mcp import types
from jsonschema import ValidationError, validate

from app.api.errors import BridgeError, ErrorCode
from app.api.registry import RegisteredTool, ToolRegistry
from app.api.results import success, to_mcp_result
from app.audit import AuditEvent, AuditOutcome
from app.container import ApplicationContainer

BRIDGE_DASHBOARD_UI_URI = "ui://development-bridge/dashboard-v1.html"
BRIDGE_DASHBOARD_UI_META = {
    "ui": {"resourceUri": BRIDGE_DASHBOARD_UI_URI},
    "ui/resourceUri": BRIDGE_DASHBOARD_UI_URI,
    "openai/outputTemplate": BRIDGE_DASHBOARD_UI_URI,
}

COMPACT_VISIBLE_TOOLS = (
    "bridge_guide",
    "bridge_dashboard",
    "bridge_search",
    "bridge_schema",
    "bridge_call",
    "run_command",
    "repository_exec",
    "job_status",
    "job_output",
    "bridge_restart",
    "coordinator_x_mount",
    "coordinator_ack",
    "coordinator_exec_and_wake",
    "coordinator_wake_on_jobs",
)

_COMPACT_META_TOOLS = {"bridge_dashboard", "bridge_search", "bridge_schema", "bridge_call"}


def _category(name: str) -> str:
    if name.startswith("github_"):
        return "github"
    if name.startswith("knowledge_"):
        return "knowledge"
    if name.startswith("coordinator_"):
        return "coordinator"
    if name.startswith("job_") or name in {"repository_exec", "task_list", "task_start"}:
        return "jobs"
    if name.startswith("git_"):
        return "git"
    if name.startswith("file_"):
        return "files"
    if name.startswith("change_"):
        return "changes"
    if name.startswith("project_") or name in {"repository_status", "repository_clone"}:
        return "projects"
    if name.startswith("eod_browser_"):
        return "browser"
    if name.startswith("fusion_"):
        return "fusion"
    if name == "chatgpt_share_read":
        return "chatgpt-share"
    if name == "run_command":
        return "commands"
    return "bridge"


def exposed_tool_definitions(registry: ToolRegistry, surface: str) -> tuple[types.Tool, ...]:
    if surface != "compact":
        return registry.definitions
    definitions = {tool.name: tool for tool in registry.definitions}
    return tuple(definitions[name] for name in COMPACT_VISIBLE_TOOLS if name in definitions)


def _schema_summary(schema: dict[str, Any]) -> dict[str, Any]:
    properties = schema.get("properties") or {}
    return {
        "required": list(schema.get("required") or []),
        "properties": list(properties)[:24],
    }


def _memory_snapshot() -> dict[str, float | int]:
    values: dict[str, int] = {}
    try:
        for line in open("/proc/meminfo", encoding="utf-8"):
            key, raw = line.split(":", 1)
            if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
                values[key] = int(raw.strip().split()[0]) * 1024
    except OSError:
        return {}
    gib = 1024**3
    return {
        "total_gib": round(values.get("MemTotal", 0) / gib, 2),
        "available_gib": round(values.get("MemAvailable", 0) / gib, 2),
        "swap_used_gib": round((values.get("SwapTotal", 0) - values.get("SwapFree", 0)) / gib, 2),
    }


def compact_tools(container: ApplicationContainer, registry: ToolRegistry) -> tuple[RegisteredTool, ...]:
    async def bridge_search(ctx, params, request_context):
        arguments = params.arguments or {}
        query = str(arguments.get("query") or "").strip().lower()
        category = str(arguments.get("category") or "all").strip().lower()
        limit = max(1, min(int(arguments.get("limit", 12)), 40))
        tokens = [token for token in re.split(r"[^a-z0-9_]+", query) if token]
        rows: list[tuple[int, dict[str, Any]]] = []
        for tool in registry.definitions:
            if tool.name in _COMPACT_META_TOOLS:
                continue
            tool_category = _category(tool.name)
            if category != "all" and tool_category != category:
                continue
            haystack = f"{tool.name} {tool.description or ''}".lower()
            if tokens and not all(token in haystack for token in tokens):
                continue
            score = sum(4 if token in tool.name.lower() else 1 for token in tokens)
            rows.append((score, {
                "name": tool.name,
                "category": tool_category,
                "purpose": tool.description or "",
                "schema": _schema_summary(tool.input_schema or {}),
            }))
        rows.sort(key=lambda item: (-item[0], item[1]["name"]))
        return to_mcp_result(success(request_context.request_id, {
            "query": query,
            "category": category,
            "matches": [row for _, row in rows[:limit]],
            "hint": "Use bridge_schema for the exact JSON schema, then bridge_call.",
        }))

    async def bridge_schema(ctx, params, request_context):
        name = str((params.arguments or {}).get("tool_name") or "")
        registered = registry.get(name)
        if registered is None or name in _COMPACT_META_TOOLS:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown delegated tool: {name}")
        tool = registered.definition
        return to_mcp_result(success(request_context.request_id, {
            "name": tool.name,
            "category": _category(tool.name),
            "purpose": tool.description or "",
            "input_schema": tool.input_schema,
            "meta": tool.meta or {},
        }))

    async def bridge_call(ctx, params, request_context):
        arguments = params.arguments or {}
        name = str(arguments.get("tool_name") or "")
        if name in _COMPACT_META_TOOLS:
            raise BridgeError(ErrorCode.POLICY_VIOLATION, "compact meta-tools cannot delegate to themselves")
        registered = registry.get(name)
        if registered is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown delegated tool: {name}")
        delegated_arguments = arguments.get("arguments") or {}
        if not isinstance(delegated_arguments, dict):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "arguments must be an object")
        try:
            validate(instance=delegated_arguments, schema=registered.definition.input_schema or {})
        except ValidationError as exc:
            path = ".".join(str(item) for item in exc.absolute_path)
            location = f" at {path}" if path else ""
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                f"invalid arguments for {name}{location}: {exc.message}",
            ) from exc

        delegated = SimpleNamespace(name=name, arguments=delegated_arguments)
        started = time.perf_counter()
        outcome = AuditOutcome.SUCCESS
        error_code = None
        try:
            return await registered.handler(ctx, delegated, request_context)
        except BridgeError as error:
            outcome = AuditOutcome.ERROR
            error_code = error.code.value
            raise
        except Exception:
            outcome = AuditOutcome.ERROR
            error_code = ErrorCode.INTERNAL_ERROR.value
            raise
        finally:
            audit = getattr(container, "audit", None)
            if audit is not None:
                await audit.emit(AuditEvent(
                    request_id=request_context.request_id,
                    tool=name,
                    outcome=outcome,
                    duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                    project_id=delegated_arguments.get("project_id"),
                    repository_id=delegated_arguments.get("repository_id"),
                    error_code=error_code,
                    event="delegated_via_bridge_call",
                ))

    async def bridge_dashboard(ctx, params, request_context):
        disk = shutil.disk_usage("/")
        mem = _memory_snapshot()
        visible = exposed_tool_definitions(registry, "compact")
        route = container.route_registry.resolve()
        data = {
            "status": "online",
            "name": container.settings.server.name,
            "version": "1.0.0",
            "api_version": "1.0",
            "tool_surface": "compact",
            "visible_tools": len(visible),
            "internal_tools": len(registry.definitions),
            "projects": len(container.projects.list()),
            "disk": {
                "total_gib": round(disk.total / 1024**3, 1),
                "free_gib": round(disk.free / 1024**3, 1),
                "used_percent": round((disk.used / disk.total) * 100, 1) if disk.total else 0,
            },
            "memory": mem,
            "load": [round(value, 2) for value in os.getloadavg()],
            "route": ({"route_id": route.get("route_id"), "channel_id": route.get("channel_id")} if route else None),
            "workflow": "search → schema (when needed) → call; use direct shell/job tools for common execution",
        }
        result = to_mcp_result(success(request_context.request_id, data))
        result.structured_content = data
        result.meta = dict(BRIDGE_DASHBOARD_UI_META)
        return result

    return (
        RegisteredTool(types.Tool(
            name="bridge_search",
            description="Search the complete hidden Development Bridge capability catalog by intent/category without loading every tool schema into ChatGPT",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 500},
                    "category": {"type": "string", "default": "all", "maxLength": 64},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 40, "default": 12},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ), bridge_search, "compact"),
        RegisteredTool(types.Tool(
            name="bridge_schema",
            description="Return the exact description and JSON input schema for one hidden Development Bridge capability",
            inputSchema={
                "type": "object",
                "properties": {"tool_name": {"type": "string", "minLength": 1, "maxLength": 200}},
                "required": ["tool_name"],
                "additionalProperties": False,
            },
        ), bridge_schema, "compact"),
        RegisteredTool(types.Tool(
            name="bridge_call",
            description="Execute one hidden Development Bridge capability by exact tool name; use bridge_search/bridge_schema when the capability or arguments are not already known",
            inputSchema={
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string", "minLength": 1, "maxLength": 200},
                    "arguments": {"type": "object", "additionalProperties": True, "default": {}},
                },
                "required": ["tool_name"],
                "additionalProperties": False,
            },
        ), bridge_call, "compact"),
        RegisteredTool(types.Tool(
            name="bridge_dashboard",
            description="Show a compact user-facing Development Bridge health and capacity dashboard",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
            _meta=BRIDGE_DASHBOARD_UI_META,
        ), bridge_dashboard, "compact"),
    )
