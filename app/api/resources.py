from __future__ import annotations

import base64
from pathlib import Path

from mcp import types


DEFAULT_FILE_RESOURCE_INLINE_LIMIT = 4 * 1024 * 1024


def file_resource_blocks(
    path: Path,
    *,
    uri: str,
    file_name: str,
    media_type: str,
    size_bytes: int,
    inline_limit: int = DEFAULT_FILE_RESOURCE_INLINE_LIMIT,
    description: str | None = None,
) -> tuple[types.ResourceLink | types.EmbeddedResource, ...]:
    """Build standard MCP blocks for an already-authorized local file."""
    blocks: list[types.ResourceLink | types.EmbeddedResource] = [
        types.ResourceLink(
            uri=uri,
            name=file_name,
            title=file_name,
            mimeType=media_type,
            size=size_bytes,
            description=description,
        )
    ]
    if size_bytes <= inline_limit:
        blocks.append(
            types.EmbeddedResource(
                type="resource",
                resource=types.BlobResourceContents(
                    uri=uri,
                    mimeType=media_type,
                    blob=base64.b64encode(path.read_bytes()).decode("ascii"),
                ),
            )
        )
    return tuple(blocks)
