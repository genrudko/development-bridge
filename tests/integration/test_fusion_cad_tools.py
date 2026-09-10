from __future__ import annotations

import asyncio
import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp import types

from app.api.context import RequestContext
from app.api.errors import BridgeError, ErrorCode
from app.container import ApplicationContainer, build_container
from app.desktop_nodes.service import NodeState
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.service import FusionCadService
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry


def setup_desk1_capabilities(container: ApplicationContainer) -> None:
    from app.fusion_cad.capabilities import CapabilityMatrix
    from app.fusion_cad.models import CapabilityRecord

    all_supported = [
        CapabilityRecord(name=name, state="supported")
        for name in (
            "entity.token_resolver",
            "design.access",
            "timeline.access",
            "sketch.access",
            "inspect.measure",
            "view.camera",
            "view.viewport_conversion",
            "view.pick",
            "selection.primitives",
            "transaction.preview_hooks",
            "transaction.preview_replay",
            "metadata.attributes",
            "style.sketch_text",
            "transaction.undo_redo",
            "revision.mutation_indicators",
            "revision.external_change_detection",
            "export.dxf",
            "view.section",
            "assembly.joints",
        )
    ]
    container.fusion_cad.set_node_capabilities("desk-1", CapabilityMatrix.from_records(all_supported), generation=1)
    container.fusion_cad.revision_tracker.observe("doc_1", "hash-desk1-seed")
    container.fusion_cad.revision_tracker.begin_transaction("tx_1", "doc_1")
    container.fusion_cad.revision_tracker.begin_transaction("tx_1234", "doc_1")
    # Document-bounded inspect resolution: the fast-read describe case targets a
    # face registered in the active document so its opaque ref resolves exactly.
    container.fusion_cad.ref_registry.issue(
        document_ref="doc_1",
        kind="face",
        name="Face1",
        native_token="face_token_1",
        opaque_ref="ent_face_1",
    )
    # Task 8 exact view target resolution: zoom_entity/orient_to_face favorites
    # resolve ent_1 through the ref registry before dispatch.
    container.fusion_cad.ref_registry.issue(
        document_ref="doc_1",
        kind="body",
        name="Body1",
        native_token="body_token_1",
        opaque_ref="ent_1",
    )


def prime_commit_ready(container: ApplicationContainer, tx_id: str) -> None:
    service = container.fusion_cad
    baseline = service.revision_tracker.get_transaction_baseline(tx_id)
    assert baseline is not None
    record = service.transaction_store.find(tx_id)
    if record is None:
        record = service.transaction_store.begin(
            tx_id,
            baseline["document_ref"],
            baseline["baseline_revision"],
            baseline["baseline_fingerprint"],
            {},
        )
    if not record.plan:
        record = service.transaction_store.stage(tx_id, {"action_type": "text_create"})
    if record.preview_evidence is None:
        service.transaction_store.begin_preview(tx_id, record.baseline_fingerprint)
        service.transaction_store.finish_preview(
            tx_id, preview={"replay_signature": {"plan_hash": record.plan_hash}}
        )


@pytest.fixture
def mock_container() -> ApplicationContainer:
    container = build_container(BridgeSettings.model_validate({
        "server": {"public_base_url": "https://127.0.0.1:8000"},
        "desktop_nodes": {"token": "test-desktop-token", "journal_path": ":memory:"}
    }))
    container.desktop_nodes._nodes["desk-1"] = NodeState(
        node_id="desk-1",
        last_seen=time.monotonic(),
        last_seen_wall=time.time(),
        tools=[{"name": "fusion_mcp_execute"}],
        fusion_available=True,
        session_generation=1,
    )
    setup_desk1_capabilities(container)
    return container


def test_fusion_tools_registration(mock_container: ApplicationContainer):
    registry = build_tool_registry(mock_container)
    expected_infra = {
        "fusion_node_status",
        "fusion_tools",
        "fusion_call",
        "fusion_submit",
        "fusion_operation_status",
        "fusion_operation_result",
    }
    expected_domain = {
        "fusion_read",
        "fusion_inspect",
        "fusion_view",
        "fusion_metadata",
        "fusion_style",
        "fusion_validate",
        "fusion_transaction",
    }
    all_expected = expected_infra | expected_domain
    for tool_name in all_expected:
        tool = registry.get(tool_name)
        assert tool is not None, f"Tool {tool_name} not registered"
        assert tool.source == "fusion-desktop"


@pytest.mark.parametrize("tool_name", [
    "fusion_read",
    "fusion_inspect",
    "fusion_view",
    "fusion_metadata",
    "fusion_style",
    "fusion_validate",
    "fusion_transaction",
])
@pytest.mark.asyncio
async def test_domain_tools_reject_invalid_arguments_before_service(mock_container: ApplicationContainer, tool_name: str):
    registry = build_tool_registry(mock_container)
    tool = registry.get(tool_name)
    assert tool is not None

    req_ctx = RequestContext(request_id="req_123")
    params = types.CallToolRequestParams(
        name=tool_name,
        arguments={"node_id": "desk-1", "operation": "unknown_invalid_operation"},
    )
    with pytest.raises(BridgeError) as exc_info:
        await tool.handler(None, params, req_ctx)
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT


@pytest.mark.parametrize("tool_name, valid_payload", [
    ("fusion_read", {"node_id": "desk-1", "operation": "entity", "ref": "ent_1234"}),
    ("fusion_inspect", {"node_id": "desk-1", "operation": "describe", "target": "ent_face_1"}),
    ("fusion_view", {"node_id": "desk-1", "operation": "camera_read"}),
    ("fusion_metadata", {"node_id": "desk-1", "operation": "query", "group": "bridge.cad/v1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "text_read", "text_ref": "text_1234"}),
    ("fusion_transaction", {"node_id": "desk-1", "operation": "status"}),
])
@pytest.mark.asyncio
async def test_fast_reads_execute_sync_with_read_only_journal(
    mock_container: ApplicationContainer,
    tool_name: str,
    valid_payload: dict,
):
    registry = build_tool_registry(mock_container)
    tool = registry.get(tool_name)
    assert tool is not None

    # Task 7: inspect operations carry real semantic normalization, so the
    # describe case returns a valid normalized describe result.
    # Task 8: camera_read carries a real deterministic camera context.
    is_describe = valid_payload["operation"] == "describe"
    is_camera_read = valid_payload["operation"] == "camera_read"
    if is_describe:
        result_data = {
            "operation": "describe",
            "target": {
                "ref": "ent_face_1",
                "kind": "face",
                "name": "Face1",
                "native_type": "BRepFace",
            },
            "frame": {"space": "world", "ref": None},
            "measures": {
                "area": {"quantity": "area", "value": 42.0, "unit": "mm^2"}
            },
        }
    elif valid_payload["operation"] == "text_read":
        result_data = {
            "lineage": {
                "logical_ref": valid_payload["text_ref"],
                "generation": 1,
                "is_current": True,
                "sketch": None,
                "sketch_text_id": None,
                "feature": None,
                "outputs": [],
                "text": "РАСПИСАНИЕ ПЫТОК 😈",
                "font_requested": "Arial",
                "font_used": "Arial",
                "fallback_reason": None,
                "height_mm": 5.0,
            }
        }
    elif is_camera_read:
        result_data = {
            "camera": {
                "eye": [10.0, 20.0, 30.0],
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, 1.0],
                "projection": "perspective",
                "fov_deg": 45.0,
            },
            "viewport": {"width": 1920, "height": 1080},
            "visibility": [
                {
                    "kind": "occurrence",
                    "full_path_name": "Root:Left",
                    "is_visible": True,
                    "effective_visibility": True,
                }
            ],
            "section": {"active": False, "type": None},
        }
    else:
        result_data = {"result_key": "РАСПИСАНИЕ ПЫТОК 😈"}

    mock_container.desktop_nodes.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": f"Executed {valid_payload['operation']} successfully",
                "data": result_data,
            }, ensure_ascii=False),
        }],
        "isError": False,
    })

    req_ctx = RequestContext(request_id="req_123")
    params = types.CallToolRequestParams(
        name=tool_name,
        arguments=valid_payload,
    )
    result = await tool.handler(None, params, req_ctx)
    assert isinstance(result, types.CallToolResult)
    assert not result.is_error
    assert len(result.content) == 1
    content = result.content[0]
    assert isinstance(content, types.TextContent)
    parsed = json.loads(content.text)
    assert parsed["ok"] is True
    if is_describe:
        assert parsed["data"]["data"]["kind"] == "face"
        assert parsed["data"]["data"]["frame"]["space"] == "world"
        assert parsed["data"]["data"]["measures"]["area"]["unit"] == "mm^2"
    elif valid_payload["operation"] == "text_read":
        assert parsed["data"]["data"]["lineage"]["logical_ref"] == valid_payload["text_ref"]
        assert parsed["data"]["data"]["lineage"]["text"] == "РАСПИСАНИЕ ПЫТОК 😈"
    elif is_camera_read:
        assert parsed["data"]["data"]["camera_revision"].startswith("cam_")
        assert parsed["data"]["data"]["visibility_revision"].startswith("vis_")
        assert parsed["data"]["data"]["section_revision"].startswith("sec_")
        assert parsed["data"]["data"]["camera"]["eye"] == [10.0, 20.0, 30.0]
        assert parsed["data"]["data"]["viewport"]["width"] == 1920
        assert parsed["data"]["data"]["viewport"]["height"] == 1080
    else:
        assert parsed["data"]["data"]["result_key"] == "РАСПИСАНИЕ ПЫТОК 😈"

    assert mock_container.desktop_nodes.call.called
    call_args = mock_container.desktop_nodes.call.call_args
    journal = call_args[0][3] if len(call_args[0]) > 3 else call_args[1].get("journal")
    assert isinstance(journal, dict)
    assert journal.get("mutation") is False


@pytest.mark.parametrize("tool_name, valid_payload, expected_mutation", [
    ("fusion_metadata", {"node_id": "desk-1", "operation": "tag", "target": "ent_1", "tag_name": "bolt", "expected_revision": "rev_1"}, True),
    ("fusion_style", {"node_id": "desk-1", "operation": "show", "target": "ent_1", "expected_revision": "rev_1"}, True),
    ("fusion_style", {"node_id": "desk-1", "operation": "text_create", "text": "Label", "height_mm": 5.0, "position": {"x": 0, "y": 0, "z": 0, "frame": {"space": "world"}}, "expected_revision": "rev_1"}, True),
    ("fusion_validate", {"node_id": "desk-1", "operation": "run"}, False),
    ("fusion_view", {"node_id": "desk-1", "operation": "screenshot"}, False),
    ("fusion_view", {"node_id": "desk-1", "operation": "camera_set", "fov": 45.0}, True),
    ("fusion_view", {"node_id": "desk-1", "operation": "fit"}, True),
    ("fusion_view", {"node_id": "desk-1", "operation": "zoom_entity", "target": "ent_1"}, True),
    ("fusion_view", {"node_id": "desk-1", "operation": "orient_to_face", "target": "ent_1"}, True),
    ("fusion_transaction", {"node_id": "desk-1", "operation": "begin"}, True),
    ("fusion_transaction", {"node_id": "desk-1", "operation": "stage", "transaction_id": "tx_1234", "action": {"action_type": "show", "target": "ent_1"}}, True),
    ("fusion_transaction", {"node_id": "desk-1", "operation": "abort", "transaction_id": "tx_1234"}, True),
    ("fusion_transaction", {"node_id": "desk-1", "operation": "preview", "transaction_id": "tx_1234", "expected_revision": "rev_1"}, True),
    ("fusion_transaction", {"node_id": "desk-1", "operation": "commit", "transaction_id": "tx_1234", "expected_revision": "rev_1"}, True),
    ("fusion_transaction", {"node_id": "desk-1", "operation": "rollback", "transaction_id": "tx_1234"}, True),
    ("fusion_read", {"node_id": "desk-1", "operation": "model_snapshot", "detail": "full"}, False),
])
@pytest.mark.asyncio
async def test_mutations_and_long_ops_use_async_submit_lifecycle(
    mock_container: ApplicationContainer,
    tool_name: str,
    valid_payload: dict,
    expected_mutation: bool,
):
    registry = build_tool_registry(mock_container)
    tool = registry.get(tool_name)
    assert tool is not None

    mock_container.desktop_nodes.submit = AsyncMock(return_value={
        "operation_id": "op_987654321",
        "status": "queued",
    })

    if tool_name == "fusion_transaction" and valid_payload.get("operation") == "commit":
        prime_commit_ready(mock_container, valid_payload["transaction_id"])

    req_ctx = RequestContext(request_id="req_async_1")
    params = types.CallToolRequestParams(
        name=tool_name,
        arguments=valid_payload,
    )
    result = await tool.handler(None, params, req_ctx)
    assert isinstance(result, types.CallToolResult)
    assert not result.is_error
    assert len(result.content) == 1
    content = result.content[0]
    assert isinstance(content, types.TextContent)
    parsed = json.loads(content.text)
    assert parsed["ok"] is True
    assert parsed["data"]["operation_id"] == "op_987654321"
    assert parsed["data"]["status"] == "queued"

    assert mock_container.desktop_nodes.submit.called
    call_args = mock_container.desktop_nodes.submit.call_args
    journal = call_args[0][3] if len(call_args[0]) > 3 else call_args[1].get("journal")
    assert isinstance(journal, dict)
    assert journal.get("mutation") is expected_mutation


@pytest.mark.asyncio
async def test_native_is_error_true_malformed_text_fails_closed(mock_container: ApplicationContainer):
    registry = build_tool_registry(mock_container)
    tool = registry.get("fusion_read")
    assert tool is not None

    mock_container.desktop_nodes.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": "Traceback (most recent call last):\n  File 'fusion_script.py', line 12\nZeroDivisionError: division by zero",
        }],
        "isError": True,
    })

    req_ctx = RequestContext(request_id="req_fail_1")
    params = types.CallToolRequestParams(
        name="fusion_read",
        arguments={"node_id": "desk-1", "operation": "entity", "ref": "ent_1234"},
    )
    with pytest.raises(FusionCadError) as exc_info:
        await tool.handler(None, params, req_ctx)
    assert exc_info.value.code == ErrorCode.FUSION_API_ERROR
    assert "ZeroDivisionError" in exc_info.value.message or "failed" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_native_is_error_true_structured_domain_error(mock_container: ApplicationContainer):
    registry = build_tool_registry(mock_container)
    tool = registry.get("fusion_read")
    assert tool is not None

    mock_container.desktop_nodes.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "failed",
                "error": {
                    "code": "TYPE_MISMATCH",
                    "message": "Expected BRepFace, got BRepEdge",
                    "details": {"entity": "ent_1234"},
                },
            }),
        }],
        "isError": True,
    })

    req_ctx = RequestContext(request_id="req_fail_2")
    params = types.CallToolRequestParams(
        name="fusion_read",
        arguments={"node_id": "desk-1", "operation": "entity", "ref": "ent_1234"},
    )
    with pytest.raises(BridgeError) as exc_info:
        await tool.handler(None, params, req_ctx)
    assert exc_info.value.code == ErrorCode.TYPE_MISMATCH
    assert exc_info.value.retryable is False


@pytest.mark.asyncio
async def test_native_non_json_or_unrecognized_domain_output_fails_closed(mock_container: ApplicationContainer):
    registry = build_tool_registry(mock_container)
    tool = registry.get("fusion_read")
    assert tool is not None

    # Case A: isError is False, but text is non-JSON
    mock_container.desktop_nodes.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": "Some plain text output that is not JSON",
        }],
        "isError": False,
    })

    req_ctx = RequestContext(request_id="req_malformed_1")
    params = types.CallToolRequestParams(
        name="fusion_read",
        arguments={"node_id": "desk-1", "operation": "entity", "ref": "ent_1234"},
    )
    with pytest.raises(FusionCadError) as exc_info:
        await tool.handler(None, params, req_ctx)
    assert exc_info.value.code == ErrorCode.FUSION_API_ERROR

    # Case B: isError is False, valid JSON, but missing api_version 'fusion.cad/v1'
    mock_container.desktop_nodes.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps({"status": "succeeded", "arbitrary_data": 42}),
        }],
        "isError": False,
    })
    with pytest.raises(FusionCadError) as exc_info:
        await tool.handler(None, params, req_ctx)
    assert exc_info.value.code == ErrorCode.FUSION_API_ERROR
    assert "Unrecognized domain output" in exc_info.value.message


@pytest.mark.parametrize("group, operation, payload, expected_async, expected_mutation", [
    # fusion_read
    ("read", "entity", {"operation": "entity", "ref": "ent_1"}, False, False),
    ("read", "feature_tree", {"operation": "feature_tree"}, False, False),
    ("read", "sketch", {"operation": "sketch", "ref": "ent_1"}, False, False),
    ("read", "parameters", {"operation": "parameters"}, False, False),
    ("read", "visibility", {"operation": "visibility"}, False, False),
    ("read", "selection", {"operation": "selection"}, False, False),
    ("read", "query", {"operation": "query", "selector": {"kind": ["face"]}}, False, False),
    ("read", "capabilities", {"operation": "capabilities"}, False, False),
    ("read", "model_snapshot", {"operation": "model_snapshot", "detail": "compact"}, False, False),
    ("read", "model_snapshot", {"operation": "model_snapshot", "detail": "full"}, True, False),
    ("read", "model_snapshot", {"operation": "model_snapshot", "include_views": True}, True, False),

    # fusion_inspect (15 operations)
    ("inspect", "describe", {"operation": "describe", "target": "ent_1"}, False, False),
    ("inspect", "bounding_box", {"operation": "bounding_box", "target": "ent_1", "frame": {"space": "world"}}, False, False),
    ("inspect", "oriented_bbox", {"operation": "oriented_bbox", "target": "ent_1"}, False, False),
    ("inspect", "centroid", {"operation": "centroid", "target": "ent_1", "frame": {"space": "world"}}, False, False),
    ("inspect", "area", {"operation": "area", "target": "ent_1"}, False, False),
    ("inspect", "perimeter", {"operation": "perimeter", "target": "ent_1"}, False, False),
    ("inspect", "volume", {"operation": "volume", "target": "ent_1"}, False, False),
    ("inspect", "distance", {"operation": "distance", "target_a": "ent_1", "target_b": "ent_2"}, False, False),
    ("inspect", "minimum_distance", {"operation": "minimum_distance", "target_a": "ent_1", "target_b": "ent_2"}, False, False),
    ("inspect", "angle", {"operation": "angle", "target_a": "ent_1", "target_b": "ent_2"}, False, False),
    ("inspect", "parallel", {"operation": "parallel", "target_a": "ent_1", "target_b": "ent_2"}, False, False),
    ("inspect", "perpendicular", {"operation": "perpendicular", "target_a": "ent_1", "target_b": "ent_2"}, False, False),
    ("inspect", "coplanar", {"operation": "coplanar", "target_a": "ent_1", "target_b": "ent_2"}, False, False),
    ("inspect", "concentric", {"operation": "concentric", "target_a": "ent_1", "target_b": "ent_2"}, False, False),
    ("inspect", "face_to_face_thickness", {"operation": "face_to_face_thickness", "face_a": "ent_1", "face_b": "ent_2"}, False, False),

    # fusion_view (8 operations)
    ("view", "camera_read", {"operation": "camera_read"}, False, False),
    ("view", "pick", {"operation": "pick", "view_ref": "view_1", "x": 0.5, "y": 0.5}, False, False),
    ("view", "camera_set", {"operation": "camera_set", "fov": 45.0}, True, True),
    ("view", "fit", {"operation": "fit"}, True, True),
    ("view", "zoom_entity", {"operation": "zoom_entity", "target": "ent_1"}, True, True),
    ("view", "orient_to_face", {"operation": "orient_to_face", "target": "ent_1"}, True, True),
    ("view", "standard_view", {"operation": "standard_view", "view_type": "top"}, True, True),
    ("view", "screenshot", {"operation": "screenshot"}, True, False),

    # fusion_metadata (9 operations)
    ("mutate", "get", {"operation": "get", "target": "ent_1"}, False, False),
    ("mutate", "query", {"operation": "query"}, False, False),
    ("mutate", "provenance", {"operation": "provenance", "target": "ent_1"}, False, False),
    ("mutate", "set", {"operation": "set", "target": "ent_1", "name": "k", "value": "v"}, True, True),
    ("mutate", "remove", {"operation": "remove", "target": "ent_1", "name": "k"}, True, True),
    ("mutate", "tag", {"operation": "tag", "target": "ent_1", "tag_name": "t"}, True, True),
    ("mutate", "untag", {"operation": "untag", "target": "ent_1", "tag_name": "t"}, True, True),
    ("mutate", "set_role", {"operation": "set_role", "target": "ent_1", "role": "r"}, True, True),
    ("mutate", "clear_role", {"operation": "clear_role", "target": "ent_1"}, True, True),

    # fusion_style (12 operations)
    ("mutate", "text_read", {"operation": "text_read", "text_ref": "text_1"}, False, False),
    ("mutate", "text_create", {"operation": "text_create", "text": "t", "height_mm": 5.0, "position": {"x": 0, "y": 0, "z": 0, "frame": {"space": "world"}}}, True, True),
    ("mutate", "text_update", {"operation": "text_update", "text_ref": "text_1"}, True, True),
    ("mutate", "text_delete", {"operation": "text_delete", "text_ref": "text_1"}, True, True),
    ("mutate", "text_extrude", {"operation": "text_extrude", "text_ref": "text_1", "distance_mm": 2.0}, True, True),
    ("mutate", "text_cut", {"operation": "text_cut", "text_ref": "text_1", "distance_mm": 2.0, "target_body": "ent_1"}, True, True),
    ("mutate", "show", {"operation": "show", "target": "ent_1"}, True, True),
    ("mutate", "hide", {"operation": "hide", "target": "ent_1"}, True, True),
    ("mutate", "set", {"operation": "set", "target": "ent_1", "visible": True}, True, True),
    ("mutate", "show_only", {"operation": "show_only", "target": "ent_1"}, True, True),
    ("mutate", "isolate", {"operation": "isolate", "target": "ent_1"}, True, True),
    ("mutate", "restore", {"operation": "restore"}, True, True),

    # fusion_validate
    ("validate", "run", {"operation": "run"}, True, False),

    # fusion_transaction
    ("transaction", "begin", {"operation": "begin"}, True, True),
    ("transaction", "stage", {"operation": "stage", "transaction_id": "tx_1", "action": {"action_type": "show", "target": "ent_1"}}, True, True),
    ("transaction", "status", {"operation": "status"}, False, False),
    ("transaction", "abort", {"operation": "abort", "transaction_id": "tx_1"}, True, True),
    ("transaction", "preview", {"operation": "preview", "transaction_id": "tx_1"}, True, True),
    ("transaction", "commit", {"operation": "commit", "transaction_id": "tx_1"}, True, True),
    ("transaction", "rollback", {"operation": "rollback", "transaction_id": "tx_1"}, True, True),
])
def test_exhaustive_operation_classification(
    mock_container: ApplicationContainer,
    group: str,
    operation: str,
    payload: dict,
    expected_async: bool,
    expected_mutation: bool,
):
    service = mock_container.fusion_cad
    is_async, is_mutation, summary = service._classify_operation(group, payload)
    assert is_async == expected_async, f"Operation {group}:{operation} is_async mismatch"
    assert is_mutation == expected_mutation, f"Operation {group}:{operation} is_mutation mismatch"
    assert summary == f"{group}:{operation}"


@pytest.mark.asyncio
async def test_capabilities_read_is_publicly_nonmutating_but_transport_is_uncertainty_sensitive(
    mock_container: ApplicationContainer,
):
    service = mock_container.fusion_cad
    is_async, is_mutation, summary = service._classify_operation(
        "read", {"operation": "capabilities"}
    )
    assert is_async is False
    assert is_mutation is False
    assert summary == "read:capabilities"

    captured = {}

    async def fail_after_dispatch(node_id, tool_name, arguments, journal=None):
        captured["journal"] = journal
        raise BridgeError(
            ErrorCode.DESKTOP_NODE_TIMEOUT,
            "capability probe dispatch sentinel",
            retryable=False,
        )

    mock_container.desktop_nodes.call = AsyncMock(side_effect=fail_after_dispatch)
    with pytest.raises(BridgeError) as exc_info:
        await service.execute(
            {"node_id": "desk-1", "operation": "capabilities"},
            group="read",
        )
    assert exc_info.value.code == ErrorCode.DESKTOP_NODE_TIMEOUT
    assert captured["journal"]["mutation"] is True
    assert captured["journal"]["summary"] == "read:capabilities"


@pytest.mark.parametrize("tool_name, payload", [
    ("fusion_view", {"node_id": "desk-1", "operation": "camera_set", "fov": 45.0}),
    ("fusion_view", {"node_id": "desk-1", "operation": "fit"}),
    ("fusion_view", {"node_id": "desk-1", "operation": "zoom_entity", "target": "ent_1"}),
    ("fusion_view", {"node_id": "desk-1", "operation": "orient_to_face", "target": "ent_1"}),
    ("fusion_view", {"node_id": "desk-1", "operation": "standard_view", "view_type": "top"}),
    ("fusion_metadata", {"node_id": "desk-1", "operation": "set", "target": "ent_1", "name": "k", "value": "v", "expected_revision": "rev_1"}),
    ("fusion_metadata", {"node_id": "desk-1", "operation": "remove", "target": "ent_1", "name": "k", "expected_revision": "rev_1"}),
    ("fusion_metadata", {"node_id": "desk-1", "operation": "tag", "target": "ent_1", "tag_name": "t", "expected_revision": "rev_1"}),
    ("fusion_metadata", {"node_id": "desk-1", "operation": "untag", "target": "ent_1", "tag_name": "t", "expected_revision": "rev_1"}),
    ("fusion_metadata", {"node_id": "desk-1", "operation": "set_role", "target": "ent_1", "role": "r", "expected_revision": "rev_1"}),
    ("fusion_metadata", {"node_id": "desk-1", "operation": "clear_role", "target": "ent_1", "expected_revision": "rev_1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "text_create", "text": "t", "height_mm": 5.0, "position": {"x": 0, "y": 0, "z": 0, "frame": {"space": "world"}}, "expected_revision": "rev_1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "text_update", "text_ref": "text_1", "expected_revision": "rev_1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "text_delete", "text_ref": "text_1", "expected_revision": "rev_1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "text_extrude", "text_ref": "text_1", "distance_mm": 2.0, "expected_revision": "rev_1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "text_cut", "text_ref": "text_1", "distance_mm": 2.0, "target_body": "ent_1", "expected_revision": "rev_1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "show", "target": "ent_1", "expected_revision": "rev_1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "hide", "target": "ent_1", "expected_revision": "rev_1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "set", "target": "ent_1", "visible": True, "expected_revision": "rev_1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "show_only", "target": "ent_1", "expected_revision": "rev_1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "isolate", "target": "ent_1", "expected_revision": "rev_1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "restore", "expected_revision": "rev_1"}),
    ("fusion_transaction", {"node_id": "desk-1", "operation": "begin"}),
    ("fusion_transaction", {"node_id": "desk-1", "operation": "stage", "transaction_id": "tx_1", "action": {"action_type": "show", "target": "ent_1"}}),
    ("fusion_transaction", {"node_id": "desk-1", "operation": "abort", "transaction_id": "tx_1"}),
    ("fusion_transaction", {"node_id": "desk-1", "operation": "preview", "transaction_id": "tx_1"}),
    ("fusion_transaction", {"node_id": "desk-1", "operation": "commit", "transaction_id": "tx_1"}),
    ("fusion_transaction", {"node_id": "desk-1", "operation": "rollback", "transaction_id": "tx_1"}),
])
@pytest.mark.asyncio
async def test_state_changing_operations_marked_mutating_and_non_replayable_on_timeout(
    tool_name: str,
    payload: dict,
    tmp_path,
):
    tool_to_group = {
        "fusion_read": "read",
        "fusion_inspect": "inspect",
        "fusion_view": "view",
        "fusion_metadata": "mutate",
        "fusion_style": "mutate",
        "fusion_validate": "validate",
        "fusion_transaction": "transaction",
    }
    container = build_container(BridgeSettings.model_validate({
        "server": {"public_base_url": "https://127.0.0.1:8000"},
        "desktop_nodes": {
            "token": "test-token",
            "journal_path": str(tmp_path / "journal.jsonl"),
            "call_timeout_seconds": 0.05,
        },
    }))
    setup_desk1_capabilities(container)
    registry = build_tool_registry(container)
    tool = registry.get(tool_name)
    assert tool is not None

    await container.desktop_nodes.register(
        "desk-1",
        [{"name": "fusion_mcp_execute"}],
        fusion_available=True,
    )

    if tool_name == "fusion_transaction" and payload.get("operation") == "commit":
        prime_commit_ready(container, payload["transaction_id"])

    group = tool_to_group[tool_name]
    is_async, is_mutation, _ = container.fusion_cad._classify_operation(
        group,
        payload,
    )
    assert is_mutation is True, f"Operation {tool_name} {payload['operation']} must have mutation=True"

    if not is_async:
        req_ctx = RequestContext(request_id="req_timeout_1")
        params = types.CallToolRequestParams(name=tool_name, arguments=payload)

        call_task = asyncio.create_task(tool.handler(None, params, req_ctx))

        claimed = await container.desktop_nodes.claim("desk-1", wait_seconds=1.0)
        assert claimed is not None
        op_id = claimed["operation_id"]

        with pytest.raises(BridgeError) as exc_info:
            await call_task
        assert exc_info.value.code == ErrorCode.DESKTOP_NODE_TIMEOUT
        assert exc_info.value.retryable is False

        status_data = container.desktop_nodes.operation_status("desk-1", op_id)
        assert status_data["status"] == "uncertain"
        assert status_data["mutation"] is True
    else:
        req_ctx = RequestContext(request_id="req_async_mutation")
        params = types.CallToolRequestParams(name=tool_name, arguments=payload)
        res = await tool.handler(None, params, req_ctx)
        assert not res.is_error
        parsed = json.loads(res.content[0].text)
        op_id = parsed["data"]["operation_id"]
        status_data = container.desktop_nodes.operation_status("desk-1", op_id)
        assert status_data["mutation"] is True



@pytest.mark.asyncio
async def test_fusion_tool_renders_external_result(mock_container: ApplicationContainer):
    registry = build_tool_registry(mock_container)
    tool = registry.get("fusion_read")
    assert tool is not None

    mock_container.desktop_nodes.call = AsyncMock(return_value={
        "external_result": {
            "result_id": "res_123",
            "size_bytes": 1024,
            "sha256": "abcdef",
        },
    })
    mock_container.desktop_nodes.overwrite_external_result = MagicMock()
    mock_container.desktop_nodes.external_result = MagicMock(return_value=(
        {
            "api_version": "fusion.cad/v1",
            "status": "succeeded",
            "summary": "Read entity ent_1234",
            "data": {"ref": "ent_1234"},
        },
        {
            "result_id": "res_123",
            "size_bytes": 1024,
            "sha256": "abcdef",
            "file_name": "fusion-result-res_123.json",
            "export_url": "http://localhost:8080/export/res_123",
            "resources": [{
                "uri": "http://localhost:8080/image/1",
                "file_name": "image.png",
                "mime_type": "image/png",
                "size_bytes": 500,
            }],
        },
    ))

    req_ctx = RequestContext(request_id="req_123")
    params = types.CallToolRequestParams(
        name="fusion_read",
        arguments={"node_id": "desk-1", "operation": "entity", "ref": "ent_1234"},
    )
    result = await tool.handler(None, params, req_ctx)
    assert isinstance(result, types.CallToolResult)
    assert not result.is_error
    resource_links = [b for b in result.content if isinstance(b, types.ResourceLink)]
    assert len(resource_links) == 2


@pytest.mark.parametrize("binary_shape, payload_data", [
    (
        "png_magic_base64",
        {"thumbnail_b64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="},
    ),
    (
        "data_uri_png",
        {"preview_image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="},
    ),
    (
        "model_stl_data_uri",
        {"stl_data": "data:model/stl;base64," + base64.b64encode(b"solid test\nfacet normal 0 0 0\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid test\n").decode()},
    ),
    (
        "jpeg_magic_base64",
        {"image_data": "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="},
    ),
    (
        "pdf_magic_base64",
        {"document_bytes": "JVBERi0xLjQKJcOkw7zDtsOfCjIgMCBvYmoKPDwvTGVuZ3RoIDM+PgpzdHJlYW0KYmJjCmVuZHN0cmVhbQplbmRvYmo="},
    ),
    (
        "zip_3mf_magic_base64",
        {"archive_mesh": "UEsDBAoAAAAAAACGvlVFAAAAAAAAAAAAAAAACQAAAHZpZXcvM21mUEsBAj8ACgAAAAAAAIa+VUUAAAAAAAAAAAAAAAAJAAAAAAAAAAAAAAC0gQAAAAB2aWV3LzNtZlBLBQYAAAAAAQABAEAAAABVAAAAAAA="},
    ),
    (
        "raw_bytes_in_dict",
        {"binary_data": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"},
    ),
    (
        "nested_in_artifacts_list",
        {"artifacts": [{"type": "image", "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "mimeType": "image/png"}]},
    ),
    (
        "blob_arbitrary_binary_base64",
        {"blob": "AAECAwQFBgcICQ=="},
    ),
    (
        "bytes_arbitrary_binary_base64",
        {"bytes": "EBEiM0RVZnd4eXo="},
    ),
    (
        "base64_arbitrary_binary_base64",
        {"base64": "ICElJicoKSorLC0="},
    ),
])
@pytest.mark.asyncio
async def test_comprehensive_binary_and_base64_shapes_externalization(
    mock_container: ApplicationContainer,
    binary_shape: str,
    payload_data: dict,
):
    registry = build_tool_registry(mock_container)
    tool = registry.get("fusion_read")
    assert tool is not None

    if "binary_data" in payload_data and isinstance(payload_data["binary_data"], (bytes, bytearray)):
        mock_container.desktop_nodes.call = AsyncMock(return_value={
            "api_version": "fusion.cad/v1",
            "status": "succeeded",
            "summary": f"result for {binary_shape}",
            "data": payload_data,
            "isError": False,
        })
    else:
        mock_container.desktop_nodes.call = AsyncMock(return_value={
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({
                        "api_version": "fusion.cad/v1",
                        "status": "succeeded",
                        "summary": f"result for {binary_shape}",
                        "data": payload_data,
                    }),
                },
            ],
            "isError": False,
        })


    req_ctx = RequestContext(request_id=f"req_bin_{binary_shape}")
    params = types.CallToolRequestParams(
        name="fusion_read",
        arguments={"node_id": "desk-1", "operation": "entity", "ref": "ent_1234"},
    )
    result = await tool.handler(None, params, req_ctx)
    assert isinstance(result, types.CallToolResult)
    assert not result.is_error

    for block in result.content:
        if isinstance(block, types.TextContent):
            parsed = json.loads(block.text)
            assert "external_result" in parsed["data"]
            assert "iVBORw0KGgo" not in block.text
            assert "/9j/" not in block.text
            assert "JVBERi0" not in block.text
            assert "UEsDB" not in block.text
            assert "AAECAwQFBgcICQ==" not in block.text
            assert "EBEiM0RVZnd4eXo=" not in block.text
            assert "ICElJicoKSorLC0=" not in block.text

    resource_links = [b for b in result.content if isinstance(b, types.ResourceLink)]
    assert len(resource_links) >= 1


@pytest.mark.asyncio
async def test_unambiguous_binary_keys_externalization_and_semantic_visibility(
    mock_container: ApplicationContainer,
):
    registry = build_tool_registry(mock_container)
    tool = registry.get("fusion_read")
    assert tool is not None

    blob_b64 = base64.b64encode(b"\x01\x02\x03\x04\x05\x06\x07\x08").decode("ascii")
    bytes_b64 = base64.b64encode(b"\x11\x12\x13\x14\x15\x16\x17\x18").decode("ascii")
    base64_b64 = base64.b64encode(b"\x21\x22\x23\x24\x25\x26\x27\x28").decode("ascii")

    for key_name, b64_val in [("blob", blob_b64), ("bytes", bytes_b64), ("base64", base64_b64)]:
        mock_container.desktop_nodes.call = AsyncMock(return_value={
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "api_version": "fusion.cad/v1",
                    "status": "succeeded",
                    "summary": f"result for {key_name}",
                    "data": {key_name: b64_val},
                }),
            }],
            "isError": False,
        })
        req_ctx = RequestContext(request_id=f"req_unambiguous_{key_name}")
        params = types.CallToolRequestParams(
            name="fusion_read",
            arguments={"node_id": "desk-1", "operation": "entity", "ref": "ent_1234"},
        )
        result = await tool.handler(None, params, req_ctx)
        assert isinstance(result, types.CallToolResult)
        assert not result.is_error
        text_blocks = [b for b in result.content if isinstance(b, types.TextContent)]
        assert len(text_blocks) == 1
        parsed = json.loads(text_blocks[0].text)
        assert "external_result" in parsed["data"]
        assert b64_val not in text_blocks[0].text
        resource_links = [b for b in result.content if isinstance(b, types.ResourceLink)]
        assert len(resource_links) == 2
        assert any(link.name.endswith(".bin") for link in resource_links)
        assert any(link.mime_type == "application/json" for link in resource_links)

    # Contrast with non-binary generic data and semantic strings without magic: remains model-visible
    mock_container.desktop_nodes.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "generic payload",
                "data": {
                    "data": blob_b64,
                    "description": "Just regular text describing model",
                },
            }),
        }],
        "isError": False,
    })
    req_ctx = RequestContext(request_id="req_generic_visible")
    params = types.CallToolRequestParams(
        name="fusion_read",
        arguments={"node_id": "desk-1", "operation": "entity", "ref": "ent_1234"},
    )
    result = await tool.handler(None, params, req_ctx)
    assert isinstance(result, types.CallToolResult)
    assert not result.is_error
    text_blocks = [b for b in result.content if isinstance(b, types.TextContent)]
    assert len(text_blocks) == 1
    parsed = json.loads(text_blocks[0].text)
    assert "external_result" not in parsed["data"]
    assert parsed["data"]["data"]["data"] == blob_b64
    assert parsed["data"]["data"]["description"] == "Just regular text describing model"
    resource_links = [b for b in result.content if isinstance(b, types.ResourceLink)]
    assert len(resource_links) == 0


@pytest.mark.asyncio
async def test_cad_error_raises_with_correct_code_and_retryable(mock_container: ApplicationContainer):
    registry = build_tool_registry(mock_container)
    tool = registry.get("fusion_read")
    assert tool is not None

    mock_container.desktop_nodes.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "failed",
                "error": {
                    "code": "REVISION_CONFLICT",
                    "message": "Model revision changed externally",
                    "details": {"current_revision": "rev_2", "expected_revision": "rev_1"},
                },
            }, ensure_ascii=False),
        }],
        "isError": False,
    })

    req_ctx = RequestContext(request_id="req_123")
    params = types.CallToolRequestParams(
        name="fusion_read",
        arguments={"node_id": "desk-1", "operation": "entity", "ref": "ent_1234"},
    )
    with pytest.raises(BridgeError) as exc_info:
        await tool.handler(None, params, req_ctx)
    assert exc_info.value.code == ErrorCode.REVISION_CONFLICT
    assert exc_info.value.retryable is False


def test_container_no_global_singleton():
    c1 = build_container(BridgeSettings())
    c2 = build_container(BridgeSettings())
    assert c1.fusion_cad is not c2.fusion_cad
    assert isinstance(c1.fusion_cad, FusionCadService)


@pytest.mark.asyncio
async def test_generic_key_data_with_plain_text_remains_model_visible(mock_container: ApplicationContainer):
    registry = build_tool_registry(mock_container)
    tool = registry.get("fusion_read")
    assert tool is not None

    semantic_payload = {
        "api_version": "fusion.cad/v1",
        "status": "succeeded",
        "summary": "Model snapshot read",
        "data": {
            "component_count": 5,
            "feature_names": ["extrude_1", "fillet_2", "cut_3"],
            "annotation": "Ordinary semantic text data",
        },
    }
    mock_container.desktop_nodes.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps(semantic_payload),
        }],
        "isError": False,
    })

    req_ctx = RequestContext(request_id="req_semantic_data")
    params = types.CallToolRequestParams(
        name="fusion_read",
        arguments={"node_id": "desk-1", "operation": "entity", "ref": "ent_1234"},
    )
    result = await tool.handler(None, params, req_ctx)
    assert isinstance(result, types.CallToolResult)
    assert not result.is_error
    assert len(result.content) == 1
    content_text = result.content[0].text
    parsed = json.loads(content_text)
    assert parsed["ok"] is True
    # Verify semantic fields remain directly visible and were NOT externalized
    assert "external_result" not in parsed["data"]
    assert parsed["data"]["data"]["annotation"] == "Ordinary semantic text data"
    assert parsed["data"]["data"]["feature_names"] == ["extrude_1", "fillet_2", "cut_3"]


@pytest.mark.parametrize("invalid_shape, raw_output", [
    ("malformed_json", "Traceback (most recent call last):\nScriptError: syntax error"),
    ("wrong_api_version", json.dumps({"api_version": "wrong.version/v2", "status": "succeeded", "data": {}})),
    ("invalid_cad_result_schema", json.dumps({"api_version": "fusion.cad/v1", "status": "unknown_status", "data": {}})),
    ("native_is_error", json.dumps({"api_version": "fusion.cad/v1", "status": "failed", "error": {"code": "FUSION_API_ERROR", "message": "Crash"}})),
])
@pytest.mark.asyncio
async def test_async_domain_operation_result_fails_closed(
    tmp_path,
    invalid_shape: str,
    raw_output: str,
):
    container = build_container(BridgeSettings.model_validate({
        "server": {"public_base_url": "https://127.0.0.1:8000"},
        "desktop_nodes": {
            "token": "test-token",
            "journal_path": str(tmp_path / "journal.jsonl"),
            "result_artifact_directory": str(tmp_path / "artifacts"),
        },
    }))
    setup_desk1_capabilities(container)
    registry = build_tool_registry(container)
    op_result_tool = registry.get("fusion_operation_result")
    assert op_result_tool is not None

    await container.desktop_nodes.register(
        "desk-1",
        [{"name": "fusion_mcp_execute"}],
        fusion_available=True,
    )

    # Submit domain operation (summary="validate:run")
    submit_res = await container.fusion_cad.execute({
        "node_id": "desk-1",
        "operation": "run",
    }, group="validate")
    assert isinstance(submit_res, dict)
    op_id = submit_res["operation_id"]

    claimed = await container.desktop_nodes.claim("desk-1", wait_seconds=1.0)
    assert claimed is not None
    cmd_id = claimed["command_id"]

    # Submit the invalid result
    if invalid_shape == "native_is_error":
        node_result = {
            "content": [{"type": "text", "text": raw_output}],
            "isError": True,
        }
    else:
        node_result = {
            "content": [{"type": "text", "text": raw_output}],
            "isError": False,
        }

    await container.desktop_nodes.submit_result("desk-1", cmd_id, node_result)

    # Query operation_result
    req_ctx = RequestContext(request_id=f"req_op_fail_{invalid_shape}")
    params = types.CallToolRequestParams(
        name="fusion_operation_result",
        arguments={"node_id": "desk-1", "operation_id": op_id},
    )

    with pytest.raises((FusionCadError, BridgeError)):
        await op_result_tool.handler(None, params, req_ctx)


@pytest.mark.asyncio
async def test_async_domain_operation_result_succeeds_for_valid_cad_result(tmp_path):
    container = build_container(BridgeSettings.model_validate({
        "server": {"public_base_url": "https://127.0.0.1:8000"},
        "desktop_nodes": {
            "token": "test-token",
            "journal_path": str(tmp_path / "journal.jsonl"),
            "result_artifact_directory": str(tmp_path / "artifacts"),
        },
    }))
    setup_desk1_capabilities(container)
    registry = build_tool_registry(container)
    op_result_tool = registry.get("fusion_operation_result")
    assert op_result_tool is not None

    await container.desktop_nodes.register(
        "desk-1",
        [{"name": "fusion_mcp_execute"}],
        fusion_available=True,
    )

    # Submit domain operation
    submit_res = await container.fusion_cad.execute({
        "node_id": "desk-1",
        "operation": "run",
    }, group="validate")
    op_id = submit_res["operation_id"]

    claimed = await container.desktop_nodes.claim("desk-1", wait_seconds=1.0)
    cmd_id = claimed["command_id"]

    valid_cad_result = {
        "api_version": "fusion.cad/v1",
        "status": "succeeded",
        "summary": "Validation run passed",
        "data": {"passed": True, "findings": []},
    }
    await container.desktop_nodes.submit_result("desk-1", cmd_id, {
        "content": [{"type": "text", "text": json.dumps(valid_cad_result)}],
        "isError": False,
    })

    req_ctx = RequestContext(request_id="req_op_success")
    params = types.CallToolRequestParams(
        name="fusion_operation_result",
        arguments={"node_id": "desk-1", "operation_id": op_id},
    )
    res = await op_result_tool.handler(None, params, req_ctx)
    assert isinstance(res, types.CallToolResult)
    assert not res.is_error
    parsed = json.loads(res.content[0].text)
    assert parsed["ok"] is True
    assert "external_result" in parsed["data"]


@pytest.mark.asyncio
async def test_generic_infrastructure_operation_result_preserves_non_domain_json(tmp_path):
    container = build_container(BridgeSettings.model_validate({
        "server": {"public_base_url": "https://127.0.0.1:8000"},
        "desktop_nodes": {
            "token": "test-token",
            "journal_path": str(tmp_path / "journal.jsonl"),
            "result_artifact_directory": str(tmp_path / "artifacts"),
        },
    }))
    registry = build_tool_registry(container)
    submit_tool = registry.get("fusion_submit")
    op_result_tool = registry.get("fusion_operation_result")
    assert submit_tool is not None and op_result_tool is not None

    await container.desktop_nodes.register(
        "desk-1",
        [{"name": "generic_custom_tool"}],
        fusion_available=True,
    )

    req_ctx = RequestContext(request_id="req_gen_submit")
    submit_params = types.CallToolRequestParams(
        name="fusion_submit",
        arguments={"node_id": "desk-1", "tool_name": "generic_custom_tool", "arguments": {"foo": "bar"}},
    )
    submit_res = await submit_tool.handler(None, submit_params, req_ctx)
    parsed_submit = json.loads(submit_res.content[0].text)
    op_id = parsed_submit["data"]["operation_id"]

    claimed = await container.desktop_nodes.claim("desk-1", wait_seconds=1.0)
    cmd_id = claimed["command_id"]

    # Submit generic non-domain result (not fusion.cad/v1)
    generic_payload = {"custom_status": "ok", "arbitrary_field": 42}
    await container.desktop_nodes.submit_result("desk-1", cmd_id, generic_payload)

    # Query operation_result
    req_ctx = RequestContext(request_id="req_gen_result")
    params = types.CallToolRequestParams(
        name="fusion_operation_result",
        arguments={"node_id": "desk-1", "operation_id": op_id},
    )
    res = await op_result_tool.handler(None, params, req_ctx)
    assert isinstance(res, types.CallToolResult)
    assert not res.is_error
    parsed_res = json.loads(res.content[0].text)
    assert parsed_res["ok"] is True


def test_recovered_result_expiry_cleans_up_res_and_image_files(tmp_path):
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    settings = BridgeSettings.model_validate({
        "server": {"public_base_url": "https://127.0.0.1:8000"},
        "desktop_nodes": {
            "token": "test-token",
            "journal_path": str(tmp_path / "journal.jsonl"),
            "result_artifact_directory": str(artifact_dir),
            "result_artifact_ttl_seconds": 60,
        },
    })
    container = build_container(settings)

    payload_with_binary = {
        "api_version": "fusion.cad/v1",
        "status": "succeeded",
        "summary": "Screenshot artifact",
        "data": {
            "thumbnail_b64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        },
    }
    result_ref = container.desktop_nodes.store_external_result("desk-1", payload_with_binary)
    result_id = result_ref["external_result"]["result_id"]

    json_file = artifact_dir / f"{result_id}.json"
    res_files = list(artifact_dir.glob(f"{result_id}-res-*"))
    assert json_file.exists()
    assert len(res_files) >= 1

    # Also create a legacy -image- file to verify backwards-compatible cleanup
    legacy_image = artifact_dir / f"{result_id}-image-0.png"
    legacy_image.write_bytes(b"\x89PNG\r\n\x1a\n")

    # Clear in-memory state so recovery is triggered
    container.desktop_nodes._external_results.clear()
    container.desktop_nodes._external_resources.clear()

    # Set file mtime to 100 seconds in the past (exceeding 1s TTL)
    import os
    past_time = os.path.getmtime(json_file) - 100
    os.utime(json_file, (past_time, past_time))

    recovered = container.desktop_nodes._recover_external_result(result_id)
    assert recovered is None
    assert not json_file.exists()
    assert not legacy_image.exists()
    for res_path in res_files:
        assert not res_path.exists()


@pytest.mark.parametrize("error_payload", [
    {"isError": True, "error": {"code": "INVALID_ARGUMENT", "message": "Bad arg"}},
    {"status": "failed", "error": {"code": "DOCUMENT_NOT_OPEN", "message": "No doc"}},
    {"content": [{"type": "text", "text": "Traceback (most recent call last):\nRuntimeError: crashed"}], "isError": True},
    {"content": [{"type": "text", "text": json.dumps({"status": "failed", "error": {"code": "FUSION_API_ERROR", "message": "Internal CAD error"}})}]},
])
@pytest.mark.asyncio
async def test_fusion_call_fails_closed_on_native_errors(mock_container: ApplicationContainer, error_payload: dict):
    registry = build_tool_registry(mock_container)
    tool = registry.get("fusion_call")
    assert tool is not None

    mock_container.desktop_nodes.call = AsyncMock(return_value=error_payload)

    req_ctx = RequestContext(request_id="req_call_err")
    params = types.CallToolRequestParams(
        name="fusion_call",
        arguments={"node_id": "desk-1", "tool_name": "fusion_mcp_execute", "arguments": {"script": "# test"}},
    )
    result = await tool.handler(None, params, req_ctx)
    assert isinstance(result, types.CallToolResult)
    assert result.is_error is True
    parsed = json.loads(result.content[0].text)
    assert parsed["ok"] is False
    assert parsed["error"] is not None


@pytest.mark.parametrize("operation, payload", [
    ("begin", {"node_id": "desk-1", "operation": "begin"}),
    ("stage", {"node_id": "desk-1", "operation": "stage", "transaction_id": "tx_1234", "action": {"action_type": "show", "target": "ent_1"}}),
    ("abort", {"node_id": "desk-1", "operation": "abort", "transaction_id": "tx_1234"}),
])
@pytest.mark.asyncio
async def test_async_transaction_mutations_lifecycle_operation_result_and_uncertain_recovery(
    operation: str,
    payload: dict,
    tmp_path,
):
    settings = BridgeSettings.model_validate({
        "server": {"public_base_url": "https://127.0.0.1:8000"},
        "desktop_nodes": {
            "token": "test-token",
            "journal_path": str(tmp_path / "journal.jsonl"),
            "result_artifact_directory": str(tmp_path / "artifacts"),
            "call_timeout_seconds": 0.05,
        },
    })
    container = build_container(settings)
    setup_desk1_capabilities(container)
    registry = build_tool_registry(container)
    tool = registry.get("fusion_transaction")
    op_result_tool = registry.get("fusion_operation_result")
    assert tool is not None
    assert op_result_tool is not None

    await container.desktop_nodes.register(
        "desk-1",
        [{"name": "fusion_mcp_execute"}],
        fusion_available=True,
    )

    # stage/abort represent an already-begun transaction. The helper above
    # seeds the RevisionTracker baseline; seed the matching declarative record
    # too so terminal finalization has the same valid precondition as runtime.
    if operation in {"stage", "abort"}:
        container.fusion_cad.transaction_store.begin(
            "tx_1234",
            document_ref="doc_1",
            baseline_revision="rev_1",
            baseline_fingerprint="hash-desk1-seed",
            baseline_snapshot={
                "structural_hash": "hash-desk1-seed",
                "counts": {},
                "refs": [],
            },
        )

    # 1. Asynchronous dispatch via submit with mutation journal
    req_ctx = RequestContext(request_id=f"req_tx_{operation}")
    params = types.CallToolRequestParams(name="fusion_transaction", arguments=payload)
    res = await tool.handler(None, params, req_ctx)
    assert not res.is_error
    parsed_submit = json.loads(res.content[0].text)
    assert parsed_submit["ok"] is True
    op_id = parsed_submit["data"]["operation_id"]

    # Check journal has mutation=True and summary=transaction:<op>
    status_submitted = container.desktop_nodes.operation_status("desk-1", op_id)
    assert status_submitted["status"] == "queued"
    assert status_submitted["mutation"] is True
    assert status_submitted["summary"] == f"transaction:{operation}"

    # 2. Claiming transitions to running
    claimed = await container.desktop_nodes.claim("desk-1", wait_seconds=1.0)
    assert claimed is not None
    assert claimed["operation_id"] == op_id
    cmd_id = claimed["command_id"]

    status_claimed = container.desktop_nodes.operation_status("desk-1", op_id)
    assert status_claimed["status"] == "running"
    assert status_claimed["mutation"] is True

    # 3. Simulate bridge restart/crash during active claimed mutation -> recovered as uncertain (non-replayable)
    restarted = build_container(settings)
    restarted_status = restarted.desktop_nodes.operation_status("desk-1", op_id)
    assert restarted_status["status"] == "uncertain"
    assert restarted_status["mutation"] is True

    # 4. Successful result submission -> retained operation_result succeeds with decoded CadResult
    valid_cad_result = {
        "api_version": "fusion.cad/v1",
        "status": "succeeded",
        "summary": f"Transaction {operation} completed",
        "data": {
            "transaction_id": "tx_1234",
            "operation": operation,
            "applied": True,
            "fingerprint": "hash-desk1-seed" if operation == "abort" else "valid_real_fp_123",
            "document_ref": "doc_1",
        },
    }
    await container.desktop_nodes.submit_result("desk-1", cmd_id, {
        "content": [{"type": "text", "text": json.dumps(valid_cad_result)}],
        "isError": False,
    })

    # Query fusion_operation_result
    op_res_ctx = RequestContext(request_id=f"req_op_res_{operation}")
    op_res_params = types.CallToolRequestParams(
        name="fusion_operation_result",
        arguments={"node_id": "desk-1", "operation_id": op_id},
    )
    result_res = await op_result_tool.handler(None, op_res_params, op_res_ctx)
    assert not result_res.is_error
    parsed_op_result = json.loads(result_res.content[0].text)
    assert parsed_op_result["ok"] is True
    assert "external_result" in parsed_op_result["data"]


@pytest.mark.asyncio
async def test_sync_read_timeout_preserves_retryable_and_timed_out_status(tmp_path):
    container = build_container(BridgeSettings.model_validate({
        "server": {"public_base_url": "https://127.0.0.1:8000"},
        "desktop_nodes": {
            "token": "test-token",
            "journal_path": str(tmp_path / "journal.jsonl"),
            "call_timeout_seconds": 0.05,
        },
    }))
    registry = build_tool_registry(container)
    tool = registry.get("fusion_read")
    assert tool is not None

    await container.desktop_nodes.register(
        "desk-1",
        [{"name": "fusion_mcp_execute"}],
        fusion_available=True,
    )
    from app.fusion_cad.capabilities import CapabilityMatrix
    from app.fusion_cad.models import CapabilityRecord
    container.fusion_cad.set_node_capabilities(
        "desk-1",
        CapabilityMatrix.from_records([
            CapabilityRecord(name="entity.token_resolver", state="supported"),
        ]),
    )

    req_ctx = RequestContext(request_id="req_read_timeout")
    params = types.CallToolRequestParams(
        name="fusion_read",
        arguments={"node_id": "desk-1", "operation": "entity", "ref": "ent_1234"},
    )

    call_task = asyncio.create_task(tool.handler(None, params, req_ctx))

    claimed = await container.desktop_nodes.claim("desk-1", wait_seconds=1.0)
    assert claimed is not None
    op_id = claimed["operation_id"]

    with pytest.raises(BridgeError) as exc_info:
        await call_task
    assert exc_info.value.code == ErrorCode.DESKTOP_NODE_TIMEOUT
    assert exc_info.value.retryable is True

    status_data = container.desktop_nodes.operation_status("desk-1", op_id)
    assert status_data["status"] == "timed_out"
    assert status_data["mutation"] is False


def test_bridge_restart_recovers_claimed_mutations_as_uncertain(tmp_path):
    journal_file = str(tmp_path / "journal.jsonl")
    settings = BridgeSettings.model_validate({
        "server": {"public_base_url": "https://127.0.0.1:8000"},
        "desktop_nodes": {
            "token": "test-token",
            "journal_path": journal_file,
        },
    })
    c1 = build_container(settings)
    # Manually write an incomplete claimed mutating operation into journal
    c1.desktop_nodes._journal.create({
        "operation_id": "op_tx_stage_1",
        "command_id": "cmd_tx_1",
        "node_id": "desk-1",
        "tool_name": "fusion_mcp_execute",
        "arguments_sha256": "abc",
        "status": "claimed",
        "mutation": True,
        "summary": "transaction:stage",
        "created_at": 1000.0,
        "claimed_at": 1001.0,
        "completed_at": None,
        "result_sha256": None,
    })
    c1.desktop_nodes._journal.create({
        "operation_id": "op_read_ent_1",
        "command_id": "cmd_read_1",
        "node_id": "desk-1",
        "tool_name": "fusion_mcp_execute",
        "arguments_sha256": "def",
        "status": "claimed",
        "mutation": False,
        "summary": "read:entity",
        "created_at": 1000.0,
        "claimed_at": 1001.0,
        "completed_at": None,
        "result_sha256": None,
    })

    # Restart bridge
    c2 = build_container(settings)
    st_mut = c2.desktop_nodes.operation_status("desk-1", "op_tx_stage_1")
    assert st_mut["status"] == "uncertain"
    assert st_mut["mutation"] is True

    st_read = c2.desktop_nodes.operation_status("desk-1", "op_read_ent_1")
    assert st_read["status"] == "interrupted"
    assert st_read["mutation"] is False


@pytest.mark.asyncio
async def test_externalization_storage_failure_fails_closed(mock_container: ApplicationContainer):
    registry = build_tool_registry(mock_container)
    tool = registry.get("fusion_read")
    assert tool is not None

    mock_container.desktop_nodes.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Read with binary",
                "data": {"raw_blob": "data:application/octet-stream;base64,AQIDBAU="},
            }),
        }],
        "isError": False,
    })
    # Simulate disk / storage failure during store_external_result
    mock_container.desktop_nodes.store_external_result = MagicMock(side_effect=OSError("Disk full"))

    req_ctx = RequestContext(request_id="req_ext_fail")
    params = types.CallToolRequestParams(
        name="fusion_read",
        arguments={"node_id": "desk-1", "operation": "entity", "ref": "ent_1234"},
    )
    with pytest.raises(BridgeError) as exc_info:
        await tool.handler(None, params, req_ctx)
    assert exc_info.value.code == ErrorCode.INTERNAL_ERROR
    assert "Failed to externalize binary result payload" in exc_info.value.message


@pytest.mark.asyncio
async def test_execute_rejects_arbitrary_dict_with_extra_fields(mock_container: ApplicationContainer):
    service: FusionCadService = mock_container.fusion_cad

    # 1. Dict with extra forbidden field
    with pytest.raises(BridgeError) as exc_info:
        await service.execute({
            "node_id": "desk-1",
            "operation": "camera_read",
            "evil_extra_field": "injected",
        })
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT
    assert "validation_errors" in exc_info.value.details

    # 2. Dict with invalid operation for specified group
    with pytest.raises(BridgeError) as exc_info:
        await service.execute({
            "node_id": "desk-1",
            "operation": "text_create",
        }, group="read")
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT

    # 3. Dict with missing required fields
    with pytest.raises(BridgeError) as exc_info:
        await service.execute({
            "node_id": "desk-1",
            "operation": "entity",
            # missing required 'ref'
        }, group="read")
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT

    # 4. Arbitrary non-CAD BaseModel
    from pydantic import BaseModel as _BM

    class ArbitraryModel(_BM):
        node_id: str
        operation: str
        custom_data: str

    with pytest.raises(BridgeError) as exc_info:
        await service.execute(ArbitraryModel(node_id="desk-1", operation="camera_read", custom_data="bad"))
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_execute_accepts_valid_dict_and_dispatches_cleanly(mock_container: ApplicationContainer):
    service: FusionCadService = mock_container.fusion_cad

    mock_container.desktop_nodes.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Read entity ok",
                "data": {"entity": "ent_1234"},
            }),
        }],
        "isError": False,
    })

    result = await service.execute({
        "node_id": "desk-1",
        "operation": "entity",
        "ref": "ent_1234",
    })
    assert result.status == "succeeded"
    assert result.summary == "Read entity ok"


@pytest.mark.parametrize("bad_is_error", ["true", 1, {}, {"nested": "value"}, "false", 0, None, [True]])
def test_decode_domain_result_fails_closed_on_non_bool_is_error_direct(bad_is_error):
    # Direct domain dict with malformed isError
    raw = {
        "api_version": "fusion.cad/v1",
        "status": "succeeded",
        "summary": "Should fail",
        "data": {"key": "val"},
        "isError": bad_is_error,
    }
    with pytest.raises(FusionCadError) as exc_info:
        FusionCadService.decode_domain_result(raw)
    assert exc_info.value.code == ErrorCode.FUSION_API_ERROR


@pytest.mark.parametrize("bad_is_error", ["true", 1, {}, {"nested": "value"}, "false", 0, None, [True]])
def test_decode_domain_result_fails_closed_on_non_bool_is_error_wrapped_content(bad_is_error):
    # Content block with inner JSON containing malformed isError
    inner = {
        "api_version": "fusion.cad/v1",
        "status": "succeeded",
        "summary": "Should fail",
        "data": {"key": "val"},
        "isError": bad_is_error,
    }
    raw = {
        "content": [{"type": "text", "text": json.dumps(inner)}],
        "isError": False,
    }
    with pytest.raises(FusionCadError) as exc_info:
        FusionCadService.decode_domain_result(raw)
    assert exc_info.value.code == ErrorCode.FUSION_API_ERROR

    # Content block with top-level malformed isError
    raw_top_bad = {
        "content": [{"type": "text", "text": json.dumps({"api_version": "fusion.cad/v1", "summary": "ok", "status": "succeeded", "data": {}})}],
        "isError": bad_is_error,
    }
    with pytest.raises(FusionCadError) as exc_info_top:
        FusionCadService.decode_domain_result(raw_top_bad)
    assert exc_info_top.value.code == ErrorCode.FUSION_API_ERROR


def test_decode_domain_result_is_error_control_cases():
    # isError=True fails
    with pytest.raises(FusionCadError):
        FusionCadService.decode_domain_result({
            "api_version": "fusion.cad/v1",
            "status": "succeeded",
            "summary": "Error control",
            "data": {},
            "isError": True,
        })

    # isError=False succeeds for direct dict
    res_direct = FusionCadService.decode_domain_result({
        "api_version": "fusion.cad/v1",
        "status": "succeeded",
        "summary": "Success control",
        "data": {"foo": "bar"},
        "isError": False,
    })
    assert res_direct.summary == "Success control"
    assert res_direct.status == "succeeded"

    # isError=False succeeds for wrapped content
    res_wrapped = FusionCadService.decode_domain_result({
        "content": [{
            "type": "text",
            "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Success wrapped control",
                "data": {"foo": "bar"},
                "isError": False,
            }),
        }],
        "isError": False,
    })
    assert res_wrapped.summary == "Success wrapped control"
    assert res_wrapped.status == "succeeded"


@pytest.mark.parametrize("is_error_val, should_succeed", [
    ("true", False),
    (1, False),
    ({}, False),
    ({"error": "detail"}, False),
    (True, False),
    (False, True),
])
@pytest.mark.asyncio
async def test_service_execute_direct_sync_is_error_matrix(
    mock_container: ApplicationContainer,
    is_error_val,
    should_succeed: bool,
):
    service: FusionCadService = mock_container.fusion_cad
    mock_container.desktop_nodes.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Sync matrix test",
                "data": {"result": 42},
                "isError": is_error_val,
            }),
        }],
        "isError": is_error_val if isinstance(is_error_val, bool) else False,
    })

    req = {"node_id": "desk-1", "operation": "entity", "ref": "ent_1234"}
    if should_succeed:
        res = await service.execute(req)
        assert res.summary == "Sync matrix test"
    else:
        with pytest.raises((FusionCadError, BridgeError)):
            await service.execute(req)


@pytest.mark.parametrize("is_error_val, should_succeed", [
    ("true", False),
    (1, False),
    ({}, False),
    (True, False),
    (False, True),
])
@pytest.mark.asyncio
async def test_retained_async_domain_operation_result_is_error_matrix(
    tmp_path,
    is_error_val,
    should_succeed: bool,
):
    container = build_container(BridgeSettings.model_validate({
        "server": {"public_base_url": "https://127.0.0.1:8000"},
        "desktop_nodes": {
            "token": "test-token",
            "journal_path": str(tmp_path / "journal.jsonl"),
            "result_artifact_directory": str(tmp_path / "artifacts"),
        },
    }))
    setup_desk1_capabilities(container)
    registry = build_tool_registry(container)
    op_result_tool = registry.get("fusion_operation_result")
    assert op_result_tool is not None

    await container.desktop_nodes.register(
        "desk-1",
        [{"name": "fusion_mcp_execute"}],
        fusion_available=True,
    )

    submit_res = await container.fusion_cad.execute({
        "node_id": "desk-1",
        "operation": "run",
    }, group="validate")
    op_id = submit_res["operation_id"]

    claimed = await container.desktop_nodes.claim("desk-1", wait_seconds=1.0)
    cmd_id = claimed["command_id"]

    payload = {
        "api_version": "fusion.cad/v1",
        "status": "succeeded",
        "summary": "Async matrix test",
        "data": {"checked": True},
        "isError": is_error_val,
    }
    node_result = {
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "isError": is_error_val,
    }
    await container.desktop_nodes.submit_result("desk-1", cmd_id, node_result)

    req_ctx = RequestContext(request_id="req_async_matrix")
    params = types.CallToolRequestParams(
        name="fusion_operation_result",
        arguments={"node_id": "desk-1", "operation_id": op_id},
    )

    if should_succeed:
        res = await op_result_tool.handler(None, params, req_ctx)
        assert isinstance(res, types.CallToolResult)
        assert not res.is_error
        parsed = json.loads(res.content[0].text)
        assert parsed["ok"] is True
    else:
        with pytest.raises((FusionCadError, BridgeError)):
            await op_result_tool.handler(None, params, req_ctx)


# =========================================================================
# Task 8: Camera, screenshot, immutable ViewRef
# =========================================================================


def _view_camera_payload(**overrides):
    payload = {
        "camera": {
            "eye": [10.0, 20.0, 30.0],
            "target": [0.0, 0.0, 0.0],
            "up": [0.0, 0.0, 1.0],
            "projection": "perspective",
            "fov_deg": 45.0,
        },
        "viewport": {"width": 1920, "height": 1080},
        "visibility": [
            {
                "kind": "occurrence",
                "full_path_name": "Root:Left",
                "is_visible": True,
                "effective_visibility": True,
            }
        ],
        "section": {"active": False, "type": None},
    }
    payload.update(overrides)
    return payload


def _screenshot_desktop_result(width=1920, height=1080, **overrides):
    data = dict(_view_camera_payload())
    data.update(overrides)
    data.update(
        {
            "operation": "screenshot",
            "width": width,
            "height": height,
            "screenshot_b64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        }
    )
    return {
        "api_version": "fusion.cad/v1",
        "status": "succeeded",
        "summary": "Screenshot captured",
        "data": data,
    }


def _camera_desktop_result(op, camera_overrides=None):
    camera = dict(_view_camera_payload())
    if camera_overrides:
        camera["camera"] = {**camera["camera"], **camera_overrides}
    camera["operation"] = op
    return {
        "api_version": "fusion.cad/v1",
        "status": "succeeded",
        "summary": "Camera context captured",
        "data": camera,
    }


def _build_view_container(tmp_path) -> ApplicationContainer:
    """New-container helper registering desk-1 so capability caches resolve."""
    container = build_container(BridgeSettings.model_validate({
        "server": {"public_base_url": "https://127.0.0.1:8000"},
        "desktop_nodes": {
            "token": "test-token",
            "journal_path": str(tmp_path / "journal.jsonl"),
            "result_artifact_directory": str(tmp_path / "artifacts"),
        },
    }))
    setup_desk1_capabilities(container)
    container.desktop_nodes._nodes["desk-1"] = NodeState(
        node_id="desk-1",
        last_seen=time.monotonic(),
        last_seen_wall=time.time(),
        tools=[{"name": "fusion_mcp_execute"}],
        fusion_available=True,
        session_generation=1,
    )
    return container


def _extract_script_payload(script: str) -> dict:
    """Decode the JSON-injected PAYLOAD_RAW literal from a rendered script."""
    import re

    match = re.search(r'^PAYLOAD_RAW = (".*")$', script, re.MULTILINE)
    assert match is not None, "PAYLOAD_RAW literal not found in rendered script"
    return json.loads(json.loads(match.group(1)))


@pytest.mark.asyncio
async def test_view_screenshot_binds_immutable_viewref_and_externalizes_image(tmp_path):
    container = _build_view_container(tmp_path)

    container.desktop_nodes.submit = AsyncMock(return_value={
        "content": [{"type": "text", "text": json.dumps(_screenshot_desktop_result())}],
        "isError": False,
    })

    result = await container.fusion_cad.execute({"node_id": "desk-1", "operation": "screenshot"})
    assert isinstance(result, dict)
    assert "external_result" in result
    ref = result["external_result"]

    full, metadata = container.desktop_nodes.external_result(ref)
    data = full["data"]
    # Immutable ViewRef public metadata shape
    assert data["view_ref"].startswith("view_")
    assert data["model_revision"] == "rev_1"
    assert data["camera_revision"].startswith("cam_")
    assert data["visibility_revision"].startswith("vis_")
    assert data["width"] == 1920
    assert data["height"] == 1080
    # The ViewRef image is bound to the real emitted image ResourceLink URI from
    # DesktopNodeService.external_result metadata.resources[*].uri; the fabricated
    # resource://views/... placeholder may never escape.
    image_resources = [
        r for r in metadata["resources"] if str(r.get("mime_type", "")).startswith("image/")
    ]
    assert image_resources, "expected an emitted image resource"
    emitted_uri = image_resources[0]["uri"]
    assert data["image"] == emitted_uri
    assert not data["image"].startswith("resource://")
    # No inline base64 screenshot payload in the public view metadata or the
    # full exported/model-visible JSON.
    assert "iVBORw0KGgo" not in json.dumps(data)
    assert "iVBORw0KGgo" not in json.dumps(full)

    # Bound record exists in the immutable store and carries the real URI
    record = container.fusion_cad.view_store.get(data["view_ref"])
    assert record is not None
    assert record.model_revision == "rev_1"
    assert record.image == emitted_uri
    from app.fusion_cad.models import ViewRefSummary

    restored_summary = ViewRefSummary.model_validate(record.to_summary().model_dump())
    assert restored_summary.view_ref == data["view_ref"]
    assert restored_summary.image == emitted_uri

    # Image resource link rendered through the proven artifact path
    assert any(r.get("mime_type", "").startswith("image/") for r in metadata["resources"])


@pytest.mark.asyncio
async def test_view_camera_change_invalidates_old_viewref_but_not_model_revision(tmp_path):
    container = _build_view_container(tmp_path)

    # 1. Screenshot binds view_1
    container.desktop_nodes.submit = AsyncMock(return_value={
        "content": [{"type": "text", "text": json.dumps(_screenshot_desktop_result())}],
        "isError": False,
    })
    shot = await container.fusion_cad.execute({"node_id": "desk-1", "operation": "screenshot"})
    ref = shot["external_result"]
    full, _ = container.desktop_nodes.external_result(ref)
    view_ref = full["data"]["view_ref"]
    assert container.fusion_cad.view_store.get(view_ref) is not None

    # Fresh immediately after screenshot
    container.fusion_cad.assert_view_fresh(view_ref, "desk-1", "doc_1")

    # 2. Camera mutation with a changed camera context (eye changed)
    container.desktop_nodes.submit = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps(_camera_desktop_result("camera_set", camera_overrides={"eye": [11.0, 20.0, 30.0]})),
        }],
        "isError": False,
    })
    cam_res = await container.fusion_cad.execute(
        {
            "node_id": "desk-1",
            "operation": "camera_set",
            "eye": {"x": 11.0, "y": 20.0, "z": 30.0, "frame": {"space": "world"}},
        }
    )
    # Camera mutation finalizes to view-state only (CadResult, no external artifact)
    assert not (isinstance(cam_res, dict) and "external_result" in cam_res)

    # Camera mutation never advances model revision
    assert container.fusion_cad.revision_tracker.current("doc_1").revision == "rev_1"

    # Old view_ref is now stale (camera revision changed)
    with pytest.raises(FusionCadError) as exc:
        container.fusion_cad.assert_view_fresh(view_ref, "desk-1", "doc_1")
    assert exc.value.code == ErrorCode.VIEW_STALE


@pytest.mark.asyncio
async def test_fusion_view_screenshot_tool_returns_resource_link_without_inline_base64(tmp_path):
    container = _build_view_container(tmp_path)
    registry = build_tool_registry(container)
    tool = registry.get("fusion_view")
    assert tool is not None

    container.desktop_nodes.submit = AsyncMock(return_value={
        "content": [{"type": "text", "text": json.dumps(_screenshot_desktop_result())}],
        "isError": False,
    })

    req_ctx = RequestContext(request_id="req_view_shot")
    params = types.CallToolRequestParams(
        name="fusion_view",
        arguments={"node_id": "desk-1", "operation": "screenshot"},
    )
    result = await tool.handler(None, params, req_ctx)
    assert isinstance(result, types.CallToolResult)
    assert not result.is_error

    text_blocks = [b for b in result.content if isinstance(b, types.TextContent)]
    assert len(text_blocks) == 1
    parsed = json.loads(text_blocks[0].text)
    assert parsed["ok"] is True
    assert "iVBORw0KGgo" not in text_blocks[0].text
    assert "screenshot_b64" not in text_blocks[0].text

    resource_links = [b for b in result.content if isinstance(b, types.ResourceLink)]
    assert len(resource_links) >= 1
    assert any(
        getattr(link, "mime_type", None) or getattr(link, "mimeType", "").startswith("image/png")
        or str(getattr(link, "description", "")) == "Fusion image artifact"
        for link in resource_links
    )


@pytest.mark.asyncio
async def test_view_operation_missing_camera_context_fails_closed(mock_container: ApplicationContainer):
    # A view result without deterministic camera context must fail closed
    mock_container.desktop_nodes.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Camera read without context",
                "data": {"result_key": "no camera"},
            }),
        }],
        "isError": False,
    })
    with pytest.raises(FusionCadError) as exc:
        await mock_container.fusion_cad.execute(
            {"node_id": "desk-1", "operation": "camera_read"}
        )
    assert exc.value.code == ErrorCode.PRECONDITION_FAILED


@pytest.mark.asyncio
async def test_view_zoom_entity_injects_exact_resolution_hint(tmp_path):
    container = _build_view_container(tmp_path)
    container.fusion_cad.ref_registry.issue(
        document_ref="doc_1",
        kind="body",
        name="Bracket",
        native_token="native_body_1",
        opaque_ref="ent_zoom_1",
    )

    captured_script = {}

    async def capture_submit(node_id, tool_name, arguments, journal=None):
        captured_script["script"] = arguments["object"]["script"]
        return _camera_desktop_result("zoom_entity")

    container.desktop_nodes.submit = capture_submit  # type: ignore[assignment]

    await container.fusion_cad.execute(
        {"node_id": "desk-1", "operation": "zoom_entity", "target": "ent_zoom_1"}
    )
    payload = _extract_script_payload(captured_script.get("script", ""))
    # Exact Task5/Task7 hint (native token) injected into the static script payload:
    # no name-only/raw Python escape hatch.
    assert payload["target"]["native_token"] == "native_body_1"
    assert payload["target"]["ref"] == "ent_zoom_1"
    assert payload["target"]["name"] == "Bracket"


@pytest.mark.asyncio
async def test_view_zoom_entity_unknown_ref_fails_closed(tmp_path):
    container = _build_view_container(tmp_path)
    container.desktop_nodes.submit = AsyncMock()

    with pytest.raises(FusionCadError) as exc:
        await container.fusion_cad.execute(
            {"node_id": "desk-1", "operation": "zoom_entity", "target": "ent_unknown"}
        )
    assert exc.value.code in (ErrorCode.REF_STALE, ErrorCode.REF_AMBIGUOUS)
    # Failed closed before dispatch: no raw Python/native token escape hatch
    assert container.desktop_nodes.submit.call_count == 0
    assert fake_submit_not_dispatched(container) is True


def fake_submit_not_dispatched(container):
    return container.desktop_nodes.submit.call_count == 0



@pytest.mark.asyncio
async def test_view_screenshot_tool_image_uri_matches_emitted_resource_link(tmp_path):
    """Finding 1+2 tool-level regression: the public screenshot ViewRef image URI
    must equal the actual emitted image ResourceLink URI (from
    DesktopNodeService.external_result metadata.resources[*].uri), the returned
    metadata must use the requested non-default output dimensions, and neither
    the tool text nor the full exported/model-visible JSON may contain the
    screenshot base64/png bytes.
    """
    container = _build_view_container(tmp_path)
    registry = build_tool_registry(container)
    tool = registry.get("fusion_view")
    assert tool is not None

    container.desktop_nodes.submit = AsyncMock(return_value={
        "content": [{"type": "text", "text": json.dumps(_screenshot_desktop_result(width=640, height=480))}],
        "isError": False,
    })

    req_ctx = RequestContext(request_id="req_view_uri")
    params = types.CallToolRequestParams(
        name="fusion_view",
        arguments={"node_id": "desk-1", "operation": "screenshot", "width": 640, "height": 480},
    )
    result = await tool.handler(None, params, req_ctx)
    assert isinstance(result, types.CallToolResult)
    assert not result.is_error

    text_blocks = [b for b in result.content if isinstance(b, types.TextContent)]
    assert len(text_blocks) == 1
    parsed = json.loads(text_blocks[0].text)
    assert parsed["ok"] is True
    # No base64 screenshot bytes in the tool text block.
    assert "iVBORw0KGgo" not in text_blocks[0].text
    assert "screenshot_b64" not in text_blocks[0].text

    resource_links = [
        b
        for b in result.content
        if isinstance(b, types.ResourceLink)
        and (
            str(getattr(b, "description", "")) == "Fusion image artifact"
            or str(getattr(b, "uri", "")).startswith("http")
        )
    ]
    # There is an image ResourceLink plus the full-result export link.
    image_links = [
        b
        for b in resource_links
        if str(getattr(b, "description", "")) == "Fusion image artifact"
        or str(getattr(b, "mime_type", None) or getattr(b, "mimeType", "") or "").startswith("image/png")
    ]
    assert image_links, "expected an image ResourceLink in the tool response"

    # The tool text exposes the external-result metadata (resources + export_url).
    metadata = parsed["data"]["external_result"]
    image_resources = [
        r for r in metadata["resources"] if str(r.get("mime_type", "")).startswith("image/")
    ]
    assert image_resources, "expected an emitted image resource in metadata"
    emitted_uri = image_resources[0]["uri"]

    # The ResourceLink URI exposed by the proven app/tools/fusion.py path equals
    # the emitted image URI.
    assert any(str(getattr(link, "uri", "")) == emitted_uri for link in image_links)

    # Resolve the exported/model-visible JSON through the export_url token (the
    # same file external_result would serve) and verify the ViewRef image equals
    # the emitted URI and no base64/png signal exists anywhere.
    export_url = metadata["export_url"]
    assert isinstance(export_url, str) and "/" in export_url
    token = export_url.rsplit("/", 1)[-1]
    export_path, _ = container.desktop_nodes.resolve_external_export(token)
    full = json.loads(export_path.read_text())
    assert full["data"]["image"] == emitted_uri
    assert not full["data"]["image"].startswith("resource://")
    full_json = json.dumps(full)
    assert "iVBORw0KGgo" not in full_json
    assert "screenshot_b64" not in full_json

    # Requested non-default output dimensions are bound and reported.
    assert full["data"]["width"] == 640
    assert full["data"]["height"] == 480
    record = container.fusion_cad.view_store.get(full["data"]["view_ref"])
    assert record is not None
    assert record.image == emitted_uri
    assert record.viewport_width == 640
    assert record.viewport_height == 480
    summary = record.to_summary()
    assert summary.image == emitted_uri
    assert summary.width == 640
    assert summary.height == 480
    # Freshness against the current context still holds after image promotion.
    container.fusion_cad.assert_view_fresh(record.view_ref, "desk-1", "doc_1")


# =========================================================================
# Task 9: screen-space pick service contract
# =========================================================================

@pytest.mark.asyncio
async def test_view_pick_fresh_view_injects_immutable_authority_and_normalizes_hits(tmp_path):
    container = _build_view_container(tmp_path)
    container.desktop_nodes.submit = AsyncMock(return_value={
        "content": [{"type": "text", "text": json.dumps(_screenshot_desktop_result())}],
        "isError": False,
    })
    shot = await container.fusion_cad.execute({"node_id": "desk-1", "operation": "screenshot"})
    full, _ = container.desktop_nodes.external_result(shot["external_result"])
    view_ref = full["data"]["view_ref"]

    captured = {}
    async def pick_call(node_id, tool_name, arguments, journal=None):
        captured["script"] = arguments["object"]["script"]
        return {
            "api_version": "fusion.cad/v1",
            "status": "succeeded",
            "summary": "pick",
            "data": {
                "hit": True,
                "candidate_count": 2,
                "candidates": [
                    {"kind":"face","name":"FaceA","native_token":"native_face_a","depth":0,"world_point":{"x":1.0,"y":2.0,"z":3.0,"frame":{"space":"world","ref":None}},"distance":10.0},
                    {"kind":"face","name":"FaceB","native_token":"native_face_b","depth":1,"world_point":{"x":4.0,"y":5.0,"z":6.0,"frame":{"space":"world","ref":None}},"distance":20.0},
                ],
            },
        }
    container.desktop_nodes.call = pick_call  # type: ignore[assignment]

    result = await container.fusion_cad.execute({"node_id":"desk-1","operation":"pick","view_ref":view_ref,"x":0.5,"y":0.5,"filters":["face"]})
    data = result["data"] if isinstance(result, dict) else dict(result.data)
    assert data["hit"] is True
    assert data["candidate_count"] == 2
    assert [c["depth"] for c in data["candidates"]] == [0, 1]
    assert all(str(c["ref"]).startswith("ent_") for c in data["candidates"])
    assert "native_face_a" not in repr(data)
    assert "native_face_b" not in repr(data)
    payload = _extract_script_payload(captured["script"])
    expected = payload["_pick_expected"]
    assert expected["document_ref"] == "doc_1"
    assert expected["model_fingerprint"] == "hash-desk1-seed"
    assert expected["image_width"] == 1920
    assert expected["image_height"] == 1080
    assert expected["camera"]["viewport_width"] == 1920
    assert expected["camera"]["viewport_height"] == 1080


@pytest.mark.asyncio
async def test_view_pick_known_stale_view_blocks_before_raycast_dispatch(tmp_path):
    container = _build_view_container(tmp_path)
    container.desktop_nodes.submit = AsyncMock(return_value={
        "content": [{"type": "text", "text": json.dumps(_screenshot_desktop_result())}],
        "isError": False,
    })
    shot = await container.fusion_cad.execute({"node_id": "desk-1", "operation": "screenshot"})
    full, _ = container.desktop_nodes.external_result(shot["external_result"])
    view_ref = full["data"]["view_ref"]
    container.fusion_cad.revision_tracker.observe("doc_1", "hash-after-shot")
    container.desktop_nodes.call = AsyncMock()
    with pytest.raises(FusionCadError) as exc:
        await container.fusion_cad.execute({"node_id":"desk-1","operation":"pick","view_ref":view_ref,"x":0.5,"y":0.5})
    assert exc.value.code == ErrorCode.VIEW_STALE
    assert container.desktop_nodes.call.call_count == 0


@pytest.mark.asyncio
async def test_async_domain_operation_result_persists_public_finalized_artifact(tmp_path):
    container = build_container(BridgeSettings.model_validate({
        "server": {"public_base_url": "https://127.0.0.1:8000"},
        "desktop_nodes": {
            "token": "test-token",
            "journal_path": str(tmp_path / "journal.jsonl"),
            "result_artifact_directory": str(tmp_path / "artifacts"),
        },
    }))
    setup_desk1_capabilities(container)
    registry = build_tool_registry(container)
    op_result_tool = registry.get("fusion_operation_result")
    assert op_result_tool is not None
    await container.desktop_nodes.register(
        "desk-1", [{"name": "fusion_mcp_execute"}], fusion_available=True
    )

    submit_res = await container.fusion_cad.execute(
        {"node_id": "desk-1", "operation": "run"}, group="validate"
    )
    op_id = submit_res["operation_id"]
    claimed = await container.desktop_nodes.claim("desk-1", wait_seconds=1.0)
    assert claimed is not None
    native = "native::feature::must-not-leak"
    raw_cad_result = {
        "api_version": "fusion.cad/v1",
        "status": "succeeded",
        "summary": "Validation evidence collected",
        "data": {
            "document_ref": "doc_1",
            "features": [{
                "kind": "feature",
                "name": "Feature1",
                "native_token": native,
                "valid": True,
                "health": "ok",
            }],
            "timeline": {"available": True, "rolled_back": False},
        },
    }
    await container.desktop_nodes.submit_result(
        "desk-1",
        claimed["command_id"],
        {"content": [{"type": "text", "text": json.dumps(raw_cad_result)}], "isError": False},
    )

    params = types.CallToolRequestParams(
        name="fusion_operation_result",
        arguments={"node_id": "desk-1", "operation_id": op_id},
    )
    res = await op_result_tool.handler(None, params, RequestContext(request_id="req_public_artifact"))
    assert not res.is_error
    retained, _ = container.desktop_nodes.operation_result("desk-1", op_id)
    assert native not in json.dumps(retained, sort_keys=True)
    assert retained.get("api_version") == "fusion.cad/v1"
    assert retained.get("validation") is not None
    assert container.desktop_nodes.operation_status("desk-1", op_id).get("domain_finalization") == "finalized"


@pytest.mark.asyncio
async def test_async_transaction_begin_operation_result_is_idempotent(tmp_path):
    container = build_container(BridgeSettings.model_validate({
        "server": {"public_base_url": "https://127.0.0.1:8000"},
        "desktop_nodes": {
            "token": "test-token",
            "journal_path": str(tmp_path / "journal.jsonl"),
            "result_artifact_directory": str(tmp_path / "artifacts"),
        },
    }))
    setup_desk1_capabilities(container)
    registry = build_tool_registry(container)
    tx_tool = registry.get("fusion_transaction")
    op_result_tool = registry.get("fusion_operation_result")
    assert tx_tool is not None and op_result_tool is not None
    await container.desktop_nodes.register(
        "desk-1", [{"name": "fusion_mcp_execute"}], fusion_available=True
    )

    tx_id = "tx_idem_begin_1"
    submit = await tx_tool.handler(
        None,
        types.CallToolRequestParams(
            name="fusion_transaction",
            arguments={
                "node_id": "desk-1",
                "operation": "begin",
                "transaction_id": tx_id,
                "document_ref": "doc_1",
            },
        ),
        RequestContext(request_id="req_begin_submit"),
    )
    op_id = json.loads(submit.content[0].text)["data"]["operation_id"]
    claimed = await container.desktop_nodes.claim("desk-1", wait_seconds=1.0)
    assert claimed is not None
    raw = {
        "api_version": "fusion.cad/v1",
        "status": "succeeded",
        "summary": "Transaction begin completed",
        "document": {"document_ref": "doc_1", "model_revision": "rev_1"},
        "data": {
            "operation": "begin",
            "applied": True,
            "transaction_id": tx_id,
            "document_ref": "doc_1",
            "fingerprint": "fp_idempotent_begin",
        },
    }
    await container.desktop_nodes.submit_result(
        "desk-1",
        claimed["command_id"],
        {"content": [{"type": "text", "text": json.dumps(raw)}], "isError": False},
    )
    params = types.CallToolRequestParams(
        name="fusion_operation_result",
        arguments={"node_id": "desk-1", "operation_id": op_id},
    )
    first = await op_result_tool.handler(None, params, RequestContext(request_id="req_begin_first"))
    second = await op_result_tool.handler(None, params, RequestContext(request_id="req_begin_second"))
    assert not first.is_error and not second.is_error
    first_payload = json.loads(first.content[0].text)
    second_payload = json.loads(second.content[0].text)
    assert first_payload["data"]["external_result"]["sha256"] == second_payload["data"]["external_result"]["sha256"]
    baseline = container.fusion_cad.revision_tracker.get_transaction_baseline(tx_id)
    assert baseline is not None
    assert baseline["baseline_fingerprint"] == "fp_idempotent_begin"
    assert container.desktop_nodes.operation_status("desk-1", op_id).get("domain_finalization") == "finalized"
