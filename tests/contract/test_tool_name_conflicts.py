import pytest
from mcp import types

from app.api.errors import ToolNameConflictError
from app.api.registry import RegisteredTool
from app.container import build_container
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry


async def conflicting_handler(ctx, params, request_context):
    raise AssertionError("not called")


def test_legacy_v1_name_conflict_fails_registry_construction():
    conflicting_v1_tool = RegisteredTool(
        definition=types.Tool(
            name="git_status",
            description="Conflicting v1 tool",
            inputSchema={"type": "object", "properties": {}},
        ),
        handler=conflicting_handler,
        source="v1",
    )
    with pytest.raises(ToolNameConflictError, match="legacy"):
        build_tool_registry(
            build_container(BridgeSettings()), v1_tools=[conflicting_v1_tool]
        )

