from __future__ import annotations

import gc
import json
import weakref

import pytest
from mcp import types
from mcp.server import Server

from app.blender_relay import BlenderRelayService
from app.settings import BlenderBridgeSettings
from tests.unit.test_blender_relay import FakeDesktop, tool


class Session: pass
class Context:
    def __init__(self, session): self.session = session


def handlers(service):
    from app.blender_relay.server import create_blender_server
    server = create_blender_server(service)
    return server, server.get_request_handler("tools/list").handler, server.get_request_handler("tools/call").handler


@pytest.mark.asyncio
async def test_dynamic_list_uses_real_tool_aliases_and_plain_capabilities():
    service = BlenderRelayService(BlenderBridgeSettings(enabled=True), FakeDesktop())
    service.accept_registration("blender-hub", 1, "mcp-v1", [tool("z.read"), tool("a.read", outputSchema=None, annotations={"readOnlyHint": True})])
    server, list_tools, _ = handlers(service)
    assert type(server) is Server
    result = await list_tools(Context(Session()), types.PaginatedRequestParams())
    dumped = [item.model_dump(mode="json", by_alias=True, exclude_none=True) for item in result.tools]
    assert [item["name"] for item in dumped] == ["a.read", "z.read"]
    assert dumped[0]["annotations"] == {"readOnlyHint": True}
    assert "outputSchema" not in dumped[0]
    assert dumped[1]["execution"] == {"taskSupport": "forbidden"}
    assert dumped[1]["icons"][0]["mimeType"] == "image/png"
    assert dumped[1]["_meta"] == {"vendor": {"stable": True}}
    assert server.get_capabilities().tools.list_changed is False


@pytest.mark.asyncio
async def test_dynamic_list_preserves_exact_supported_annotation_evidence():
    annotations = {
        "title": "Safe lookup",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
    service = BlenderRelayService(BlenderBridgeSettings(enabled=True), FakeDesktop())
    publication = service.accept_registration(
        "blender-hub", 1, "mcp-v1", [tool(annotations=annotations)]
    )
    _, list_tools, _ = handlers(service)
    result = await list_tools(Context(Session()), types.PaginatedRequestParams())
    dumped = result.tools[0].model_dump(mode="json", by_alias=True, exclude_none=True)
    assert dumped["annotations"] == annotations
    assert publication.tools[0].mutating is False


@pytest.mark.asyncio
async def test_stale_surface_requires_relist_but_generation_only_change_does_not():
    desktop = FakeDesktop()
    service = BlenderRelayService(BlenderBridgeSettings(enabled=True), desktop)
    service.accept_registration("blender-hub", 1, "mcp-v1", [tool()])
    _, list_tools, call_tool = handlers(service)
    session = Session(); assert weakref.ref(session)() is session
    await list_tools(Context(session), types.PaginatedRequestParams())
    service.accept_registration("blender-hub", 2, "mcp-v1", [tool(title="changed")])
    stale = await call_tool(Context(session), types.CallToolRequestParams(name="dcc.search", arguments={}))
    assert stale.is_error is True and "catalog_changed_relist_required" in stale.content[0].text
    assert desktop.calls == []
    await list_tools(Context(session), types.PaginatedRequestParams())
    assert (await call_tool(Context(session), types.CallToolRequestParams(name="dcc.search", arguments={}))).is_error is False
    service.accept_registration("blender-hub", 3, "mcp-v1", [tool(title="changed")])
    assert (await call_tool(Context(session), types.CallToolRequestParams(name="dcc.search", arguments={}))).is_error is False


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,expected_type", [
    ({"content": [{"type": "text", "text": "bad"}], "structuredContent": {"x": 1}, "isError": True, "resultType": "complete", "_meta": {"safe": True}}, types.CallToolResult),
    ({"resultType": "input_required", "requestState": "s1", "inputRequests": {}, "_meta": {"safe": True}}, types.InputRequiredResult),
])
async def test_result_adapter_roundtrips_real_sdk_result_models(payload, expected_type):
    service = BlenderRelayService(BlenderBridgeSettings(enabled=True), FakeDesktop(payload))
    service.accept_registration("blender-hub", 1, "mcp-v1", [tool()])
    _, list_tools, call_tool = handlers(service); session = Session()
    await list_tools(Context(session), types.PaginatedRequestParams())
    result = await call_tool(Context(session), types.CallToolRequestParams(name="dcc.search", arguments={}))
    assert isinstance(result, expected_type)
    assert result.model_dump(mode="json", by_alias=True, exclude_none=True) == payload


@pytest.mark.asyncio
async def test_malformed_desktop_envelope_is_sanitized():
    service = BlenderRelayService(BlenderBridgeSettings(enabled=True), FakeDesktop({"content": [{"type": "text", "text": object()}], "secret": "DO_NOT_LEAK"}))
    service.accept_registration("blender-hub", 1, "mcp-v1", [tool()])
    _, list_tools, call_tool = handlers(service); session = Session()
    await list_tools(Context(session), types.PaginatedRequestParams())
    result = await call_tool(Context(session), types.CallToolRequestParams(name="dcc.search", arguments={}))
    text = result.content[0].text
    assert result.is_error is True and len(text) < 256
    assert "DO_NOT_LEAK" not in text and "object at" not in text


@pytest.mark.asyncio
async def test_external_result_adds_bridge_owned_resource_links():
    class ExternalDesktop(FakeDesktop):
        def __init__(self): super().__init__({"external_result": {"result_id": "r1"}})
        def external_result(self, reference):
            assert reference == {"result_id": "r1"}
            return ({"content": [{"type": "text", "text": "full"}], "structuredContent": {"ok": True}, "isError": False}, {"resources": [{"uri": "https://bridge.example/r/one", "file_name": "one.png", "mime_type": "image/png", "size_bytes": 7}], "export_url": "https://bridge.example/r/full", "file_name": "result.json", "size_bytes": 99})
    service = BlenderRelayService(BlenderBridgeSettings(enabled=True), ExternalDesktop())
    service.accept_registration("blender-hub", 1, "mcp-v1", [tool()])
    _, list_tools, call_tool = handlers(service); session = Session()
    await list_tools(Context(session), types.PaginatedRequestParams())
    result = await call_tool(Context(session), types.CallToolRequestParams(name="dcc.search", arguments={}))
    links = [block for block in result.content if isinstance(block, types.ResourceLink)]
    assert [(link.name, str(link.uri)) for link in links] == [("one.png", "https://bridge.example/r/one"), ("result.json", "https://bridge.example/r/full")]


def test_real_installed_server_session_is_weak_referenceable():
    # Regression proof for the Task 2 plan requirement: the production relay
    # keys listed_revisions by MCP request context session using a
    # weakref.WeakKeyDictionary, so it must never retain closed/unused
    # sessions. This exercises the REAL installed SDK ServerSession type
    # rather than the dummy Session used elsewhere, constructing an
    # uninitialized instance via object.__new__ to avoid unrelated connection
    # internals. A first-run GREEN is expected: this documents already-working
    # weak-reference capability.
    from mcp.server.session import ServerSession

    session = object.__new__(ServerSession)
    ref = weakref.ref(session)
    assert ref() is session
    del session
    gc.collect()
    assert ref() is None
