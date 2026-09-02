from __future__ import annotations

import asyncio
import os
import sys

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

URL = os.environ.get("DEVELOPMENT_BRIDGE_GC_URL", "http://127.0.0.1:8789/mcp")


async def run() -> int:
    async with streamable_http_client(URL) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            result = await session.call_tool(
                "bridge_call",
                {
                    "tool_name": "repository_gc_apply",
                    "arguments": {
                        "cache_days": 30,
                        "ephemeral_days": 14,
                        "max_groups": 4,
                        "confirm": True,
                    },
                },
            )
    text = "\n".join(
        block.text for block in result.content if getattr(block, "type", None) == "text"
    )
    if text:
        print(text[:16000])
    if getattr(result, "isError", False):
        # Busy is a normal maintenance skip, not a failed timer run.
        if "JOB_BUSY" in text:
            print("Managed repository GC skipped: durable job activity detected.")
            return 0
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
