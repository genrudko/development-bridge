import asyncio
import json
from types import SimpleNamespace

from app.tools.blender import blender_tools


BLENDER_TOOLS = {
    "blender_node_status",
    "blender_tools",
    "blender_call",
    "blender_submit",
    "blender_operation_status",
    "blender_operation_result",
    "blender_result_view",
    "blender_operator_ask",
}


class BlockingDesktopNode:
    def __init__(self):
        self.started = asyncio.Event()
        self.answer = asyncio.Event()
        self.calls = []

    async def call(self, node_id, tool_name, arguments, journal=None):
        self.calls.append((node_id, tool_name, arguments, journal))
        self.started.set()
        await self.answer.wait()
        return {"prompt_id": "ask_1", "value": "B"}


def test_blender_control_surface_and_schemas_are_registered():
    tools = {tool.definition.name: tool.definition for tool in blender_tools(SimpleNamespace())}

    assert set(tools) == BLENDER_TOOLS
    assert all(tool.input_schema["additionalProperties"] is False for tool in tools.values())
    assert tools["blender_call"].input_schema["required"] == ["node_id", "tool_name"]
    assert tools["blender_operator_ask"].input_schema["required"] == ["node_id", "question"]
    assert tools["blender_operator_ask"].input_schema["properties"]["choices"]["maxItems"] == 20


def test_blender_operator_ask_keeps_same_handler_pending_until_node_answers():
    async def scenario():
        desktop = BlockingDesktopNode()
        container = SimpleNamespace(desktop_nodes=desktop)
        tools = {tool.definition.name: tool for tool in blender_tools(container)}
        handler = tools["blender_operator_ask"].handler

        task = asyncio.create_task(
            handler(
                None,
                SimpleNamespace(
                    arguments={
                        "node_id": "blender-workstation",
                        "question": "Which variant?",
                        "choices": ["A", "B"],
                        "operation_id": "op_1",
                    }
                ),
                SimpleNamespace(request_id="request-1"),
            )
        )
        await desktop.started.wait()
        assert not task.done()
        assert desktop.calls == [
            (
                "blender-workstation",
                "operator.ask",
                {
                    "question": "Which variant?",
                    "choices": ["A", "B"],
                    "operation_id": "op_1",
                },
                {
                    "summary": "Blender Hub same-turn operator prompt",
                    "mutation": False,
                },
            )
        ]

        desktop.answer.set()
        result = await task
        payload = json.loads(result.content[0].text)
        assert payload["data"] == {"prompt_id": "ask_1", "value": "B"}

    asyncio.run(scenario())
