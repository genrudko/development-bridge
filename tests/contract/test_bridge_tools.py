from app.container import build_container
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry

V1_TOOLS = {
    "bridge_info",
    "bridge_restart",
    "project_list",
    "project_describe",
    "repository_status",
    "repository_clone",
}

BRIDGE_CAPABILITIES = {
    "multi-project",
    "repository-status",
    "repository-files",
    "git-read",
    "controlled-changes",
    "tasks-jobs",
    "repository-exec",
    "git-write",
    "github-host",
    "community-knowledge",
    "chatgpt-share",
    "coordinator-x",
    "structured-command",
}


def test_v1_tool_surface_is_registered():
    registry = build_tool_registry(build_container(BridgeSettings()))
    names = {tool.name for tool in registry.definitions}
    assert V1_TOOLS <= names


def test_v1_schemas_are_closed_objects():
    registry = build_tool_registry(build_container(BridgeSettings()))
    tools = {tool.name: tool for tool in registry.definitions if tool.name in V1_TOOLS}
    assert all(
        tool.input_schema["additionalProperties"] is False for tool in tools.values()
    )
    assert tools["bridge_restart"].input_schema == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    assert tools["repository_status"].input_schema["required"] == [
        "project_id",
        "repository_id",
    ]
    assert tools["repository_clone"].input_schema["required"] == [
        "project_id",
        "repository_id",
        "url",
    ]
    assert tools["repository_clone"].input_schema["properties"]["depth"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 10000,
        "default": 50,
    }
    assert tools["repository_clone"].input_schema["properties"]["ref"] == {
        "type": "string",
        "minLength": 1,
        "maxLength": 1024,
    }


def test_bridge_info_reports_only_current_capabilities():
    import asyncio
    import json
    from types import SimpleNamespace

    registry = build_tool_registry(build_container(BridgeSettings()))
    result = asyncio.run(
        registry.get("bridge_info").handler(
            None,
            SimpleNamespace(arguments={}),
            SimpleNamespace(request_id="contract-request"),
        )
    )
    payload = json.loads(result.content[0].text)
    assert set(payload["data"]["capabilities"]) == BRIDGE_CAPABILITIES
