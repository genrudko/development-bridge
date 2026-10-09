import json

from app.container import build_container
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry
from app.api.errors import BridgeError, ErrorCode
from app.tools.visio import _payload_error, _validate_visio_invocation


VISIO_SURFACE = {
    "visio_node_status",
    "visio_tools",
    "visio_list_open_documents",
    "visio_list_diagram_types",
    "visio_snapshot",
    "visio_result_view",
    "visio_managed_update",
    "visio_console_install",
    "visio_operator_reply",
    "visio_operator_ack",
    "visio_operator_notes",
    "visio_transfer_artifact",
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


def test_visio_read_only_tool_does_not_require_mutation_journal():
    _validate_visio_invocation({"tool_name": "list_shapes"})


def test_visio_mutation_requires_explicit_mutation_journal():
    try:
        _validate_visio_invocation({"tool_name": "draw_rectangle"})
    except BridgeError as exc:
        assert exc.code is ErrorCode.POLICY_VIOLATION
        assert "journal.mutation=true" in exc.message
    else:
        raise AssertionError("mutation without journal must fail closed")


def test_visio_unknown_future_tool_is_treated_as_mutation():
    try:
        _validate_visio_invocation({"tool_name": "future_new_tool"})
    except BridgeError as exc:
        assert exc.code is ErrorCode.POLICY_VIOLATION
    else:
        raise AssertionError("unknown tool must fail closed without mutation journal")


def test_visio_in_place_save_is_blocked_even_with_mutation_journal():
    try:
        _validate_visio_invocation({
            "tool_name": "save_document",
            "journal": {"mutation": True},
        })
    except BridgeError as exc:
        assert exc.code is ErrorCode.POLICY_VIOLATION
        assert "In-place Visio save is disabled" in exc.message
    else:
        raise AssertionError("save_document must remain blocked")


def test_visio_mutation_with_explicit_journal_is_allowed():
    _validate_visio_invocation({
        "tool_name": "save_document_as",
        "journal": {"mutation": True},
    })


def test_visio_render_page_png_is_read_only():
    _validate_visio_invocation({"tool_name": "render_page_png"})


def test_visio_internal_managed_update_is_blocked_from_generic_call():
    try:
        _validate_visio_invocation({
            "tool_name": "__openai_visio_managed_update",
            "journal": {"mutation": True},
        })
    except BridgeError as exc:
        assert exc.code is ErrorCode.POLICY_VIOLATION
    else:
        raise AssertionError("internal managed update must not be callable via generic visio_call")


def test_visio_operator_notes_peek_is_read_only():
    _validate_visio_invocation({"tool_name": "operator_notes_peek"})
