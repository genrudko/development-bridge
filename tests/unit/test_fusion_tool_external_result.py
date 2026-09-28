import base64
from types import SimpleNamespace

import pytest
from mcp import types

from app.tools.fusion import fusion_tools


@pytest.mark.asyncio
async def test_external_screenshot_uses_resource_links_without_inline_base64():
    encoded = "iVBORw0KGgo="

    class Desktop:
        async def call(self, *args):
            return {"external_result": {"result_id": "result-1"}}

        def external_result(self, reference):
            return (
                {"content": [{"type": "image", "data": encoded, "mimeType": "image/png"}], "isError": False},
                {
                    "size_bytes": 999999,
                    "sha256": "a" * 64,
                    "file_name": "fusion-result.json",
                    "export_url": "https://bridge.example/mcp/desktop-results/exports/result-token",
                    "resources": [{
                        "uri": "https://bridge.example/mcp/desktop-results/exports/image-token",
                        "file_name": "fusion-image-result-1-0.png",
                        "mime_type": "image/png",
                        "size_bytes": 8,
                    }],
                },
            )

    tool = next(item for item in fusion_tools(SimpleNamespace(desktop_nodes=Desktop())) if item.definition.name == "fusion_call")
    result = await tool.handler(None, SimpleNamespace(arguments={"node_id": "desk", "tool_name": "fusion_mcp_read"}), SimpleNamespace(request_id="request-1"))

    assert not any(isinstance(block, types.ImageContent) for block in result.content)
    assert isinstance(result.content[1], types.ResourceLink)
    assert str(result.content[1].uri).endswith("/image-token")
    assert result.content[1].mime_type == "image/png"
    assert isinstance(result.content[2], types.ResourceLink)
    assert result.content[2].mime_type == "application/json"
    assert encoded not in str(result.content)


@pytest.mark.asyncio
async def test_fusion_result_view_returns_retained_desktop_image_as_mcp_image_content():
    png = b"\x89PNG\r\n\x1a\nviewer-tool-image"
    uri = "https://bridge.example/mcp/desktop-results/exports/r1.result.capability"

    class Desktop:
        def external_image_resource(self, resource_uri):
            assert resource_uri == uri
            return png, {
                "uri": uri,
                "file_name": "content.png",
                "mime_type": "image/png",
                "size_bytes": len(png),
                "sha256": "a" * 64,
            }

    tool = next(
        item for item in fusion_tools(SimpleNamespace(desktop_nodes=Desktop()))
        if item.definition.name == "fusion_result_view"
    )
    assert tool.definition.input_schema == {
        "type": "object",
        "properties": {"resource_uri": {"type": "string", "minLength": 1, "maxLength": 2048}},
        "required": ["resource_uri"],
        "additionalProperties": False,
    }

    result = await tool.handler(
        None,
        SimpleNamespace(arguments={"resource_uri": uri}),
        SimpleNamespace(request_id="request-view-1"),
    )

    images = [block for block in result.content if isinstance(block, types.ImageContent)]
    assert len(images) == 1
    assert images[0].mime_type == "image/png"
    assert base64.b64decode(images[0].data) == png
    assert not any(isinstance(block, types.ResourceLink) for block in result.content)
    assert "content.png" in result.content[0].text
