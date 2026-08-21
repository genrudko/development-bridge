from app.container import build_container
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry


V1_TOOLS = {
    "bridge_info",
    "project_list",
    "project_describe",
    "repository_status",
}


def test_v1_tool_surface_is_registered():
    registry = build_tool_registry(build_container(BridgeSettings()))
    names = {tool.name for tool in registry.definitions}
    assert V1_TOOLS <= names


def test_v1_schemas_are_closed_objects():
    registry = build_tool_registry(build_container(BridgeSettings()))
    tools = {
        tool.name: tool for tool in registry.definitions if tool.name in V1_TOOLS
    }
    assert all(tool.input_schema["additionalProperties"] is False for tool in tools.values())
    assert tools["repository_status"].input_schema["required"] == [
        "project_id",
        "repository_id",
    ]

