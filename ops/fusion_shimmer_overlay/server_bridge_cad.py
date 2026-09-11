"""Thin private MCP surface for the Development Bridge Shimmer overlay."""

from __future__ import annotations


def register(mcp, client):
    @mcp.tool()
    def _bridge_cad_guard(document_ref: str) -> dict:
        """Return the private provider guard used by fusion.cad/v1 coherence checks."""
        return client.call("bridge.cad_guard", {"document_ref": document_ref})

    @mcp.tool()
    def _bridge_cad_apply(document_ref: str, expected_guard: str, mode: str, operations: list) -> dict:
        """Apply one prevalidated, allow-listed fusion.cad/v1 rich-provider plan."""
        return client.call(
            "bridge.cad_apply",
            {
                "document_ref": document_ref,
                "expected_guard": expected_guard,
                "mode": mode,
                "operations": operations,
            },
        )
