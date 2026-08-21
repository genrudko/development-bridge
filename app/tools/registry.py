from __future__ import annotations

from collections.abc import Iterable

from app.api.registry import RegisteredTool, ToolRegistry
from app.container import ApplicationContainer

from . import TOOLS, call_tool
from .bridge import bridge_tools
from .files import file_tools
from .projects import project_tools


def _legacy_tools() -> tuple[RegisteredTool, ...]:
    registered = []
    for definition in TOOLS:
        async def handler(ctx, params, request_context, _name=definition.name):
            result = await call_tool(ctx, params)
            if result is None:
                raise RuntimeError(f"legacy handler missing for {_name}")
            return result

        registered.append(RegisteredTool(definition, handler, "legacy"))
    return tuple(registered)


def build_tool_registry(
    container: ApplicationContainer,
    *,
    v1_tools: Iterable[RegisteredTool] | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_many(_legacy_tools())
    registry.register_many(
        tuple(v1_tools)
        if v1_tools is not None
        else bridge_tools(container) + project_tools(container) + file_tools(container)
    )
    return registry
