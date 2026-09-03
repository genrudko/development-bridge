from types import SimpleNamespace

import pytest

from app.api.errors import BridgeError
from app.tools.compact import (
    BRIDGE_DASHBOARD_UI_META,
    COMPACT_VISIBLE_TOOLS,
    compact_tools,
    exposed_tool_definitions,
)
from app.api.registry import ToolRegistry
from app.api.registry import RegisteredTool
from mcp import types


async def _handler(ctx, params, request_context):
    return types.CallToolResult(content=[types.TextContent(type="text", text=params.arguments.get("value", "ok"))])


def _registry():
    registry = ToolRegistry()
    for name in ("file_read", "github_pull_request_get", "coordinator_ack", "coordinator_route_bind_current", "executor_status", "executor_start"):
        registry.register(RegisteredTool(types.Tool(
            name=name,
            description=f"tool {name}",
            inputSchema={"type":"object","properties":{"value":{"type":"string"}},"additionalProperties":False},
        ), _handler, "test"))
    return registry


def test_compact_surface_exposes_only_allowlisted_names():
    registry = _registry()
    container = SimpleNamespace(
        settings=SimpleNamespace(server=SimpleNamespace(name="development-bridge")),
        projects=SimpleNamespace(list=lambda: ()),
        route_registry=SimpleNamespace(resolve=lambda: None),
    )
    registry.register_many(compact_tools(container, registry))
    names = {tool.name for tool in exposed_tool_definitions(registry, "compact")}
    assert names <= set(COMPACT_VISIBLE_TOOLS)
    assert "bridge_call" in names
    assert "coordinator_route_bind_current" in names
    assert "file_read" not in names
    assert "executor_status" not in names and "executor_start" not in names


@pytest.mark.asyncio
async def test_bridge_call_delegates_hidden_tool():
    registry = _registry()
    container = SimpleNamespace(
        settings=SimpleNamespace(server=SimpleNamespace(name="development-bridge")),
        projects=SimpleNamespace(list=lambda: ()),
        route_registry=SimpleNamespace(resolve=lambda: None),
    )
    tools = {tool.definition.name: tool for tool in compact_tools(container, registry)}
    registry.register_many(tools.values())
    params = SimpleNamespace(arguments={"tool_name":"file_read","arguments":{"value":"delegated"}})
    request_context = SimpleNamespace(request_id="req_test")
    result = await tools["bridge_call"].handler(None, params, request_context)
    assert result.content[0].text == "delegated"


@pytest.mark.asyncio
async def test_bridge_search_and_schema_cover_hidden_tools():
    registry = _registry()
    container = SimpleNamespace(
        settings=SimpleNamespace(server=SimpleNamespace(name="development-bridge")),
        projects=SimpleNamespace(list=lambda: ()),
        route_registry=SimpleNamespace(resolve=lambda: None),
    )
    tools = {tool.definition.name: tool for tool in compact_tools(container, registry)}
    registry.register_many(tools.values())
    request_context = SimpleNamespace(request_id="req_search_schema")

    search = await tools["bridge_search"].handler(
        None, SimpleNamespace(arguments={"query": "github pull request"}), request_context
    )
    assert "github_pull_request_get" in search.content[0].text

    schema = await tools["bridge_schema"].handler(
        None, SimpleNamespace(arguments={"tool_name": "github_pull_request_get"}), request_context
    )
    assert "input_schema" in schema.content[0].text
    assert "value" in schema.content[0].text


@pytest.mark.asyncio
async def test_bridge_call_rejects_invalid_hidden_arguments():
    registry = _registry()
    container = SimpleNamespace(
        settings=SimpleNamespace(server=SimpleNamespace(name="development-bridge")),
        projects=SimpleNamespace(list=lambda: ()),
        route_registry=SimpleNamespace(resolve=lambda: None),
    )
    tools = {tool.definition.name: tool for tool in compact_tools(container, registry)}
    registry.register_many(tools.values())
    request_context = SimpleNamespace(request_id="req_invalid_delegate")
    with pytest.raises(BridgeError) as exc:
        await tools["bridge_call"].handler(
            None,
            SimpleNamespace(arguments={"tool_name": "github_pull_request_get", "arguments": {"value": 3}}),
            request_context,
        )
    assert "invalid arguments" in str(exc.value)

@pytest.mark.asyncio
async def test_progress_tools_are_hidden_and_dashboard_includes_route_progress(tmp_path):
    registry = _registry()

    class Routes:
        path = tmp_path / "routes.json"
        def resolve(self, route_id=None):
            selected = route_id or "ad5x"
            return {"route_id": selected, "channel_id": f"telegram-{selected}"}

    container = SimpleNamespace(
        settings=SimpleNamespace(server=SimpleNamespace(name="development-bridge")),
        projects=SimpleNamespace(list=lambda: ()),
        route_registry=Routes(),
        coordinator=SimpleNamespace(session_binding=lambda session_id: {"route_id": "ad5x"}),
    )
    tools = {tool.definition.name: tool for tool in compact_tools(container, registry)}
    registry.register_many(tools.values())
    exposed = {tool.name for tool in exposed_tool_definitions(registry, "compact")}
    assert "work_progress_update" not in exposed
    assert "work_progress_get" not in exposed

    request_context = SimpleNamespace(request_id="req_progress")
    update = await tools["work_progress_update"].handler(
        None,
        SimpleNamespace(arguments={
            "route_id": "ad5x",
            "title": "Bridge optimization",
            "total": 4,
            "completed": 2,
            "phase": "Dashboard",
            "status": "working",
            "current": "Run tests",
            "next": "Deploy",
        }),
        request_context,
    )
    assert "50" in update.content[0].text

    dashboard = await tools["bridge_dashboard"].handler(
        None, SimpleNamespace(arguments={}), request_context
    )
    assert dashboard.structured_content["progress"]["title"] == "Bridge optimization"
    assert dashboard.structured_content["progress"]["percent"] == 50


@pytest.mark.asyncio
async def test_dashboard_unbound_session_uses_requested_route_progress(tmp_path):
    registry = _registry()

    class Routes:
        path = tmp_path / "routes.json"
        def snapshot(self):
            return {"requested_route": "ad5x"}
        def resolve(self, route_id=None):
            if route_id == "ad5x":
                return {"route_id": "ad5x", "channel_id": "telegram-ad5x"}
            return None

    container = SimpleNamespace(
        settings=SimpleNamespace(server=SimpleNamespace(name="development-bridge")),
        projects=SimpleNamespace(list=lambda: ()),
        route_registry=Routes(),
        coordinator=SimpleNamespace(session_binding=lambda session_id: None),
    )
    tools = {tool.definition.name: tool for tool in compact_tools(container, registry)}
    registry.register_many(tools.values())
    request_context = SimpleNamespace(request_id="req_unbound_progress")
    await tools["work_progress_update"].handler(
        None,
        SimpleNamespace(arguments={
            "route_id": "ad5x",
            "title": "Progress dashboard",
            "total": 4,
            "completed": 1,
            "status": "working",
        }),
        request_context,
    )
    dashboard = await tools["bridge_dashboard"].handler(
        None, SimpleNamespace(arguments={}), request_context
    )
    assert dashboard.structured_content["route"]["route_id"] == "ad5x"
    assert dashboard.structured_content["progress"]["title"] == "Progress dashboard"
    assert dashboard.structured_content["progress"]["percent"] == 25


@pytest.mark.asyncio
async def test_dashboard_progress_payload_starts_bound_operation_with_app_result(tmp_path):
    registry = _registry()

    class Routes:
        path = tmp_path / "routes.json"
        def resolve(self, route_id=None):
            return {"route_id": route_id or "ad5x", "channel_id": "telegram-ad5x"}

    container = SimpleNamespace(
        settings=SimpleNamespace(server=SimpleNamespace(name="development-bridge")),
        projects=SimpleNamespace(list=lambda: ()),
        route_registry=Routes(),
        coordinator=SimpleNamespace(session_binding=lambda session_id: {"route_id": "ad5x"}),
    )
    tools = {tool.definition.name: tool for tool in compact_tools(container, registry)}
    registry.register_many(tools.values())
    request_context = SimpleNamespace(request_id="req_dashboard_start")
    dashboard_schema = tools["bridge_dashboard"].definition.input_schema
    assert dashboard_schema["properties"]["progress"]["required"] == ["title", "total"]
    assert dashboard_schema["properties"]["progress"]["properties"]["status"]["enum"] == [
        "planning", "working",
    ]
    assert "operation_id" in tools["work_progress_update"].definition.input_schema["properties"]

    result = await tools["bridge_dashboard"].handler(
        None,
        SimpleNamespace(arguments={"progress": {
            "title": "Lifecycle change",
            "total": 4,
            "phase": "Tests",
            "current": "Confirm RED",
            "status": "planning",
        }}),
        request_context,
    )

    progress = result.structured_content["progress"]
    assert progress["operation_id"]
    assert progress["title"] == "Lifecycle change"
    assert progress["status"] == "planning"
    assert result.meta == BRIDGE_DASHBOARD_UI_META


@pytest.mark.asyncio
async def test_work_progress_update_has_no_dashboard_ui_metadata(tmp_path):
    registry = _registry()

    class Routes:
        path = tmp_path / "routes.json"
        def resolve(self, route_id=None):
            return {"route_id": route_id or "ad5x", "channel_id": "telegram-ad5x"}

    container = SimpleNamespace(
        settings=SimpleNamespace(server=SimpleNamespace(name="development-bridge")),
        projects=SimpleNamespace(list=lambda: ()),
        route_registry=Routes(),
        coordinator=SimpleNamespace(session_binding=lambda session_id: {"route_id": "ad5x"}),
    )
    tools = {tool.definition.name: tool for tool in compact_tools(container, registry)}
    registry.register_many(tools.values())
    request_context = SimpleNamespace(request_id="req_hidden_update")
    started = await tools["bridge_dashboard"].handler(
        None,
        SimpleNamespace(arguments={"progress": {"title": "One card", "total": 2}}),
        request_context,
    )

    update = await tools["work_progress_update"].handler(
        None,
        SimpleNamespace(arguments={
            "operation_id": started.structured_content["progress"]["operation_id"],
            "completed": 1,
        }),
        request_context,
    )

    assert update.structured_content is None
    assert update.meta is None
