from app.container import build_container
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry


GIT_READ_TOOLS = {"git_log", "git_show", "git_diff", "git_refs"}


def test_git_read_surface_is_registered_with_closed_schemas():
    registry = build_tool_registry(build_container(BridgeSettings()))
    tools = {
        tool.name: tool
        for tool in registry.definitions
        if tool.name in GIT_READ_TOOLS
    }

    assert set(tools) == GIT_READ_TOOLS
    assert all(tool.input_schema["additionalProperties"] is False for tool in tools.values())
    assert all(
        tool.input_schema["required"][:2] == ["project_id", "repository_id"]
        for tool in tools.values()
    )
    assert tools["git_show"].input_schema["required"] == [
        "project_id",
        "repository_id",
        "revision",
    ]
    assert tools["git_diff"].input_schema["properties"]["mode"]["enum"] == [
        "working",
        "staged",
        "range",
    ]
