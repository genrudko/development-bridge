from __future__ import annotations

from collections.abc import Iterable

from app.api.registry import RegisteredTool, ToolRegistry
from app.container import ApplicationContainer

from .bridge import bridge_tools
from .bridge_restart import bridge_restart_tools
from .changes import change_tools
from .chatgpt_share import chatgpt_share_tools
from .commands import command_tools
from .coordinator import coordinator_tools
from .eod_browser import eod_browser_tools
from .files import file_tools
from .fusion import fusion_tools
from .git_read import git_read_tools
from .git_workspace import git_workspace_tools
from .git_write import git_write_tools
from .github import github_tools
from .guide import guide_tools
from .jobs import job_tools
from .knowledge import knowledge_tools
from .projects import project_tools
from .telegram_supervisor import telegram_supervisor_tools


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
        + bridge_restart_tools(container)
        + project_tools(container)
        + file_tools(container)
        + eod_browser_tools(container)
        + fusion_tools(container)
        + git_read_tools(container)
        + git_write_tools(container)
        + git_workspace_tools(container)
        + change_tools(container)
        + job_tools(container)
        + knowledge_tools(container)
        + github_tools(container)
        + chatgpt_share_tools(container)
        + coordinator_tools(container)
        + telegram_supervisor_tools(container)
        + command_tools(container)
    )
    registry.register_many(guide_tools(registry))
    return registry
