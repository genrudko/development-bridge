from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp import types

from app.api.context import RequestContext
from app.api.errors import BridgeError, ErrorCode
from app.container import ApplicationContainer, build_container
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

    # Verify DesktopNodeService.call was called with journal having mutation=False
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

    # Verify submit was called with correct mutation flag in journal
    assert mock_container.desktop_nodes.submit.called
    call_args = mock_container.desktop_nodes.submit.call_args
    journal = call_args[0][3] if len(call_args[0]) > 3 else call_args[1].get("journal")
    assert isinstance(journal, dict)
    assert journal.get("mutation") is expected_mutation


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


@pytest.mark.asyncio
async def test_inline_small_image_or_base64_result_is_externalized_and_bounded(
    mock_container: ApplicationContainer,
):
    registry = build_tool_registry(mock_container)
    tool = registry.get("fusion_read")
    assert tool is not None

    # Direct response containing small inline image content block
    small_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    mock_container.desktop_nodes.call = AsyncMock(return_value={
        "content": [
            {
                "type": "image",
                "data": small_b64,
                "mimeType": "image/png",
            },
            {
                "type": "text",
                "text": json.dumps({
                    "api_version": "fusion.cad/v1",
                    "status": "succeeded",
                    "summary": "rendered thumbnail",
                    "data": {"thumbnail_b64": small_b64},
                }),
            },
        ],
        "isError": False,
    })

    req_ctx = RequestContext(request_id="req_inline_img")
    params = types.CallToolRequestParams(
        name="fusion_read",
        arguments={"node_id": "desk-1", "operation": "entity", "ref": "ent_1234"},
    )
    result = await tool.handler(None, params, req_ctx)
    assert isinstance(result, types.CallToolResult)
    assert not result.is_error

    # Ensure no raw base64 or image payload is in the model-visible text content
    for block in result.content:
        if isinstance(block, types.TextContent):
            assert small_b64 not in block.text

    # Ensure resource links are generated for externalized images
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
