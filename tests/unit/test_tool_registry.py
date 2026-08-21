import pytest
from mcp import types

from app.api.errors import ToolNameConflictError
from app.api.registry import RegisteredTool, ToolRegistry


async def handler(ctx, params, request_context):
    raise AssertionError("not called")


def registered(name: str, source: str) -> RegisteredTool:
    return RegisteredTool(
        definition=types.Tool(
            name=name,
            description=name,
            inputSchema={"type": "object", "properties": {}},
        ),
        handler=handler,
        source=source,
    )


def test_registry_preserves_registration_order():
    registry = ToolRegistry()
    registry.register_many([registered("first", "v1"), registered("second", "v1")])
    assert [tool.name for tool in registry.definitions] == ["first", "second"]


def test_registry_rejects_name_conflict_with_source_details():
    registry = ToolRegistry()
    registry.register(registered("git_status", "legacy"))
    with pytest.raises(ToolNameConflictError, match="legacy"):
        registry.register(registered("git_status", "v1"))

