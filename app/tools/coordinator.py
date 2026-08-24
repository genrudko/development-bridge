from __future__ import annotations

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.api.schemas import IDENTIFIER_SCHEMA
from app.coordinator.context import MAX_CONTEXT_CHARS, RouteContextStore, default_route_context_path
from app.container import ApplicationContainer
from app.tools.jobs import JOB_ID_SCHEMA

COORDINATOR_UI_URI = "ui://development-bridge/coordinator-x-v3.html"
COORDINATOR_UI_META = {
    "ui": {"resourceUri": COORDINATOR_UI_URI},
    "ui/resourceUri": COORDINATOR_UI_URI,
    "openai/outputTemplate": COORDINATOR_UI_URI,
}


def coordinator_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    route_contexts = RouteContextStore(default_route_context_path(container.route_registry.path))
    async def mount(ctx, params, request_context):
        requested_channel = (params.arguments or {}).get("channel_id", "coordinator")
        if isinstance(requested_channel, str) and requested_channel.startswith("cont_"):
            ack = await container.coordinator.model_ack(requested_channel)
            data = dict(ack)
            data["state"] = "acknowledged" if ack.get("acknowledged") else "not_found"
            return to_mcp_result(success(request_context.request_id, data))
        channel_id = container.coordinator.validate_channel(requested_channel)
        result = to_mcp_result(
            success(
                request_context.request_id,
                {
                    "channel_id": channel_id,
                    "state": "mounted",
                    "external_trigger_enabled": (
                        container.settings.server.x_trigger_token is not None
                    ),
                },
            )
        )
        trigger_path = container.settings.server.endpoint.rstrip("/") + "/x/coordinator/"
        public_base = container.settings.server.public_base_url
        trigger_url = (
            str(public_base).rstrip("/") + trigger_path if public_base is not None else trigger_path
        )
        result.structured_content = {
            "channel_id": channel_id,
            "trigger_url": trigger_url,
        }
        result.meta = dict(COORDINATOR_UI_META)
        return result

    async def takeover(ctx, params, request_context):
        arguments = params.arguments or {}
        route = container.route_registry.takeover(
            arguments["route_id"], arguments["url"], arguments.get("title"),
            make_default=arguments.get("make_default", True),
        )
        bootstrap = route_contexts.bootstrap(route)
        result = to_mcp_result(success(request_context.request_id, bootstrap))
        trigger_path = container.settings.server.endpoint.rstrip("/") + "/x/coordinator/"
        public_base = container.settings.server.public_base_url
        trigger_url = str(public_base).rstrip("/") + trigger_path if public_base is not None else trigger_path
        result.structured_content = {
            "channel_id": route["channel_id"],
            "trigger_url": trigger_url,
            "route_context": bootstrap["context"],
            "bootstrap_message": bootstrap["bootstrap_message"],
        }
        result.meta = dict(COORDINATOR_UI_META)
        return result

    async def context_get(ctx, params, request_context):
        arguments = params.arguments or {}
        route_id = container.route_registry.validate_route_id(arguments["route_id"])
        route = container.route_registry.resolve(route_id)
        if route is None:
            from app.api.errors import BridgeError, ErrorCode
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")
        return to_mcp_result(success(request_context.request_id, route_contexts.bootstrap(route)))

    async def context_update(ctx, params, request_context):
        arguments = params.arguments or {}
        route_id = container.route_registry.validate_route_id(arguments["route_id"])
        if container.route_registry.resolve(route_id) is None:
            from app.api.errors import BridgeError, ErrorCode
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")
        data = route_contexts.update(
            route_id, arguments["content"], expected_revision=arguments.get("expected_revision")
        )
        return to_mcp_result(success(request_context.request_id, data))

    async def continue_(ctx, params, request_context):
        arguments = params.arguments or {}
        data = await container.coordinator.arm(
            arguments["message"],
            channel_id=arguments.get("channel_id", "coordinator"),
            delay_seconds=arguments.get("delay_seconds", 12),
            conflict=arguments.get("conflict", "coalesce"),
        )
        return to_mcp_result(success(request_context.request_id, data))

    async def ack_continuation(ctx, params, request_context):
        data = await container.coordinator.model_ack(
            (params.arguments or {})["continuation_id"]
        )
        return to_mcp_result(success(request_context.request_id, data))

    async def wake_on_jobs(ctx, params, request_context):
        arguments = params.arguments or {}
        channel_id = container.coordinator.validate_channel(
            arguments.get("channel_id", "coordinator")
        )
        message = arguments.get("message")

        repository = container.projects.repositories.get(
            arguments["project_id"], arguments["repository_id"]
        )
        payload = {"channel_id": channel_id}
        if message is not None:
            payload["message"] = message
        data = await container.jobs.wake_on_jobs_durable(
            repository,
            tuple(arguments["job_ids"]),
            arguments.get("policy", "all_terminal"),
            "coordinator",
            payload,
        )
        data["channel_id"] = channel_id
        return to_mcp_result(success(request_context.request_id, data))

    common_meta = COORDINATOR_UI_META
    return (
        RegisteredTool(
            types.Tool(
                name="coordinator_x_mount",
                description="Mount the coordinator X wake listener; cached clients may pass an exact cont_... ID as channel_id to ACK only that continuation",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "channel_id": {
                            "type": "string",
                            "pattern": "^[A-Za-z0-9_-]{1,64}$",
                            "default": "coordinator",
                        }
                    },
                    "additionalProperties": False,
                },
                _meta=common_meta,
            ),
            mount,
            "coordinator-x",
        ),
        RegisteredTool(
            types.Tool(
                name="coordinator_route_takeover",
                description="Make this ChatGPT conversation the next generation of a logical route and mount its X listener",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "route_id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{0,30}$"},
                        "url": {"type": "string", "minLength": 1, "maxLength": 500},
                        "title": {"type": "string", "minLength": 1, "maxLength": 200},
                        "make_default": {"type": "boolean", "default": True},
                    },
                    "required": ["route_id", "url"],
                    "additionalProperties": False,
                },
                _meta=common_meta,
            ),
            takeover,
            "coordinator-x",
        ),
        RegisteredTool(
            types.Tool(
                name="coordinator_route_context_get",
                description="Read the durable canonical Route Context and bootstrap message for a logical route",
                inputSchema={
                    "type": "object",
                    "properties": {"route_id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{0,30}$"}},
                    "required": ["route_id"],
                    "additionalProperties": False,
                },
            ),
            context_get,
            "coordinator-x",
        ),
        RegisteredTool(
            types.Tool(
                name="coordinator_route_context_update",
                description="Replace the compact canonical Route Context checkpoint for a logical route",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "route_id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{0,30}$"},
                        "content": {"type": "string", "minLength": 1, "maxLength": MAX_CONTEXT_CHARS},
                        "expected_revision": {"type": "integer", "minimum": 0},
                    },
                    "required": ["route_id", "content"],
                    "additionalProperties": False,
                },
            ),
            context_update,
            "coordinator-x",
        ),
        RegisteredTool(
            types.Tool(
                name="coordinator_continue",
                description="Arm one bounded delayed X wake/checkpoint for an already mounted channel",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "channel_id": {
                            "type": "string",
                            "pattern": "^[A-Za-z0-9_-]{1,64}$",
                            "default": "coordinator",
                        },
                        "message": {"type": "string", "minLength": 1, "maxLength": 4000},
                        "delay_seconds": {
                            "type": "number", "minimum": 0, "maximum": 300,
                            "default": 12,
                        },
                        "conflict": {
                            "type": "string", "enum": ["coalesce", "reject"],
                            "default": "coalesce",
                        },
                    },
                    "required": ["message"],
                    "additionalProperties": False,
                },
            ),
            continue_,
            "coordinator-x",
        ),
        RegisteredTool(
            types.Tool(
                name="coordinator_ack",
                description=(
                    "Acknowledge a resilient coordinator continuation after a fresh model turn "
                    "starts; this cancels pending X retries and Telegram escalation. The response may "
                    "include batched_messages that must be processed in the same model turn."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "continuation_id": {
                            "type": "string",
                            "pattern": "^cont_[A-Za-z0-9_-]{5,75}$",
                        }
                    },
                    "required": ["continuation_id"],
                    "additionalProperties": False,
                },
            ),
            ack_continuation,
            "coordinator-x",
        ),
        RegisteredTool(
            types.Tool(
                name="coordinator_wake_on_jobs",
                description=(
                    "Event-driven resilient X continuation for durable jobs. Requires an active "
                    "coordinator_x_mount for the same channel. After jobs become terminal, delivery "
                    "keeps one active durable continuation_id per channel, batches concurrent terminal "
                    "groups without overwriting them, and deduplicates repeated events. Transport failures "
                    "may retry X up to 3 attempts; after successful ui/message transport ACK the continuation "
                    "is not redelivered, and Telegram escalation is reserved for missing model ACK. "
                    "Terminal groups are debounce-batched, successful Web turns are cooldown-gated, and "
                    "Browser Host rate-limit backoff suppresses new X claims. The pre-terminal job waiter is durable "
                    "and restored across Bridge restart."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": IDENTIFIER_SCHEMA,
                        "repository_id": IDENTIFIER_SCHEMA,
                        "job_ids": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 64,
                            "uniqueItems": True,
                            "items": JOB_ID_SCHEMA,
                        },
                        "channel_id": {
                            "type": "string",
                            "pattern": "^[A-Za-z0-9_-]{1,64}$",
                            "default": "coordinator",
                        },
                        "message": {
                            "type": "string", "minLength": 1, "maxLength": 200,
                            "description": "Short user-facing continuation status in the current conversation language."
                        },
                        "policy": {
                            "type": "string",
                            "enum": ["all_terminal", "failure_or_all_terminal"],
                            "default": "all_terminal",
                        },
                    },
                    "required": ["project_id", "repository_id", "job_ids"],
                    "additionalProperties": False,
                },
            ),
            wake_on_jobs,
            "coordinator-x",
        ),
    )
