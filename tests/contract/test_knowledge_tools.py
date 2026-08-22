from app.container import build_container
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry


KNOWLEDGE_TOOLS = {
    "knowledge_source_list", "knowledge_search", "knowledge_message", "knowledge_thread"
}


def test_knowledge_tools_have_closed_repository_independent_schemas():
    registry = build_tool_registry(build_container(BridgeSettings()))
    tools = {tool.name: tool for tool in registry.definitions if tool.name in KNOWLEDGE_TOOLS}
    assert set(tools) == KNOWLEDGE_TOOLS
    assert all(tool.input_schema["additionalProperties"] is False for tool in tools.values())
    assert tools["knowledge_source_list"].input_schema["properties"] == {}
    assert tools["knowledge_search"].input_schema["required"] == ["query"]
    assert tools["knowledge_message"].input_schema["required"] == ["source_id", "message_id"]
    assert "project_id" not in str({name: tool.input_schema for name, tool in tools.items()})
    assert {registry.get(name).source for name in KNOWLEDGE_TOOLS} == {"community-knowledge"}
