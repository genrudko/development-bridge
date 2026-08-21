from app.container import build_container
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry


WORKSPACE_TOOLS = {
    "git_fetch",
    "git_branch_create",
    "git_branch_switch",
    "git_fast_forward",
}


def test_git_workspace_contract_is_bounded_and_repository_scoped():
    registry = build_tool_registry(build_container(BridgeSettings()))
    tools = {tool.name: tool for tool in registry.definitions if tool.name in WORKSPACE_TOOLS}
    assert set(tools) == WORKSPACE_TOOLS
    assert all(tool.input_schema["additionalProperties"] is False for tool in tools.values())
    assert tools["git_fetch"].input_schema["required"] == ["project_id", "repository_id"]
    assert tools["git_branch_create"].input_schema["required"] == [
        "project_id",
        "repository_id",
        "branch",
    ]
    for tool in tools.values():
        assert "command" not in tool.input_schema["properties"]
        assert "arguments" not in tool.input_schema["properties"]
