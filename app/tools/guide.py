from __future__ import annotations


from mcp import types

from app.api.registry import RegisteredTool, ToolRegistry
from app.api.results import success, to_mcp_result


def guide_tools(registry: ToolRegistry, *, tool_surface: str = "full") -> tuple[RegisteredTool, ...]:
    async def bridge_guide(ctx, params, request_context):
        from app.tools.compact import exposed_tool_definitions

        visible_tool_count = len(exposed_tool_definitions(registry, tool_surface))
        coordinator_available = any(
            tool.name.startswith("coordinator_") for tool in registry.definitions
        )
        return to_mcp_result(success(request_context.request_id, {
            "version": "1.0.0",
            "api_version": "1.0",
            "tool_surface": tool_surface,
            "tool_count": visible_tool_count,
            "internal_tool_count": len(registry.definitions),
            "durable_jobs": {
                "summary": (
                    "repository_exec queues durable repository work; queued is a normal initial "
                    "state. Terminal results are available through job_status and job_output."
                ),
            },
            "discovery": {
                "summary": (
                    "Hidden capabilities are indexed by bridge_search and described by "
                    "bridge_schema; bridge_call executes a discovered hidden capability."
                ),
            },
            "coordinator": {
                "available": coordinator_available,
                "summary": (
                    "Registered routes, durable Route Context, event-driven wake, and continuation ACK are available. "
                    "Mount coordinator_x_mount once per chat; later status/wake calls are widgetless and must not remount "
                    "just to refresh the coordinator card."
                ),
            },
            "route_binding": {
                "summary": (
                    "Current-chat binding uses direct coordinator_route_bind_current plus the "
                    "OOB bind-card/openExternal flow. Physical ChatGPT URLs, IDs, sessions, and "
                    "control tokens stay outside model-visible chat; marker/search fallback is "
                    "retired. Native mobile new-bind is currently unsupported; use desktop/Web."
                ),
            },
            "economy_mode": {
                "enabled": True,
                "summary": (
                    "Bounded execution, sparse status reads, bounded output, and offline "
                    "verification before live ChatGPT acceptance."
                ),
            },
        }))

    return (RegisteredTool(
        types.Tool(
            name="bridge_guide",
            description="START HERE: call first in new coordinator chats for bounded operating guidance and the live capability summary",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        bridge_guide,
        "v1",
    ),)
