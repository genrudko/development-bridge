from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.container import ApplicationContainer

_RESULTS: dict[str, dict[str, Any]] = {}
_TASKS: set[asyncio.Task[None]] = set()


def _capabilities(ctx) -> dict[str, Any]:
    capabilities = getattr(ctx.session, "client_capabilities", None)
    if capabilities is None:
        dumped = None
    elif hasattr(capabilities, "model_dump"):
        dumped = capabilities.model_dump(mode="json", by_alias=True)
    else:
        dumped = repr(capabilities)
    return {
        "protocol_version": ctx.protocol_version,
        "can_send_request": bool(ctx.session.can_send_request),
        "client_capabilities": dumped,
    }


def _message() -> list[types.SamplingMessage]:
    return [
        types.SamplingMessage(
            role="user",
            content=types.TextContent(
                type="text",
                text="Reply with exactly MCP_SAMPLING_OK and nothing else.",
            ),
        )
    ]


def _dump_result(result: Any) -> Any:
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json", by_alias=True)
    return repr(result)


async def _delayed_probe(session, probe_id: str, delay_seconds: float) -> None:
    await asyncio.sleep(delay_seconds)
    record = _RESULTS[probe_id]
    record["can_send_request_at_fire"] = bool(session.can_send_request)
    try:
        result = await session.create_message(messages=_message(), max_tokens=32)
    except Exception as exc:
        record.update(
            status="failed",
            error_type=type(exc).__name__,
            error=str(exc),
        )
    else:
        record.update(status="succeeded", result=_dump_result(result))


def probe_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    async def sampling_probe(ctx, params, request_context):
        arguments = params.arguments or {}
        mode = arguments.get("mode", "capabilities")
        delay_seconds = float(arguments.get("delay_seconds", 3.0))
        data = _capabilities(ctx)
        data["mode"] = mode

        if mode == "during_call":
            try:
                result = await ctx.session.create_message(
                    messages=_message(),
                    max_tokens=32,
                    related_request_id=ctx.request_id,
                )
            except Exception as exc:
                data.update(
                    status="failed",
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            else:
                data.update(status="succeeded", result=_dump_result(result))
        elif mode == "after_return":
            probe_id = f"probe_{uuid4().hex}"
            _RESULTS[probe_id] = {
                "probe_id": probe_id,
                "status": "pending",
                "delay_seconds": delay_seconds,
                **data,
            }
            task = asyncio.create_task(
                _delayed_probe(ctx.session, probe_id, delay_seconds),
                name=f"mcp-sampling-{probe_id}",
            )
            _TASKS.add(task)
            task.add_done_callback(_TASKS.discard)
            data.update(status="scheduled", probe_id=probe_id)
        else:
            data["status"] = "observed"

        return to_mcp_result(success(request_context.request_id, data))

    async def sampling_probe_status(ctx, params, request_context):
        probe_id = (params.arguments or {}).get("probe_id", "")
        record = _RESULTS.get(probe_id)
        data = record or {"probe_id": probe_id, "status": "not_found"}
        return to_mcp_result(success(request_context.request_id, data))

    return (
        RegisteredTool(
            definition=types.Tool(
                name="sampling_probe",
                description="Probe MCP client sampling and server-to-client back-channel behavior",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "enum": ["capabilities", "during_call", "after_return"],
                            "default": "capabilities",
                        },
                        "delay_seconds": {
                            "type": "number",
                            "minimum": 0.1,
                            "maximum": 30.0,
                            "default": 3.0,
                        },
                    },
                    "additionalProperties": False,
                },
            ),
            handler=sampling_probe,
            source="probe",
        ),
        RegisteredTool(
            definition=types.Tool(
                name="sampling_probe_status",
                description="Read the result of a delayed MCP sampling probe",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "probe_id": {"type": "string", "minLength": 1},
                    },
                    "required": ["probe_id"],
                    "additionalProperties": False,
                },
            ),
            handler=sampling_probe_status,
            source="probe",
        ),
    )
