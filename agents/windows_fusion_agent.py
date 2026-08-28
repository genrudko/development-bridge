"""Outbound Windows agent relaying Autodesk Fusion Desktop MCP to Bridge."""
from __future__ import annotations
import argparse, asyncio, json, os, urllib.error, urllib.request
from contextlib import AsyncExitStack, suppress
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

async def keepalive(bridge: BridgeClient, tools: list[dict[str, Any]], interval_seconds: float) -> None:
    """Keep Bridge liveness independent from potentially long Fusion calls."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await bridge.post("heartbeat", {"fusion_available": True})
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                # Bridge may have restarted and lost its process-local node state.
                try:
                    await bridge.post("register", {"fusion_available": True, "tools": tools})
                except Exception as register_exc:
                    print(f"Bridge re-registration failed ({type(register_exc).__name__})", flush=True)
            else:
                print(f"Bridge heartbeat failed (HTTP {exc.code})", flush=True)
        except Exception as exc:
            print(f"Bridge heartbeat failed ({type(exc).__name__})", flush=True)


async def submit_result_safely(
    bridge: BridgeClient,
    command_id: str,
    result: dict[str, Any],
    tools: list[dict[str, Any]] | None = None,
) -> bool:
    """Persistently deliver one completed result; never replay the CAD command."""
    attempt = 0
    while True:
        try:
            await bridge.post("result", {"command_id": command_id, "result": result})
            return True
        except urllib.error.HTTPError as exc:
            if exc.code in {400, 409}:
                print(f"Bridge no longer accepts command {command_id}; result discarded safely", flush=True)
                return False
            if exc.code == 404 and tools is not None:
                try:
                    await bridge.post("register", {"fusion_available": True, "tools": tools})
                except Exception as register_exc:
                    print(f"Bridge re-registration during result delivery failed ({type(register_exc).__name__})", flush=True)
            elif exc.code not in {408, 425, 429} and exc.code < 500:
                raise
            delay = min(2 ** min(attempt, 5), 30)
            print(f"Bridge result delivery HTTP {exc.code}; retrying in {delay}s", flush=True)
            attempt += 1
            await asyncio.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as exc:
            delay = min(2 ** min(attempt, 5), 30)
            print(
                f"Bridge result delivery failed ({type(exc).__name__}); retrying in {delay}s",
                flush=True,
            )
            attempt += 1
            await asyncio.sleep(delay)


async def run(bridge: BridgeClient, fusion_url: str, reconnect_seconds: float, heartbeat_seconds: float, fusion_call_timeout_seconds: float) -> None:
    while True:
        try:
            async with AsyncExitStack() as stack:
                streams = await stack.enter_async_context(streamable_http_client(fusion_url))
                session = await stack.enter_async_context(ClientSession(streams[0], streams[1]))
                await session.initialize()
                tools = [tool.model_dump(mode="json", exclude_none=True) for tool in (await session.list_tools()).tools]
                names = {tool["name"] for tool in tools}
                await bridge.post("register", {"fusion_available": True, "tools": tools})
                print(f"Connected: Fusion MCP tools discovered: {len(tools)}", flush=True)
                keepalive_task = asyncio.create_task(keepalive(bridge, tools, heartbeat_seconds))
                try:
                    while True:
                        command = (await bridge.post("claim", query="?wait=25")).get("command")
                        if command is None:
                            continue
                        operation_id = command.get("operation_id", command["command_id"])
                        print(f"Fusion operation {operation_id}: {command['tool_name']} started", flush=True)
                        reconnect_after_result = False
                        if command["tool_name"] not in names:
                            result = {"content": [{"type": "text", "text": "Tool is no longer discovered"}], "isError": True}
                        else:
                            try:
                                result = result_json(await session.call_tool(command["tool_name"], command.get("arguments", {}), read_timeout_seconds=fusion_call_timeout_seconds))
                            except Exception as exc:
                                result = {"content": [{"type": "text", "text": f"Fusion tool call failed: {type(exc).__name__}"}], "isError": True}
                                reconnect_after_result = True
                        delivered = await submit_result_safely(bridge, command["command_id"], result, tools)
                        print(
                            f"Fusion operation {operation_id}: result {'delivered' if delivered else 'stale'}",
                            flush=True,
                        )
                        if reconnect_after_result:
                            raise RuntimeError("Fusion MCP call failed; reconnecting session")
                finally:
                    keepalive_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await keepalive_task
        except Exception as exc:
            print(f"Fusion/Bridge unavailable ({type(exc).__name__}); retrying in {reconnect_seconds:g}s", flush=True)
            try: await bridge.post("register", {"fusion_available": False, "tools": []})
            except Exception: pass
            await asyncio.sleep(reconnect_seconds)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge-url", default=os.environ.get("DEVELOPMENT_BRIDGE_URL")); parser.add_argument("--node-id", default=os.environ.get("DEVELOPMENT_BRIDGE_NODE_ID")); parser.add_argument("--token", default=os.environ.get("DEVELOPMENT_BRIDGE_DESKTOP_NODE_TOKEN")); parser.add_argument("--fusion-url", default=os.environ.get("FUSION_MCP_URL", DEFAULT_FUSION_URL)); parser.add_argument("--reconnect-seconds", type=float, default=5); parser.add_argument("--heartbeat-seconds", type=float, default=10); parser.add_argument("--fusion-call-timeout-seconds", type=float, default=285)
    args = parser.parse_args()
    if not args.bridge_url or not args.node_id or not args.token: parser.error("bridge URL, node ID, and token are required via CLI or environment")
    if args.reconnect_seconds <= 0 or args.heartbeat_seconds <= 0 or args.fusion_call_timeout_seconds <= 0: parser.error("timing values must be positive")
    asyncio.run(run(BridgeClient(args.bridge_url, args.node_id, args.token), args.fusion_url, args.reconnect_seconds, args.heartbeat_seconds, args.fusion_call_timeout_seconds))
if __name__ == "__main__": main()
