from app.container import build_container
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry


FILE_TOOLS = {"file_list", "file_read", "file_search"}


def test_file_tool_surface_is_registered_with_closed_schemas():
    registry = build_tool_registry(build_container(BridgeSettings()))
    tools = {tool.name: tool for tool in registry.definitions if tool.name in FILE_TOOLS}

    assert set(tools) == FILE_TOOLS
    assert all(tool.input_schema["additionalProperties"] is False for tool in tools.values())
    assert all(
        tool.input_schema["required"][:2] == ["project_id", "repository_id"]
        for tool in tools.values()
    )
    assert tools["file_read"].input_schema["required"] == [
        "project_id",
        "repository_id",
        "path",
    ]
