"""Outbound Windows agent relaying Autodesk Fusion Desktop MCP to Bridge."""
from __future__ import annotations
import argparse, asyncio, json, os, urllib.error, urllib.request
from contextlib import AsyncExitStack
from typing import Any
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

DEFAULT_FUSION_URL = "http://127.0.0.1:27182/mcp"

class BridgeClient:
    def __init__(self, base_url: str, node_id: str, token: str) -> None:
        self.url, self.token = base_url.rstrip("/") + "/mcp/desktop-nodes/" + node_id, token
    def _post(self, action: str, body: dict[str, Any] | None, query: str) -> dict[str, Any]:
        request = urllib.request.Request(self.url + "/" + action + query, data=json.dumps(body or {}).encode(), headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=35) as response:
            return json.loads(response.read())
    async def post(self, action: str, body: dict[str, Any] | None = None, query: str = "") -> dict[str, Any]:
        return await asyncio.to_thread(self._post, action, body, query)

def result_json(result: Any) -> dict[str, Any]:
    return result.model_dump(mode="json", exclude_none=True) if hasattr(result, "model_dump") else {"content": [{"type": "text", "text": str(result)}], "isError": True}

async def run(bridge: BridgeClient, fusion_url: str, reconnect_seconds: float) -> None:
    while True:
        try:
            async with AsyncExitStack() as stack:
                streams = await stack.enter_async_context(streamable_http_client(fusion_url))
                session = await stack.enter_async_context(ClientSession(streams[0], streams[1]))
                await session.initialize()
                tools = [tool.model_dump(mode="json", exclude_none=True) for tool in (await session.list_tools()).tools]
                names = {tool["name"] for tool in tools}
                await bridge.post("register", {"fusion_available": True, "tools": tools})
                while True:
                    command = (await bridge.post("claim", query="?wait=25")).get("command")
                    if command is None:
                        await bridge.post("heartbeat", {"fusion_available": True})
                        continue
                    if command["tool_name"] not in names:
                        result = {"content": [{"type": "text", "text": "Tool is no longer discovered"}], "isError": True}
                    else:
                        try:
                            result = result_json(await session.call_tool(command["tool_name"], command.get("arguments", {})))
                        except Exception as exc:
                            result = {"content": [{"type": "text", "text": f"Fusion tool call failed: {type(exc).__name__}"}], "isError": True}
                    await bridge.post("result", {"command_id": command["command_id"], "result": result})
        except Exception as exc:
            print(f"Fusion/Bridge unavailable ({type(exc).__name__}); retrying in {reconnect_seconds:g}s", flush=True)
            try: await bridge.post("register", {"fusion_available": False, "tools": []})
            except Exception: pass
            await asyncio.sleep(reconnect_seconds)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge-url", default=os.environ.get("DEVELOPMENT_BRIDGE_URL")); parser.add_argument("--node-id", default=os.environ.get("DEVELOPMENT_BRIDGE_NODE_ID")); parser.add_argument("--token", default=os.environ.get("DEVELOPMENT_BRIDGE_DESKTOP_NODE_TOKEN")); parser.add_argument("--fusion-url", default=os.environ.get("FUSION_MCP_URL", DEFAULT_FUSION_URL)); parser.add_argument("--reconnect-seconds", type=float, default=5)
    args = parser.parse_args()
    if not args.bridge_url or not args.node_id or not args.token: parser.error("bridge URL, node ID, and token are required via CLI or environment")
    asyncio.run(run(BridgeClient(args.bridge_url, args.node_id, args.token), args.fusion_url, args.reconnect_seconds))
if __name__ == "__main__": main()
