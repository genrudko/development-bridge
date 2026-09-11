"""Thin private MCP surface for the Development Bridge Shimmer overlay."""

from __future__ import annotations


def register(mcp, client):
    @mcp.tool()
    def _bridge_cad_guard() -> dict:
        """Return the private provider guard used by fusion.cad/v1 coherence checks."""
        return client.call("bridge.cad_guard", {})

    @mcp.tool()
    def _bridge_cad_apply(expected_guard: str, mode: str, operations: list) -> dict:
        """Apply one prevalidated, allow-listed fusion.cad/v1 rich-provider plan."""
        return client.call(
            "bridge.cad_apply",
            {
                "expected_guard": expected_guard,
                "mode": mode,
                "operations": operations,
            },
        )
