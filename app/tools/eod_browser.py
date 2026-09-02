from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
from contextlib import AsyncExitStack
from pathlib import Path
from uuid import uuid4
from urllib.parse import urljoin, urlsplit
from urllib.request import urlopen

from mcp import ClientSession, types
from mcp.client.sse import sse_client

from app.api.errors import BridgeError, ErrorCode
from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.container import ApplicationContainer

SAFE_BROWSER_TOOLS = frozenset(
    {
        "browser_close",
        "browser_resize",
        "browser_console_messages",
        "browser_handle_dialog",
        "browser_evaluate",
        "browser_find",
        "browser_fill_form",
        "browser_press_key",
        "browser_type",
        "browser_navigate",
        "browser_navigate_back",
        "browser_network_requests",
        "browser_network_request",
        "browser_take_screenshot",
        "browser_snapshot",
        "browser_click",
        "browser_drag",
        "browser_hover",
        "browser_select_option",
        "browser_tabs",
        "browser_wait_for",
    }
)


def _origin_tuple(value: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(value)
    return parsed.scheme, parsed.hostname or "", parsed.port


def _validate_navigation(allowed_origin: str, tool_name: str, arguments: dict) -> None:
    candidate: str | None = None
    if tool_name == "browser_navigate":
        candidate = arguments.get("url")
    elif tool_name == "browser_tabs" and arguments.get("action") == "new":
        candidate = arguments.get("url")
    if not candidate:
        return
    if _origin_tuple(candidate) != _origin_tuple(allowed_origin):
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "EOD browser navigation is restricted to the development origin",
            details={"allowed_origin": allowed_origin, "requested_url": candidate},
        )


class _BrowserWorker:
    def __init__(self, url: str, launcher) -> None:
        self.url = url
        self.launcher = launcher
        self._queue: asyncio.Queue[tuple[str, str | None, dict, asyncio.Future]] = (
            asyncio.Queue()
        )
        self._task: asyncio.Task | None = None
        self._start_lock = asyncio.Lock()

    async def _open_session(self) -> tuple[AsyncExitStack, ClientSession]:
        stack = AsyncExitStack()
        try:
            read, write = await stack.enter_async_context(
                sse_client(self.url, timeout=5, sse_read_timeout=90)
            )
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            return stack, session
        except BaseException:
            await stack.aclose()
            raise

    async def _connect(self) -> tuple[AsyncExitStack, ClientSession]:
        try:
            return await self._open_session()
        except Exception:
            if self.launcher is None:
                raise
            await _run_launcher(self.launcher)
            await asyncio.sleep(0.25)
            return await self._open_session()

    async def _run(self) -> None:
        stack: AsyncExitStack | None = None
        terminal_error: BaseException | None = None
        try:
            stack, session = await self._connect()
            while True:
                kind, tool_name, arguments, future = await self._queue.get()
                if future.cancelled():
                    continue
                if kind == "stop":
                    future.set_result(None)
                    break
                try:
                    if kind == "list":
                        result = await session.list_tools()
                    else:
                        result = await session.call_tool(
                            tool_name or "",
                            arguments,
                            read_timeout_seconds=90,
                        )
                except BaseException as exc:
                    terminal_error = exc
                    if not future.done():
                        future.set_exception(exc)
                    break
                else:
                    if not future.done():
                        future.set_result(result)
        except BaseException as exc:
            terminal_error = exc
        finally:
            if stack is not None:
                try:
                    await stack.aclose()
                except BaseException as exc:
                    terminal_error = terminal_error or exc
            failure = terminal_error or RuntimeError("EOD browser worker stopped")
            while True:
                try:
                    _, _, _, future = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if not future.done():
                    future.set_exception(failure)
            self._task = None

    async def _submit(self, kind: str, tool_name: str | None = None, arguments: dict | None = None):
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        await self._queue.put((kind, tool_name, arguments or {}, future))
        async with self._start_lock:
            if self._task is None or self._task.done():
                self._task = asyncio.create_task(self._run(), name="eod-browser-upstream")
        return await future

    async def list_tools(self):
        return await self._submit("list")

    async def call_tool(self, tool_name: str, arguments: dict):
        return await self._submit("call", tool_name, arguments)

    async def close(self) -> None:
        task = self._task
        if task is None or task.done():
            return
        await self._submit("stop")
        await task


async def _run_launcher(path) -> None:
    process = await asyncio.create_subprocess_exec(
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=20)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError("EOD browser launcher timed out")
    if process.returncode != 0:
        detail = (stderr or stdout).decode("utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"EOD browser launcher failed: {detail}")



_MAX_INLINE_SCREENSHOT_BYTES = 12 * 1024 * 1024


def _prepare_tool_arguments(
    output_dir: Path | None, tool_name: str, arguments: dict
) -> tuple[dict, Path | None]:
    prepared = dict(arguments)
    if tool_name != "browser_take_screenshot" or output_dir is None:
        return prepared, None
    root = output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    requested = prepared.get("filename")
    if requested:
        requested = str(requested)
        if Path(requested).name != requested or requested in {".", ".."}:
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                "EOD browser screenshot filename must not contain path components",
                details={"filename": requested},
            )
        filename = requested
    else:
        filename = f"eod-eye-{uuid4().hex}.png"
    target = (root / filename).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "EOD browser screenshot escaped the configured output directory",
            details={"filename": filename},
        )
    mime_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    if mime_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "EOD browser screenshot has an unsupported media type",
            details={"mime_type": mime_type},
        )
    prepared["filename"] = str(target)
    return prepared, target


def _inline_screenshot_content(target: Path | None):
    if target is None or not target.is_file():
        return []
    size = target.stat().st_size
    if size > _MAX_INLINE_SCREENSHOT_BYTES:
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "EOD browser screenshot is too large to inline",
            details={"size_bytes": size, "limit_bytes": _MAX_INLINE_SCREENSHOT_BYTES},
        )
    mime_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return [
        types.ImageContent(
            type="image",
            data=base64.b64encode(target.read_bytes()).decode("ascii"),
            mimeType=mime_type,
        )
    ]

def _health_probe(origin: str) -> dict[str, object]:
    target = urljoin(origin.rstrip("/") + "/", "_health/")
    with urlopen(target, timeout=3) as response:
        body = response.read(8192).decode("utf-8", errors="replace")
        return {"url": target, "status": response.status, "body": body}


def eod_browser_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    settings = container.settings.eod_browser
    if not settings.enabled:
        return ()

    upstream_url = str(settings.url)
    allowed_origin = str(settings.allowed_origin).rstrip("/")
    launcher = settings.launcher
    output_dir = settings.output_dir
    browser = _BrowserWorker(upstream_url, launcher)

    async def status(ctx, params, request_context):
        try:
            upstream, health = await asyncio.gather(
                browser.list_tools(),
                asyncio.to_thread(_health_probe, allowed_origin),
            )
        except Exception as exc:
            raise BridgeError(
                ErrorCode.INTERNAL_ERROR,
                "EOD browser is unavailable",
                retryable=True,
                details={"reason": str(exc)},
            ) from exc
        available = sorted(tool.name for tool in upstream.tools if tool.name in SAFE_BROWSER_TOOLS)
        return to_mcp_result(
            success(
                request_context.request_id,
                {
                    "online": True,
                    "allowed_origin": allowed_origin,
                    "safe_tool_count": len(available),
                    "health": health,
                },
            )
        )

    async def tools(ctx, params, request_context):
        try:
            upstream = await browser.list_tools()
        except Exception as exc:
            raise BridgeError(
                ErrorCode.INTERNAL_ERROR,
                "EOD browser tool discovery failed",
                retryable=True,
                details={"reason": str(exc)},
            ) from exc
        available = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in upstream.tools
            if tool.name in SAFE_BROWSER_TOOLS
        ]
        return to_mcp_result(success(request_context.request_id, {"tools": available}))

    async def call(ctx, params, request_context):
        arguments = params.arguments
        tool_name = arguments["tool_name"]
        raw_tool_arguments = arguments.get("arguments", {})
        if tool_name not in SAFE_BROWSER_TOOLS:
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                "EOD browser tool is not in the safe allowlist",
                details={"tool_name": tool_name},
            )
        _validate_navigation(allowed_origin, tool_name, raw_tool_arguments)
        tool_arguments, screenshot_target = _prepare_tool_arguments(
            output_dir, tool_name, raw_tool_arguments
        )
        try:
            result = await browser.call_tool(tool_name, tool_arguments)
        except BridgeError:
            raise
        except Exception as exc:
            raise BridgeError(
                ErrorCode.INTERNAL_ERROR,
                "EOD browser call failed",
                retryable=True,
                details={"tool_name": tool_name, "reason": str(exc)},
            ) from exc
        header = success(
            request_context.request_id,
            {"tool_name": tool_name, "allowed_origin": allowed_origin},
        )
        envelope = types.TextContent(
            type="text",
            text=json.dumps(header.model_dump(mode="json", exclude_none=True), sort_keys=True),
        )
        inline_content = (
            _inline_screenshot_content(screenshot_target)
            if tool_name == "browser_take_screenshot" and not result.is_error
            else []
        )
        return types.CallToolResult(
            content=[envelope, *list(result.content), *inline_content],
            is_error=bool(result.is_error),
        )

    no_args = {"type": "object", "properties": {}, "additionalProperties": False}
    call_schema = {
        "type": "object",
        "properties": {
            "tool_name": {"type": "string", "enum": sorted(SAFE_BROWSER_TOOLS)},
            "arguments": {"type": "object", "default": {}},
        },
        "required": ["tool_name"],
        "additionalProperties": False,
    }
    return (
        RegisteredTool(
            types.Tool(
                name="eod_browser_status",
                description="Check the local Playwright MCP and EOD development health",
                inputSchema=no_args,
            ),
            status,
            "eod-browser",
        ),
        RegisteredTool(
            types.Tool(
                name="eod_browser_tools",
                description="List the safe Playwright tools exposed for EOD development",
                inputSchema=no_args,
            ),
            tools,
            "eod-browser",
        ),
        RegisteredTool(
            types.Tool(
                name="eod_browser_call",
                description="Call one safe Playwright tool against the EOD development UI on localhost:8766",
                inputSchema=call_schema,
            ),
            call,
            "eod-browser",
        ),
    )
