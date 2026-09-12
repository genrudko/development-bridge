import asyncio

import pytest

from app.blender_bridge.models import ProviderSpec, ToolSpec
from app.blender_bridge.operator import OperatorBroker
from app.blender_bridge.service import BlenderBridgeService


class FakeProvider:
    def __init__(self, name: str, tools: list[ToolSpec], events: list[str] | None = None):
        self.name = name
        self._tools = tools
        self.events = events if events is not None else []

    async def list_tools(self):
        return list(self._tools)

    async def call_tool(self, name: str, arguments: dict):
        self.events.append(f"start:{self.name}:{name}")
        await asyncio.sleep(arguments.get("delay", 0))
        self.events.append(f"end:{self.name}:{name}")
        return {"provider": self.name, "tool": name, "arguments": arguments}


@pytest.mark.asyncio
async def test_operator_ask_blocks_until_same_request_is_answered():
    published = []

    async def publish(prompt):
        published.append(prompt)

    broker = OperatorBroker(publish)
    waiter = asyncio.create_task(
        broker.ask(
            question="Which variant?",
            choices=("A", "B"),
            operation_id="op_1",
        )
    )

    await asyncio.sleep(0)
    assert not waiter.done()
    assert len(published) == 1
    prompt = published[0]
    assert prompt.operation_id == "op_1"
    assert prompt.choices == ("A", "B")

    accepted = broker.answer(prompt.prompt_id, "B")
    assert accepted is True

    answer = await waiter
    assert answer.prompt_id == prompt.prompt_id
    assert answer.value == "B"


@pytest.mark.asyncio
async def test_provider_tools_are_namespaced_and_discoverable():
    dcc = FakeProvider("dcc", [ToolSpec(name="create_cube", description="Create cube", mutating=True)])
    research = FakeProvider("research", [ToolSpec(name="mesh_inspect", description="Inspect mesh", mutating=False)])
    service = BlenderBridgeService(
        providers=(
            ProviderSpec(namespace="dcc", client=dcc),
            ProviderSpec(namespace="research", client=research),
        )
    )

    tools = await service.refresh_catalog()

    assert [tool.public_name for tool in tools] == ["dcc.create_cube", "research.mesh_inspect"]
    assert service.resolve_tool("dcc.create_cube").provider_namespace == "dcc"
    assert service.resolve_tool("research.mesh_inspect").upstream_name == "mesh_inspect"


@pytest.mark.asyncio
async def test_mutating_calls_across_providers_are_serialized():
    events: list[str] = []
    dcc = FakeProvider("dcc", [ToolSpec(name="edit", description="", mutating=True)], events)
    research = FakeProvider("research", [ToolSpec(name="edit", description="", mutating=True)], events)
    service = BlenderBridgeService(
        providers=(
            ProviderSpec(namespace="dcc", client=dcc),
            ProviderSpec(namespace="research", client=research),
        )
    )
    await service.refresh_catalog()

    first = asyncio.create_task(service.call_tool("dcc.edit", {"delay": 0.02}))
    await asyncio.sleep(0)
    second = asyncio.create_task(service.call_tool("research.edit", {"delay": 0}))
    await asyncio.gather(first, second)

    assert events == [
        "start:dcc:edit",
        "end:dcc:edit",
        "start:research:edit",
        "end:research:edit",
    ]


@pytest.mark.asyncio
async def test_read_only_calls_do_not_take_global_write_lock():
    events: list[str] = []
    a = FakeProvider("a", [ToolSpec(name="read", description="", mutating=False)], events)
    b = FakeProvider("b", [ToolSpec(name="read", description="", mutating=False)], events)
    service = BlenderBridgeService(
        providers=(ProviderSpec(namespace="a", client=a), ProviderSpec(namespace="b", client=b))
    )
    await service.refresh_catalog()

    await asyncio.gather(
        service.call_tool("a.read", {"delay": 0.02}),
        service.call_tool("b.read", {"delay": 0}),
    )

    assert events[0:2] == ["start:a:read", "start:b:read"]


@pytest.mark.asyncio
async def test_unknown_mutation_class_defaults_to_mutating():
    dcc = FakeProvider(
        "dcc",
        [ToolSpec(name="mystery", description="Unknown classification", mutating=None)],
    )
    service = BlenderBridgeService(
        providers=(ProviderSpec(namespace="dcc", client=dcc),)
    )

    await service.refresh_catalog()

    assert service.resolve_tool("dcc.mystery").mutating is True


@pytest.mark.asyncio
async def test_duplicate_tool_inside_namespace_is_rejected():
    dcc = FakeProvider(
        "dcc",
        [
            ToolSpec(name="edit", description="first", mutating=True),
            ToolSpec(name="edit", description="second", mutating=True),
        ],
    )
    service = BlenderBridgeService(
        providers=(ProviderSpec(namespace="dcc", client=dcc),)
    )

    with pytest.raises(ValueError, match="duplicate public tool name"):
        await service.refresh_catalog()


@pytest.mark.asyncio
async def test_operator_timeout_cleans_pending_prompt():
    published = []

    async def publish(prompt):
        published.append(prompt)

    broker = OperatorBroker(publish)

    with pytest.raises(asyncio.TimeoutError):
        await broker.ask(question="Still there?", timeout_seconds=0.001)

    assert len(published) == 1
    assert broker.pending_prompt_ids() == ()
    assert broker.answer(published[0].prompt_id, "late") is False


@pytest.mark.asyncio
async def test_operator_cancellation_cleans_pending_prompt():
    published = []

    async def publish(prompt):
        published.append(prompt)

    broker = OperatorBroker(publish)
    waiter = asyncio.create_task(broker.ask(question="Pick one"))
    await asyncio.sleep(0)
    assert len(published) == 1

    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    assert broker.pending_prompt_ids() == ()
    assert broker.answer(published[0].prompt_id, "late") is False
