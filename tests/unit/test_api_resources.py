import base64

import pytest
from mcp import types

from app.api.resources import file_resource_blocks


def test_file_resource_blocks_include_link_and_byte_exact_inline_resource(
    tmp_path, monkeypatch
):
    path = tmp_path / "private-location.bin"
    content = b"\x00binary\xffcontent"
    path.write_bytes(content)
    original_read_bytes = path.__class__.read_bytes
    reads = []

    def counted_read_bytes(candidate):
        reads.append(candidate)
        return original_read_bytes(candidate)

    monkeypatch.setattr(path.__class__, "read_bytes", counted_read_bytes)

    blocks = file_resource_blocks(
        path,
        uri="https://downloads.example/resource/token",
        file_name="payload.bin",
        media_type="application/octet-stream",
        size_bytes=len(content),
        inline_limit=len(content),
        description="Test payload",
    )

    assert len(blocks) == 2
    assert isinstance(blocks[0], types.ResourceLink)
    assert blocks[0].uri == "https://downloads.example/resource/token"
    assert blocks[0].name == blocks[0].title == "payload.bin"
    assert blocks[0].mime_type == "application/octet-stream"
    assert blocks[0].size == len(content)
    assert isinstance(blocks[1], types.EmbeddedResource)
    assert isinstance(blocks[1].resource, types.BlobResourceContents)
    assert blocks[1].resource.uri == blocks[0].uri
    assert blocks[1].resource.mime_type == blocks[0].mime_type
    assert base64.b64decode(blocks[1].resource.blob) == content
    assert reads == [path]
    assert str(path) not in "".join(block.model_dump_json() for block in blocks)


def test_file_resource_blocks_skip_read_and_inline_resource_above_limit(
    tmp_path, monkeypatch
):
    path = tmp_path / "payload.bin"
    path.write_bytes(b"larger")
    monkeypatch.setattr(path.__class__, "read_bytes", lambda self: pytest.fail("read"))

    blocks = file_resource_blocks(
        path,
        uri="https://downloads.example/resource/token",
        file_name="payload.bin",
        media_type="application/octet-stream",
        size_bytes=6,
        inline_limit=5,
    )

    assert len(blocks) == 1
    assert isinstance(blocks[0], types.ResourceLink)
