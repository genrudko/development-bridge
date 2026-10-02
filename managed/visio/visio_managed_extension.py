from __future__ import annotations

import uuid
from pathlib import Path

from mcp.server.mcpserver.utilities.types import Image

MANAGED_EXTENSION_VERSION = "2026.10.02.1"


def install(namespace: dict) -> None:
    """Register managed Visio tools into the already-hardened live launcher."""
    mcp = namespace["mcp"]
    visio = namespace["visio"]
    parse_page = namespace["_parse_page"]
    workspace = Path(namespace["WORKSPACE"]).resolve()

    @mcp.tool()
    def render_page_png(page: str = "", doc_name: str = "") -> Image:
        """Render an existing Visio page to PNG and return the actual image bytes.

        This is read-only with respect to the Visio document. A short-lived PNG is
        created only inside the approved Visio workspace and deleted immediately
        after the bytes are read.
        """
        output = workspace / f".visio-snapshot-{uuid.uuid4().hex}.png"
        try:
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            page_obj.Export(str(output))
            raw = output.read_bytes()
            if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError("Visio page export did not produce a PNG")
            if len(raw) > 32 * 1024 * 1024:
                raise RuntimeError("Visio page PNG exceeds the 32 MiB visual limit")
            return Image(data=raw, format="png")
        finally:
            try:
                output.unlink(missing_ok=True)
            except OSError:
                pass
