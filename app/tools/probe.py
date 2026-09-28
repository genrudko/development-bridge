from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from mcp import types
from mcp.server.subscriptions import InMemorySubscriptionBus, ToolsListChanged

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.container import ApplicationContainer

_RESULTS: dict[str, dict[str, Any]] = {}
_TASKS: set[asyncio.Task[None]] = set()
_TOOLS_LIST_COUNT = 0
_RESOURCES_LIST_COUNT = 0
_RESOURCES_READ_COUNT = 0
_UI_CONNECTED_COUNT = 0
_UI_SEND_ATTEMPT_COUNT = 0
_UI_SEND_SUCCESS_COUNT = 0
_UI_SEND_ERROR_COUNT = 0
_SUBSCRIPTION_BUS = InMemorySubscriptionBus()

def subscription_bus():
    return _SUBSCRIPTION_BUS

def subscription_listener_count() -> int:
    return len(_SUBSCRIPTION_BUS._listeners)

def note_tools_list() -> None:
    global _TOOLS_LIST_COUNT
    _TOOLS_LIST_COUNT += 1

def note_resources_list() -> None:
    global _RESOURCES_LIST_COUNT
    _RESOURCES_LIST_COUNT += 1

def note_resources_read() -> None:
    global _RESOURCES_READ_COUNT
    _RESOURCES_READ_COUNT += 1


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
        "tools_list_count": _TOOLS_LIST_COUNT,
        "resources_list_count": _RESOURCES_LIST_COUNT,
        "resources_read_count": _RESOURCES_READ_COUNT,
        "ui_connected_count": _UI_CONNECTED_COUNT,
        "ui_send_attempt_count": _UI_SEND_ATTEMPT_COUNT,
        "ui_send_success_count": _UI_SEND_SUCCESS_COUNT,
        "ui_send_error_count": _UI_SEND_ERROR_COUNT,
        "subscription_listeners": subscription_listener_count(),
        "has_standalone_channel": ctx.session._connection.has_standalone_channel,
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
    record["tools_list_count_before"] = _TOOLS_LIST_COUNT
    record["subscription_listeners_before"] = subscription_listener_count()
    try:
        await _SUBSCRIPTION_BUS.publish(ToolsListChanged())
    except Exception as exc:
        record.update(status="failed", error_type=type(exc).__name__, error=str(exc))
    else:
        record.update(status="notification_sent")
    await asyncio.sleep(1.0)
    record["tools_list_count_after"] = _TOOLS_LIST_COUNT
    record["subscription_listeners_after"] = subscription_listener_count()


def probe_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    async def sampling_probe(ctx, params, request_context):
        arguments = params.arguments or {}
        mode = arguments.get("mode", "capabilities")
        delay_seconds = float(arguments.get("delay_seconds", 3.0))
        data = _capabilities(ctx)
        data["mode"] = mode

        if mode == "during_call":
            data["tools_list_count_before"] = _TOOLS_LIST_COUNT
            data["subscription_listeners_before"] = subscription_listener_count()
            try:
                await _SUBSCRIPTION_BUS.publish(ToolsListChanged())
            except Exception as exc:
                data.update(status="failed", error_type=type(exc).__name__, error=str(exc))
            else:
                data.update(status="notification_sent")
            await asyncio.sleep(1.0)
            data["tools_list_count_after"] = _TOOLS_LIST_COUNT
            data["subscription_listeners_after"] = subscription_listener_count()
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

        result = to_mcp_result(success(request_context.request_id, data))
        return result.model_copy(update={"structured_content": {"probe": data}, "meta": {"ui": {"resourceUri": "ui://x-test/external-trigger-v1.html"}, "ui/resourceUri": "ui://x-test/external-trigger-v1.html", "openai/outputTemplate": "ui://x-test/external-trigger-v1.html"}})

    async def sampling_probe_status(ctx, params, request_context):
        global _UI_CONNECTED_COUNT, _UI_SEND_ATTEMPT_COUNT, _UI_SEND_SUCCESS_COUNT, _UI_SEND_ERROR_COUNT
        probe_id = (params.arguments or {}).get("probe_id", "")
        if probe_id == "ui-telemetry:connected": _UI_CONNECTED_COUNT += 1
        elif probe_id == "ui-telemetry:send-attempt": _UI_SEND_ATTEMPT_COUNT += 1
        elif probe_id == "ui-telemetry:send-success": _UI_SEND_SUCCESS_COUNT += 1
        elif probe_id == "ui-telemetry:send-error": _UI_SEND_ERROR_COUNT += 1
        if probe_id.startswith("ui-telemetry:"):
            data = {"probe_id": probe_id, "status": "telemetry_recorded"}
        else:
            record = _RESULTS.get(probe_id); data = record or {"probe_id": probe_id, "status": "not_found"}
        return to_mcp_result(success(request_context.request_id, data))

    return (
        RegisteredTool(
            definition=types.Tool(
                name="external_trigger_probe",
                description="Mount the one-shot externally triggered MCP App probe",
                _meta={"ui": {"resourceUri": "ui://x-test/external-trigger-v1.html"}, "ui/resourceUri": "ui://x-test/external-trigger-v1.html", "openai/outputTemplate": "ui://x-test/external-trigger-v1.html"},
                inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
            ),
            handler=sampling_probe,
            source="probe",
        ),
        RegisteredTool(
            definition=types.Tool(
                name="sampling_probe",
                description="Probe MCP client sampling and server-to-client back-channel behavior",
                _meta={"ui": {"resourceUri": "ui://x-test/external-trigger-v1.html"}, "ui/resourceUri": "ui://x-test/external-trigger-v1.html", "openai/outputTemplate": "ui://x-test/external-trigger-v1.html"},
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
