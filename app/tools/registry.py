from __future__ import annotations

from collections.abc import Iterable

from app.api.registry import RegisteredTool, ToolRegistry
from app.container import ApplicationContainer

from .bridge import bridge_tools
from .changes import change_tools
from .files import file_tools
from .git_read import git_read_tools
from .git_write import git_write_tools
from .jobs import job_tools
from .projects import project_tools

def build_tool_registry(
    container: ApplicationContainer,
    *,
    v1_tools: Iterable[RegisteredTool] | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_many(
        tuple(v1_tools)
        if v1_tools is not None
        else bridge_tools(container)
        + project_tools(container)
        + file_tools(container)
        + git_read_tools(container)
        + git_write_tools(container)
        + change_tools(container)
        + job_tools(container)
    )
    return registry
