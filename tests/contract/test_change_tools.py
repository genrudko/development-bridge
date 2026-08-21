from app.container import build_container
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry


def test_change_tools_are_registered_with_self_contained_closed_schemas():
    registry = build_tool_registry(build_container(BridgeSettings()))
    tools = {
        tool.name: tool
        for tool in registry.definitions
        if tool.name in {"change_plan", "change_apply"}
    }

    assert set(tools) == {"change_plan", "change_apply"}
    assert all(tool.input_schema["additionalProperties"] is False for tool in tools.values())
    assert tools["change_plan"].input_schema["required"] == [
        "project_id",
        "repository_id",
        "operations",
    ]
    assert tools["change_apply"].input_schema["required"] == [
        "project_id",
        "repository_id",
        "plan_id",
        "base_revision",
        "operations",
    ]
    assert "summary" in tools["change_apply"].input_schema["properties"]
    operation_variants = tools["change_plan"].input_schema["properties"][
        "operations"
    ]["items"]["oneOf"]
    assert {variant["properties"]["type"]["const"] for variant in operation_variants} == {
        "create",
        "update",
        "delete",
        "rename",
    }
