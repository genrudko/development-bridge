import json

from app.container import build_container
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry
from app.tools.visio import _payload_error


VISIO_SURFACE = {
    "visio_node_status",
    "visio_tools",
    "visio_call",
    "visio_submit",
    "visio_operation_status",
    "visio_operation_result",
}


def test_visio_tool_surface_is_exact_and_isolated():
    settings = BridgeSettings.model_validate({"server": {"tool_surface": "visio"}})
    registry = build_tool_registry(build_container(settings))

    assert {tool.name for tool in registry.definitions} == VISIO_SURFACE
    assert {registry.get(name).source for name in VISIO_SURFACE} == {"visio-desktop"}


def test_default_full_surface_does_not_gain_visio_tools():
    registry = build_tool_registry(build_container(BridgeSettings()))

    assert VISIO_SURFACE.isdisjoint(tool.name for tool in registry.definitions)


def test_visio_payload_error_detects_upstream_json_error_even_without_iserror():
    value = {
        "content": [
            {
                "type": "text",
                "text": json.dumps({"error": "Visio attach failed"}),
            }
        ],
        "isError": False,
    }

    assert _payload_error(value) == "Visio attach failed"


def test_visio_payload_error_accepts_normal_json_text():
    value = {
        "content": [
            {
                "type": "text",
                "text": json.dumps({"name": "Document1", "pages": 1}),
            }
        ],
        "isError": False,
    }

    assert _payload_error(value) is None
