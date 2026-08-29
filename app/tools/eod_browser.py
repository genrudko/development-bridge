from __future__ import annotations

import asyncio
import json
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


async def _list_upstream(url: str):
    async with sse_client(url, timeout=5, sse_read_timeout=20) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.list_tools()


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


async def _ensure_upstream(url: str, launcher):
    try:
        return await _list_upstream(url)
    except Exception:
        if launcher is None:
            raise
        await _run_launcher(launcher)
        await asyncio.sleep(0.25)
        return await _list_upstream(url)


async def _call_upstream(url: str, tool_name: str, arguments: dict):
    async with sse_client(url, timeout=5, sse_read_timeout=90) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(
                tool_name,
                arguments,
                read_timeout_seconds=90,
            )


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

    async def status(ctx, params, request_context):
        try:
            upstream, health = await asyncio.gather(
                _ensure_upstream(upstream_url, launcher),
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
            upstream = await _ensure_upstream(upstream_url, launcher)
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
        tool_arguments = arguments.get("arguments", {})
        if tool_name not in SAFE_BROWSER_TOOLS:
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                "EOD browser tool is not in the safe allowlist",
                details={"tool_name": tool_name},
            )
        _validate_navigation(allowed_origin, tool_name, tool_arguments)
        try:
            try:
                await _ensure_upstream(upstream_url, launcher)
            except Exception as exc:
                raise RuntimeError(f"EOD browser startup failed: {exc}") from exc
            result = await _call_upstream(upstream_url, tool_name, tool_arguments)
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
        return types.CallToolResult(
            content=[envelope, *list(result.content)],
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
