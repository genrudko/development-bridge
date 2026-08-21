import asyncio

from mcp import types

from app.tools import TOOLS, call_tool
from app.tools.registry import build_tool_registry
from app.container import build_container
from app.settings import BridgeSettings


EXPECTED_LEGACY_TOOLS = {
    "workspace_status",
    "read_file",
    "apply_patch",
    "git_status",
    "git_branch",
    "git_commit",
    "git_push",
    "github_status",
    "search_workspace",
}


def test_legacy_tool_surface_is_preserved():
    assert {tool.name for tool in TOOLS} == EXPECTED_LEGACY_TOOLS


def test_registered_legacy_surface_matches_preserved_baseline():
    registry = build_tool_registry(build_container(BridgeSettings()))
    registered_legacy = {
        tool.name
        for tool in registry.definitions
        if registry.get(tool.name).source == "legacy"
    }
    assert registered_legacy == EXPECTED_LEGACY_TOOLS


def test_legacy_workspace_status_behavior_is_preserved():
    result = asyncio.run(
        call_tool(
            None,
            types.CallToolRequestParams(name="workspace_status", arguments={}),
        )
    )
    assert result.is_error is False
    assert result.content[0].text.startswith("workspace: ")
