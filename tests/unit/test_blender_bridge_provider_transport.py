import pytest

from app.blender_bridge.models import ToolSpec
from app.blender_bridge.provider_transport import (
    ManagedProviderClient,
    ProviderConnectionLost,
    ProviderHealth,
)


class FakeTransport:
    def __init__(self, *, tools, call_script=None, health=None):
        self.tools = list(tools)
        self.call_script = list(call_script or [])
        self.health_snapshot = health or ProviderHealth(
            state="online", version="1.2.3", pin="abc123"
        )
        self.calls = []
        self.reconnects = 0
        self.list_calls = 0

    async def list_tools(self):
        self.list_calls += 1
        return list(self.tools)

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self.call_script:
            outcome = self.call_script.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        return {"ok": True}

    async def reconnect(self):
        self.reconnects += 1

    async def health(self):
        return self.health_snapshot


@pytest.mark.asyncio
async def test_catalog_can_refresh_after_transport_reconnect():
    transport = FakeTransport(
        tools=[ToolSpec(name="read_scene", description="", mutating=False)]
    )
    provider = ManagedProviderClient(transport)

    first = await provider.list_tools()
    transport.tools = [
        ToolSpec(name="read_scene", description="", mutating=False),
        ToolSpec(name="new_tool", description="", mutating=False),
    ]
    await provider.reconnect()
    second = await provider.list_tools()

    assert [tool.name for tool in first] == ["read_scene"]
    assert [tool.name for tool in second] == ["read_scene", "new_tool"]
    assert transport.reconnects == 1
    health = await provider.health()
    assert health.state == "online"
    assert health.version == "1.2.3"
    assert health.pin == "abc123"


@pytest.mark.asyncio
async def test_connection_loss_during_mutation_is_uncertain_and_never_replayed():
    transport = FakeTransport(
        tools=[ToolSpec(name="edit_mesh", description="", mutating=True)],
        call_script=[ProviderConnectionLost("socket dropped")],
    )
    provider = ManagedProviderClient(transport)
    await provider.list_tools()

    result = await provider.call_tool("edit_mesh", {"faces": [1, 2]})

    assert result.state == "uncertain"
    assert result.value is None
    assert "socket dropped" in result.error
    assert transport.calls == [("edit_mesh", {"faces": [1, 2]})]
    assert transport.reconnects == 0


@pytest.mark.asyncio
async def test_idempotent_read_may_reconnect_and_retry_once():
    transport = FakeTransport(
        tools=[
            ToolSpec(
                name="read_scene",
                description="",
                mutating=False,
                idempotent=True,
            )
        ],
        call_script=[ProviderConnectionLost("drop"), {"objects": 3}],
    )
    provider = ManagedProviderClient(transport)
    await provider.list_tools()

    result = await provider.call_tool("read_scene", {})

    assert result.state == "completed"
    assert result.value == {"objects": 3}
    assert transport.reconnects == 1
    assert len(transport.calls) == 2


@pytest.mark.asyncio
async def test_non_idempotent_read_is_not_replayed_after_disconnect():
    transport = FakeTransport(
        tools=[
            ToolSpec(
                name="read_stream_cursor",
                description="",
                mutating=False,
                idempotent=False,
            )
        ],
        call_script=[ProviderConnectionLost("drop")],
    )
    provider = ManagedProviderClient(transport)
    await provider.list_tools()

    result = await provider.call_tool("read_stream_cursor", {})

    assert result.state == "failed"
    assert len(transport.calls) == 1
    assert transport.reconnects == 0
