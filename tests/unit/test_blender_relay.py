from __future__ import annotations

import pytest

from app.settings import BlenderBridgeSettings, DesktopNodeSettings


class FakeDesktop:
    def __init__(self, result=None):
        self.result = result or {"content": [{"type": "text", "text": "ok"}]}
        self.calls = []

    async def call(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result


def tool(name="dcc.search", **updates):
    value = {
        "name": name, "title": "Search", "description": "Find things",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
        "outputSchema": {"type": "object", "properties": {"hits": {"type": "array"}}},
        "annotations": {"readOnlyHint": True, "destructiveHint": False},
        "execution": {"taskSupport": "forbidden"},
        "icons": [{"src": "data:image/png;base64,AA==", "mimeType": "image/png"}],
        "_meta": {"vendor": {"stable": True}}, "mutating": True,
    }
    value.update(updates)
    return value


def relay():
    from app.blender_relay import BlenderRelayService
    return BlenderRelayService(BlenderBridgeSettings(enabled=True), FakeDesktop())


def test_registration_is_deeply_immutable_sorted_and_recomputes_mutation():
    service = relay()
    first, second = tool("zeta.read"), tool("alpha.read")
    publication = service.accept_registration("blender-hub", 7, "mcp-v1", [first, second])
    first["inputSchema"]["properties"]["query"]["type"] = "integer"
    first["annotations"]["readOnlyHint"] = False
    assert [item.name for item in publication.tools] == ["alpha.read", "zeta.read"]
    assert publication.tools[1].input_schema["properties"]["query"]["type"] == "string"
    assert publication.tools[1].mutating is False
    with pytest.raises(TypeError):
        publication.tools[1].annotations["readOnlyHint"] = False


@pytest.mark.parametrize("node,profile,tools", [
    ("other", "mcp-v1", [tool()]), ("blender-hub", "fusion-v1", [tool()]),
    ("blender-hub", "mcp-v1", [tool("plain")]),
    ("blender-hub", "mcp-v1", [tool("operator.inject")]),
    ("blender-hub", "mcp-v1", [tool("hub.inject")]),
    ("blender-hub", "mcp-v1", [tool("x." + "a" * 130)]),
    ("blender-hub", "mcp-v1", [tool(), tool()]),
    ("blender-hub", "mcp-v1", [tool(inputSchema=[])]),
    ("blender-hub", "mcp-v1", [tool(outputSchema=[])]),
    ("blender-hub", "mcp-v1", [tool(annotations=[])]),
    ("blender-hub", "mcp-v1", [tool(_meta={"bad": object()})]),
])
def test_registration_rejects_invalid_candidate_atomically(node, profile, tools):
    service = relay()
    accepted = service.accept_registration("blender-hub", 1, "mcp-v1", [tool("dcc.old")])
    with pytest.raises(ValueError):
        service.accept_registration(node, 2, profile, tools)
    assert service.snapshot() == accepted


@pytest.mark.parametrize("annotations", [
    {"readOnlyHint": "yes"},
    {"destructiveHint": 1},
    {"idempotentHint": 0},
    {"openWorldHint": "false"},
    {"read_only_hint": True},
    {"unknownHint": False},
    {"title": 7},
])
def test_registration_rejects_inexact_tool_annotations_atomically(annotations):
    service = relay()
    accepted = service.accept_registration("blender-hub", 1, "mcp-v1", [tool("dcc.old")])
    with pytest.raises(ValueError):
        service.accept_registration("blender-hub", 2, "mcp-v1", [tool(annotations=annotations)])
    assert service.snapshot() == accepted


@pytest.mark.parametrize(("field", "value"), [
    ("inputSchema", {"type": "object", "properties": {1: {"type": "string"}}}),
    ("outputSchema", {"type": "object", "examples": [(1, 2)]}),
    ("annotations", {"title": ("not", "json")}),
    ("execution", {"taskSupport": ("forbidden",)}),
    ("icons", [{"src": "x", "sizes": ("16x16",)}]),
    ("_meta", {"nested": {1: "value"}}),
    ("_meta", {"nested": {"tuple": (1, 2)}}),
    ("_meta", {"nested": {"set": {1, 2}}}),
    ("inputSchema", {"type": "object", "maximum": float("nan")}),
    ("outputSchema", {"type": "object", "maximum": float("inf")}),
])
def test_registration_rejects_non_json_evidence_at_every_depth_atomically(field, value):
    service = relay()
    accepted = service.accept_registration("blender-hub", 1, "mcp-v1", [tool("dcc.old")])
    with pytest.raises(ValueError):
        service.accept_registration("blender-hub", 2, "mcp-v1", [tool(**{field: value})])
    assert service.snapshot() == accepted


def test_registration_accepts_exact_annotations_and_nested_json_snapshot():
    service = relay()
    annotations = {
        "title": "Safe lookup",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
    candidate = tool(annotations=annotations, _meta={"nested": {"values": [1, None, False, 2.5]}})
    publication = service.accept_registration("blender-hub", 1, "mcp-v1", [candidate])
    candidate["_meta"]["nested"]["values"][0] = 99
    descriptor = publication.tools[0]
    assert dict(descriptor.annotations) == annotations
    assert descriptor.publication_metadata["_meta"]["nested"]["values"][0] == 1
    assert descriptor.mutating is False


def test_registration_accepts_null_canonical_hints_and_classifies_conservatively():
    service = relay()
    annotations = {
        "title": None,
        "readOnlyHint": None,
        "destructiveHint": None,
        "idempotentHint": None,
        "openWorldHint": None,
    }
    publication = service.accept_registration(
        "blender-hub", 1, "mcp-v1", [tool(annotations=annotations)]
    )
    assert dict(publication.tools[0].annotations) == annotations
    assert publication.tools[0].mutating is True


def test_revisions_distinguish_registration_from_public_surface():
    service = relay()
    one = service.accept_registration("blender-hub", 1, "mcp-v1", [tool()])
    two = service.accept_registration("blender-hub", 2, "mcp-v1", [tool()])
    three = service.accept_registration("blender-hub", 3, "mcp-v1", [tool(title="Changed")])
    assert (one.publication_revision, one.surface_revision) == (1, 1)
    assert (two.publication_revision, two.surface_revision, two.session_generation) == (2, 1, 2)
    assert (three.publication_revision, three.surface_revision) == (3, 2)


@pytest.mark.asyncio
async def test_invoke_uses_snapshot_generation_mutation_and_timeout():
    service = relay(); service.accept_registration("blender-hub", 9, "mcp-v1", [tool()])
    result = await service.invoke("dcc.search", {"query": "x"})
    assert result["content"][0]["text"] == "ok"
    args, kwargs = service.desktop_nodes.calls[0]
    assert args[:3] == ("blender-hub", "dcc.search", {"query": "x"})
    assert kwargs == {"journal": {"mutation": False}, "expected_session_generation": 9, "timeout_seconds": 360}


def test_blender_settings_invariants():
    value = BlenderBridgeSettings()
    assert (value.enabled, value.node_id, value.mount_path, value.mcp_path) == (False, "blender-hub", "/blender", "/mcp")
    assert value.operator_ask_timeout_seconds == 300 < value.call_timeout_seconds == 360 <= DesktopNodeSettings().call_timeout_seconds * 2
    for update in ({"mount_path": "blender"}, {"mount_path": "/"}, {"mount_path": "/blender/"}, {"mcp_path": "/blender/mcp"}, {"mcp_path": "//mcp"}, {"operator_ask_timeout_seconds": 360}, {"call_timeout_seconds": 601}):
        with pytest.raises(ValueError): BlenderBridgeSettings.model_validate(update)


def test_container_constructs_relay_only_when_enabled():
    from app.container import build_container
    from app.settings import BridgeSettings
    assert build_container(BridgeSettings()).blender_relay is None
    assert build_container(BridgeSettings.model_validate({"blender": {"enabled": True}})).blender_relay is not None
