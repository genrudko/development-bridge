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
    return build_container(BridgeSettings())


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
    ("fusion_read", {"node_id": "desk-1", "operation": "model_snapshot"}),
    ("fusion_inspect", {"node_id": "desk-1", "operation": "describe", "target": "ent_face_1"}),
    ("fusion_view", {"node_id": "desk-1", "operation": "camera_read"}),
    ("fusion_metadata", {"node_id": "desk-1", "operation": "query", "group": "bridge.cad/v1"}),
    ("fusion_style", {"node_id": "desk-1", "operation": "show", "target": "ent_body_1"}),
    ("fusion_validate", {"node_id": "desk-1", "operation": "run"}),
    ("fusion_transaction", {"node_id": "desk-1", "operation": "begin"}),
])
@pytest.mark.asyncio
async def test_domain_tools_execute_via_service(
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
        arguments={"node_id": "desk-1", "operation": "model_snapshot"},
    )
    result = await tool.handler(None, params, req_ctx)
    assert isinstance(result, types.CallToolResult)
    assert not result.is_error
    resource_links = [b for b in result.content if isinstance(b, types.ResourceLink)]
    assert len(resource_links) == 2


@pytest.mark.asyncio
async def test_cad_error_raises_with_correct_code_and_retryable(mock_container: ApplicationContainer):
    registry = build_tool_registry(mock_container)
    tool = registry.get("fusion_style")
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
        name="fusion_style",
        arguments={"node_id": "desk-1", "operation": "show", "target": "ent_body_1"},
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
