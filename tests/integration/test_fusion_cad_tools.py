from __future__ import annotations

import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp import types

from app.api.context import RequestContext
from app.api.errors import BridgeError, ErrorCode
from app.container import ApplicationContainer, build_container
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.service import FusionCadService
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry


@pytest.fixture
def mock_container() -> ApplicationContainer:
    return build_container(BridgeSettings.model_validate({
        "server": {"public_base_url": "https://127.0.0.1:8000"},
        "desktop_nodes": {"token": "test-desktop-token", "journal_path": ":memory:"}
    }))


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

    mock_container.desktop_nodes.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": f"Executed {valid_payload['operation']} successfully",
                "data": {"result_key": "РАСПИСАНИЕ ПЫТОК 😈"},
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
    assert parsed["data"]["data"]["result_key"] == "РАСПИСАНИЕ ПЫТОК 😈"

    assert mock_container.desktop_nodes.call.called
    call_args = mock_container.desktop_nodes.call.call_args
    journal = call_args[0][3] if len(call_args[0]) > 3 else call_args[1].get("journal")
    assert isinstance(journal, dict)
    assert journal.get("mutation") is False


@pytest.mark.parametrize("tool_name, valid_payload, expected_mutation", [
    ("fusion_metadata", {"node_id": "desk-1", "operation": "tag", "target": "ent_body_1", "tag_name": "bolt"}, True),
    ("fusion_style", {"node_id": "desk-1", "operation": "show", "target": "ent_body_1"}, True),
    ("fusion_style", {"node_id": "desk-1", "operation": "text_create", "text": "Label", "height_mm": 5.0, "position": {"x": 0, "y": 0, "z": 0, "frame": {"space": "world"}}}, True),
    ("fusion_validate", {"node_id": "desk-1", "operation": "run"}, False),
    ("fusion_view", {"node_id": "desk-1", "operation": "screenshot"}, False),
    ("fusion_transaction", {"node_id": "desk-1", "operation": "preview", "transaction_id": "tx_1234"}, False),
    ("fusion_transaction", {"node_id": "desk-1", "operation": "commit", "transaction_id": "tx_1234"}, True),
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
    ("view", "camera_set", {"operation": "camera_set", "fov": 45.0}, False, True),
    ("view", "fit", {"operation": "fit"}, False, True),
    ("view", "zoom_entity", {"operation": "zoom_entity", "target": "ent_1"}, False, True),
    ("view", "orient_to_face", {"operation": "orient_to_face", "target": "ent_1"}, False, True),
    ("view", "standard_view", {"operation": "standard_view", "view_type": "top"}, False, True),
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
    ("transaction", "begin", {"operation": "begin"}, False, False),
    ("transaction", "stage", {"operation": "stage", "transaction_id": "tx_1", "action": {"action_type": "show", "target": "ent_1"}}, False, False),
    ("transaction", "status", {"operation": "status"}, False, False),
    ("transaction", "abort", {"operation": "abort", "transaction_id": "tx_1"}, False, False),
    ("transaction", "preview", {"operation": "preview", "transaction_id": "tx_1"}, True, False),
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


@pytest.mark.parametrize("tool_name, payload", [
    ("fusion_view", {"node_id": "desk-1", "operation": "camera_set", "fov": 45.0}),
    ("fusion_view", {"node_id": "desk-1", "operation": "fit"}),
    ("fusion_view", {"node_id": "desk-1", "operation": "zoom_entity", "target": "ent_1"}),
    ("fusion_view", {"node_id": "desk-1", "operation": "orient_to_face", "target": "ent_1"}),
    ("fusion_view", {"node_id": "desk-1", "operation": "standard_view", "view_type": "top"}),
    ("fusion_metadata", {"node_id": "desk-1", "operation": "set", "target": "ent_1", "name": "k", "value": "v"}),
    ("fusion_metadata", {"node_id": "desk-1", "operation": "remove", "target": "ent_1", "name": "k"}),
    ("fusion_metadata", {"node_id": "desk-1", "operation": "tag", "target": "ent_1", "tag_name": "t"}),
    ("fusion_metadata", {"node_id": "desk-1", "operation": "untag", "target": "ent_1", "tag_name": "t"}),
    ("fusion_metadata", {"node_id": "desk-1", "operation": "set_role", "target": "ent_1", "role": "r"}),
    ("fusion_metadata", {"node_id": "desk-1", "operation": "clear_role", "target": "ent_1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "text_create", "text": "t", "height_mm": 5.0, "position": {"x": 0, "y": 0, "z": 0, "frame": {"space": "world"}}}),
    ("fusion_style", {"node_id": "desk-1", "operation": "text_update", "text_ref": "text_1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "text_delete", "text_ref": "text_1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "text_extrude", "text_ref": "text_1", "distance_mm": 2.0}),
    ("fusion_style", {"node_id": "desk-1", "operation": "text_cut", "text_ref": "text_1", "distance_mm": 2.0, "target_body": "ent_1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "show", "target": "ent_1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "hide", "target": "ent_1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "set", "target": "ent_1", "visible": True}),
    ("fusion_style", {"node_id": "desk-1", "operation": "show_only", "target": "ent_1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "isolate", "target": "ent_1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "restore"}),
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
    registry = build_tool_registry(container)
    tool = registry.get(tool_name)
    assert tool is not None

    await container.desktop_nodes.register(
        "desk-1",
        [{"name": "fusion_mcp_execute"}],
        fusion_available=True,
    )

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
    mock_container.desktop_nodes.external_result = MagicMock(return_value=(
        {"isError": False},
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

    resource_links = [b for b in result.content if isinstance(b, types.ResourceLink)]
    assert len(resource_links) >= 1


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
