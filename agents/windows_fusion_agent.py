"""Outbound Windows agent relaying Autodesk Fusion Desktop MCP to Bridge."""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import http.client
import io
import json
import os
import threading
import time
import urllib.error
import urllib.parse
from contextlib import AsyncExitStack, suppress
from typing import Any
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

DEFAULT_FUSION_URL = "http://127.0.0.1:27182/mcp"
INLINE_RESULT_BYTES = 192 * 1024
RESULT_CHUNK_BYTES = 128 * 1024
RESULT_DELIVERY_ATTEMPTS = 6
RESULT_DELIVERY_SECONDS = 90.0


def default_outbox_directory() -> Path:
    configured = os.environ.get("DEVELOPMENT_BRIDGE_FUSION_OUTBOX")
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "DevelopmentBridgeFusion"
    return Path(configured) if configured else base / "outbox"


class ResultOutbox:
    """Atomic local result spool; files are removed only after accepted/stale delivery."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def save(self, command_id: str, result: dict[str, Any]) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{command_id}.json"
        temporary = self.directory / f".{command_id}.tmp"
        temporary.write_text(json.dumps({"command_id": command_id, "result": result}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, path)
        return path

    def remove(self, command_id: str) -> None:
        (self.directory / f"{command_id}.json").unlink(missing_ok=True)

    def entries(self) -> list[tuple[str, dict[str, Any]]]:
        if not self.directory.exists():
            return []
        entries = []
        for path in sorted(self.directory.glob("*.json"), key=lambda item: item.stat().st_mtime):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value.get("command_id"), str) and isinstance(value.get("result"), dict):
                    entries.append((value["command_id"], value["result"]))
            except (OSError, ValueError, AttributeError):
                print(f"Invalid Fusion result outbox entry retained: {path.name}", flush=True)
        return entries

    def count(self) -> int:
        return len(self.entries())


class _PersistentHTTPSChannel:
    """One serialized persistent HTTPS connection for one traffic class."""

    def __init__(self, base_url: str, token: str, timeout_seconds: float = 35.0) -> None:
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Development Bridge URL must be HTTPS")
        self.host = parsed.hostname
        self.port = parsed.port or 443
        self.base_path = parsed.path.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.headers = {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Connection": "keep-alive",
        }
        self._connection: http.client.HTTPSConnection | None = None
        self._lock = threading.Lock()

    def _conn(self) -> http.client.HTTPSConnection:
        if self._connection is None:
            self._connection = http.client.HTTPSConnection(self.host, self.port, timeout=self.timeout_seconds)
        return self._connection

    def close(self) -> None:
        if self._connection is not None:
            with suppress(Exception):
                self._connection.close()
        self._connection = None

    def post(self, suffix: str, body: dict[str, Any] | None) -> dict[str, Any]:
        payload = json.dumps(body or {}, separators=(",", ":")).encode("utf-8")
        path = self.base_path + suffix
        with self._lock:
            connection = self._conn()
            try:
                connection.request("POST", path, body=payload, headers=self.headers)
                response = connection.getresponse()
                raw = response.read()
            except (OSError, TimeoutError, http.client.HTTPException) as exc:
                self.close()
                raise urllib.error.URLError(str(exc)) from exc
            if response.status >= 400:
                raise urllib.error.HTTPError(
                    f"https://{self.host}:{self.port}{path}",
                    response.status,
                    response.reason,
                    response.headers,
                    io.BytesIO(raw),
                )
            try:
                return json.loads(raw or b"{}")
            except ValueError as exc:
                self.close()
                raise urllib.error.URLError("Bridge returned invalid JSON") from exc


class BridgeClient:
    """Independent persistent channels prevent claim/result traffic from starving heartbeat."""

    def __init__(self, base_url: str, node_id: str, token: str) -> None:
        url = base_url.rstrip("/") + "/mcp/desktop-nodes/" + node_id
        self._claim = _PersistentHTTPSChannel(url, token)
        self._heartbeat = _PersistentHTTPSChannel(url, token)
        self._control = _PersistentHTTPSChannel(url, token)

    async def post(self, action: str, body: dict[str, Any] | None = None, query: str = "") -> dict[str, Any]:
        channel = self._claim if action == "claim" else self._heartbeat if action == "heartbeat" else self._control
        return await asyncio.to_thread(channel.post, "/" + action + query, body)

    async def close(self) -> None:
        await asyncio.gather(
            asyncio.to_thread(self._claim.close),
            asyncio.to_thread(self._heartbeat.close),
            asyncio.to_thread(self._control.close),
        )

def result_json(result: Any) -> dict[str, Any]:
    return result.model_dump(mode="json", exclude_none=True) if hasattr(result, "model_dump") else {"content": [{"type": "text", "text": str(result)}], "isError": True}


async def fusion_endpoint_available(fusion_url: str, timeout_seconds: float = 0.75) -> bool:
    parsed = urllib.parse.urlsplit(fusion_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        _reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout_seconds)
    except (OSError, TimeoutError, asyncio.TimeoutError):
        return False
    writer.close()
    with suppress(Exception):
        await writer.wait_closed()
    return True


async def keepalive(
    bridge: Any,
    tools: list[dict[str, Any]],
    interval_seconds: float,
    fusion_url: str | None = None,
    reconnect_event: asyncio.Event | None = None,
    telemetry: dict[str, Any] | None = None,
) -> None:
    """Keep Bridge liveness and local Fusion-port health independent from CAD calls."""
    failures = 0
    last_fusion_available = True
    while True:
        delay = interval_seconds if failures == 0 else min(2 ** min(failures - 1, 4), interval_seconds)
        await asyncio.sleep(delay)
        fusion_available = True if fusion_url is None else await fusion_endpoint_available(fusion_url)
        if fusion_url is not None and fusion_available != last_fusion_available:
            print(
                "Fusion MCP watchdog: port recovered" if fusion_available else "Fusion MCP watchdog: port unavailable; reconnect requested",
                flush=True,
            )
        last_fusion_available = fusion_available
        if not fusion_available and reconnect_event is not None:
            reconnect_event.set()
        try:
            body: dict[str, Any] = {"fusion_available": fusion_available}
            if telemetry is not None:
                body["telemetry"] = dict(telemetry)
            await bridge.post("heartbeat", body)
            if failures:
                print(f"Bridge heartbeat recovered after {failures} failure(s)", flush=True)
            failures = 0
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                try:
                    registration: dict[str, Any] = {
                        "fusion_available": fusion_available,
                        "tools": tools if fusion_available else [],
                    }
                    if telemetry is not None:
                        registration["telemetry"] = dict(telemetry)
                    await bridge.post(
                        "register",
                        registration,
                    )
                    if failures:
                        print(f"Bridge heartbeat recovered after {failures} failure(s)", flush=True)
                    failures = 0
                except Exception as register_exc:
                    failures += 1
                    print(f"Bridge heartbeat degraded: failures={failures} error={type(register_exc).__name__}", flush=True)
            else:
                failures += 1
                if failures == 1 or failures in {3, 6}:
                    print(f"Bridge heartbeat degraded: failures={failures} error=HTTP{exc.code}", flush=True)
        except Exception as exc:
            failures += 1
            if failures == 1 or failures in {3, 6}:
                print(f"Bridge heartbeat degraded: failures={failures} error={type(exc).__name__}", flush=True)


async def submit_result_safely(
    bridge: Any,
    command_id: str,
    result: dict[str, Any],
    tools: list[dict[str, Any]] | None = None,
    fusion_available: bool = True,
    outbox: ResultOutbox | None = None,
    max_attempts: int = RESULT_DELIVERY_ATTEMPTS,
    max_elapsed_seconds: float = RESULT_DELIVERY_SECONDS,
) -> bool:
    """Deliver a completed result with bounded retries; never replay the CAD command."""
    if outbox is not None:
        outbox.save(command_id, result)
    serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    content = result.get("content")
    contains_inline_image = isinstance(content, list) and any(
        isinstance(item, dict)
        and item.get("type") == "image"
        and isinstance(item.get("data"), str)
        for item in content
    )
    attempt = 0
    started = time.monotonic()
    while attempt < max_attempts and time.monotonic() - started <= max_elapsed_seconds:
        try:
            delivered_result = result
            if contains_inline_image or len(serialized) > INLINE_RESULT_BYTES:
                digest = hashlib.sha256(serialized).hexdigest()
                upload = await bridge.post("result-upload-start", {"command_id": command_id, "size_bytes": len(serialized), "sha256": digest})
                upload_id = upload["upload_id"]
                offset = 0
                while offset < len(serialized):
                    chunk = serialized[offset:offset + RESULT_CHUNK_BYTES]
                    response = await bridge.post("result-upload-chunk", {
                        "upload_id": upload_id, "offset": offset,
                        "data": base64.b64encode(chunk).decode("ascii"),
                    })
                    offset = response["offset"]
                finalized = await bridge.post("result-upload-finalize", {"upload_id": upload_id})
                delivered_result = finalized
            await bridge.post("result", {"command_id": command_id, "result": delivered_result})
            if outbox is not None:
                outbox.remove(command_id)
            return True
        except urllib.error.HTTPError as exc:
            if exc.code in {400, 409}:
                print(f"Bridge no longer accepts command {command_id}; result discarded safely", flush=True)
                if outbox is not None:
                    outbox.remove(command_id)
                return False
            if exc.code == 404 and tools is not None:
                try:
                    await bridge.post(
                        "register",
                        {"fusion_available": fusion_available, "tools": tools if fusion_available else []},
                    )
                except Exception as register_exc:
                    print(f"Bridge re-registration during result delivery failed ({type(register_exc).__name__})", flush=True)
            elif exc.code not in {408, 425, 429} and exc.code < 500:
                print(f"Bridge permanently rejected command {command_id} result (HTTP {exc.code}); retained in outbox", flush=True)
                return False
            delay = min(2 ** min(attempt, 5), 30)
            print(f"Bridge result delivery HTTP {exc.code}; retrying in {delay}s", flush=True)
            attempt += 1
            await asyncio.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as exc:
            delay = min(2 ** min(attempt, 5), 30)
            print(f"Bridge result delivery failed ({type(exc).__name__}); retrying in {delay}s", flush=True)
            attempt += 1
            await asyncio.sleep(delay)
    print(f"Bridge result delivery exhausted for command {command_id}; retained in outbox", flush=True)
    return False


async def flush_outbox(
    bridge: Any,
    outbox: ResultOutbox,
    tools: list[dict[str, Any]],
    telemetry: dict[str, Any],
) -> bool:
    entries = outbox.entries()
    telemetry["result_outbox_count"] = len(entries)
    telemetry["result_delivery_degraded"] = bool(entries)
    if entries:
        print(f"Bridge result delivery degraded: outbox={len(entries)}; flushing before claims", flush=True)
    for command_id, result in entries:
        delivered = await submit_result_safely(bridge, command_id, result, tools, outbox=outbox)
        telemetry["result_outbox_count"] = outbox.count()
        if not delivered and telemetry["result_outbox_count"]:
            telemetry["result_delivery_degraded"] = True
            return False
    telemetry["result_delivery_degraded"] = False
    if entries:
        print("Bridge result delivery recovered: outbox=0", flush=True)
    return True


async def run(
    bridge: BridgeClient,
    fusion_url: str,
    reconnect_seconds: float,
    heartbeat_seconds: float,
    fusion_call_timeout_seconds: float,
    claim_wait_seconds: float,
) -> None:
    outbox = ResultOutbox(default_outbox_directory())
    telemetry: dict[str, Any] = {"result_delivery_degraded": False, "result_outbox_count": outbox.count()}
    while True:
        try:
            async with AsyncExitStack() as stack:
                streams = await stack.enter_async_context(streamable_http_client(fusion_url))
                session = await stack.enter_async_context(ClientSession(streams[0], streams[1]))
                await session.initialize()
                tools = [tool.model_dump(mode="json", exclude_none=True) for tool in (await session.list_tools()).tools]
                names = {tool["name"] for tool in tools}
                telemetry["result_outbox_count"] = outbox.count()
                telemetry["result_delivery_degraded"] = bool(telemetry["result_outbox_count"])
                await bridge.post("register", {"fusion_available": True, "tools": tools, "telemetry": telemetry})
                print(f"Connected: Fusion MCP tools discovered: {len(tools)}", flush=True)
                if not await flush_outbox(bridge, outbox, tools, telemetry):
                    raise RuntimeError("Fusion result outbox remains undeliverable")
                reconnect_event = asyncio.Event()
                keepalive_task = asyncio.create_task(keepalive(bridge, tools, heartbeat_seconds, fusion_url, reconnect_event, telemetry))
                try:
                    while True:
                        if reconnect_event.is_set():
                            raise RuntimeError("Fusion MCP watchdog requested reconnect")
                        command = (await bridge.post("claim", query=f"?wait={claim_wait_seconds:g}")).get("command")
                        if command is None:
                            continue
                        operation_id = command.get("operation_id", command["command_id"])
                        print(f"Fusion operation {operation_id}: {command['tool_name']} started", flush=True)
                        reconnect_after_result = False
                        if reconnect_event.is_set():
                            result = {"content": [{"type": "text", "text": "Fusion MCP became unavailable before execution"}], "isError": True}
                            reconnect_after_result = True
                        elif command["tool_name"] not in names:
                            result = {"content": [{"type": "text", "text": "Tool is no longer discovered"}], "isError": True}
                        else:
                            try:
                                result = result_json(await session.call_tool(
                                    command["tool_name"], command.get("arguments", {}),
                                    read_timeout_seconds=fusion_call_timeout_seconds,
                                ))
                            except Exception as exc:
                                result = {"content": [{"type": "text", "text": f"Fusion tool call failed: {type(exc).__name__}"}], "isError": True}
                                reconnect_after_result = True
                        delivered = await submit_result_safely(
                            bridge, command["command_id"], result, tools,
                            fusion_available=not reconnect_event.is_set(),
                            outbox=outbox,
                        )
                        telemetry["result_outbox_count"] = outbox.count()
                        telemetry["result_delivery_degraded"] = bool(telemetry["result_outbox_count"])
                        state = "delivered" if delivered else "retained/stale"
                        print(f"Fusion operation {operation_id}: result {state}", flush=True)
                        if telemetry["result_delivery_degraded"]:
                            raise RuntimeError("Fusion result delivery degraded; reconnecting before new claims")
                        if reconnect_after_result or reconnect_event.is_set():
                            raise RuntimeError("Fusion MCP session requires reconnect")
                finally:
                    keepalive_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await keepalive_task
        except Exception as exc:
            print(f"Fusion/Bridge unavailable ({type(exc).__name__}); retrying in {reconnect_seconds:g}s", flush=True)
            try:
                await bridge.post("register", {"fusion_available": False, "tools": []})
            except Exception:
                pass
            await asyncio.sleep(reconnect_seconds)


async def async_main(args: argparse.Namespace) -> None:
    bridge = BridgeClient(args.bridge_url, args.node_id, args.token)
    try:
        await run(
            bridge, args.fusion_url, args.reconnect_seconds, args.heartbeat_seconds,
            args.fusion_call_timeout_seconds, args.claim_wait_seconds,
        )
    finally:
        await bridge.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge-url", default=os.environ.get("DEVELOPMENT_BRIDGE_URL"))
    parser.add_argument("--node-id", default=os.environ.get("DEVELOPMENT_BRIDGE_NODE_ID"))
    parser.add_argument("--token", default=os.environ.get("DEVELOPMENT_BRIDGE_DESKTOP_NODE_TOKEN"))
    parser.add_argument("--fusion-url", default=os.environ.get("FUSION_MCP_URL", DEFAULT_FUSION_URL))
    parser.add_argument("--reconnect-seconds", type=float, default=5)
    parser.add_argument("--heartbeat-seconds", type=float, default=5)
    parser.add_argument("--fusion-call-timeout-seconds", type=float, default=285)
    parser.add_argument("--claim-wait-seconds", type=float, default=10)
    args = parser.parse_args()
    if not args.bridge_url or not args.node_id or not args.token:
        parser.error("bridge URL, node ID, and token are required via CLI or environment")
    if min(args.reconnect_seconds, args.heartbeat_seconds, args.fusion_call_timeout_seconds, args.claim_wait_seconds) <= 0:
        parser.error("timing values must be positive")
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
