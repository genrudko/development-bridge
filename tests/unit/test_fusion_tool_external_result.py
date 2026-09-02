from types import SimpleNamespace

import pytest
from mcp import types

from app.tools.fusion import fusion_tools


@pytest.mark.asyncio
async def test_external_screenshot_becomes_native_image_and_resource_link():
    encoded = "iVBORw0KGgo="

    class Desktop:
        async def call(self, *args):
            return {"external_result": {"result_id": "result-1"}}

        def external_result(self, reference):
            return (
                {"content": [{"type": "image", "data": encoded, "mimeType": "image/png"}], "isError": False},
                {"size_bytes": 999999, "sha256": "a" * 64, "file_name": "fusion-result.json", "export_url": "https://bridge.example/mcp/desktop-results/exports/capability"},
            )

    tool = next(item for item in fusion_tools(SimpleNamespace(desktop_nodes=Desktop())) if item.definition.name == "fusion_call")
    result = await tool.handler(None, SimpleNamespace(arguments={"node_id": "desk", "tool_name": "fusion_mcp_read"}), SimpleNamespace(request_id="request-1"))
    assert isinstance(result.content[1], types.ImageContent)
    assert result.content[1].data == encoded
    assert isinstance(result.content[2], types.ResourceLink)
    assert encoded not in result.content[0].text
