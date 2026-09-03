from __future__ import annotations

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.api.schemas import IDENTIFIER_SCHEMA
from app.coordinator.context import MAX_CONTEXT_CHARS, RouteContextStore, default_route_context_path
from app.container import ApplicationContainer
from app.settings import ArtifactSettings
from app.tools.jobs import JOB_ID_SCHEMA

COORDINATOR_UI_URI = "ui://development-bridge/coordinator-x-v5.html"
COORDINATOR_UI_ALIASES = (
    "ui://development-bridge/coordinator-x-v4.html",
    "ui://development-bridge/coordinator-x-v3.html",
)
COORDINATOR_UI_URIS = (COORDINATOR_UI_URI, *COORDINATOR_UI_ALIASES)
COORDINATOR_UI_META = {
    "ui": {"resourceUri": COORDINATOR_UI_URI},
    "ui/resourceUri": COORDINATOR_UI_URI,
    "openai/outputTemplate": COORDINATOR_UI_URI,
}


def _session_id(ctx) -> str | None:
    session = getattr(ctx, "session", None)
    connection = getattr(session, "_connection", None)
    value = getattr(connection, "session_id", None)
    return str(value) if value else None


def _route_binding(container: ApplicationContainer, route: dict, *, route_state: str = "active") -> dict:
    return {
        "route_id": route["route_id"],
        "channel_id": route["channel_id"],
        "generation": int(route.get("generation", 0)),
        "route_state": route_state,
    }


def _bind_session(container: ApplicationContainer, ctx, binding: dict) -> dict:
    session_id = _session_id(ctx)
    if session_id is None:
        return binding
    container.coordinator.bind_session(
        session_id,
        binding["channel_id"],
        route_id=binding.get("route_id"),
        generation=binding.get("generation"),
        route_state=binding.get("route_state"),
    )
    return binding


def _resolve_destination(container: ApplicationContainer, ctx, arguments: dict) -> dict:
    from app.api.errors import BridgeError, ErrorCode

    route_id = arguments.get("route_id")
    channel_id = arguments.get("channel_id")
    if route_id is not None:
        route_id = container.route_registry.validate_route_id(route_id)
        route = container.route_registry.resolve(route_id)
        if route is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")
        if channel_id is not None and channel_id != route["channel_id"]:
            raise BridgeError(ErrorCode.POLICY_VIOLATION, "route_id and channel_id refer to different destinations")
        return _bind_session(container, ctx, _route_binding(container, route))

    if channel_id is not None:
        channel = container.coordinator.validate_channel(channel_id)
        route = container.route_registry.route_for_channel(channel)
        if route is None:
            return _bind_session(container, ctx, {"channel_id": channel, "route_state": "explicit"})
        binding = _route_binding(container, route, route_state=str(route.get("route_state", "active")))
        return _bind_session(container, ctx, binding)

    binding = container.coordinator.session_binding(_session_id(ctx))
    if binding is None:
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "Coordinator destination is not bound to this MCP session; call coordinator_x_mount with route_id or channel_id first",
        )
    bound_route = binding.get("route_id")
    if bound_route is not None:
        route = container.route_registry.resolve(str(bound_route))
        if route is None:
            raise BridgeError(ErrorCode.POLICY_VIOLATION, "Bound logical route no longer exists")
        bound_generation = binding.get("generation")
        current_generation = int(route.get("generation", 0))
        if bound_generation is not None and int(bound_generation) != current_generation:
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                "This physical chat is bound to a stale route generation; remount or use the current successor chat",
                retryable=True,
                details={
                    "route_id": str(bound_route),
                    "bound_generation": int(bound_generation),
                    "current_generation": current_generation,
                    "current_channel_id": str(route["channel_id"]),
                },
            )
        if str(binding.get("channel_id")) != str(route["channel_id"]):
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                "This physical chat channel is stale for the bound logical route",
                retryable=True,
            )
    return dict(binding)


def coordinator_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    route_contexts = RouteContextStore(default_route_context_path(container.route_registry.path))

    def attach_coordinator_ui(result, ctx, binding: dict):
        channel_id = str(binding["channel_id"])
        if binding.get("route_id") is not None and binding.get("route_state") == "active":
            container.route_registry.request(str(binding["route_id"]))
        delivery = container.coordinator.issue_delivery_lease(
            channel_id,
            session_id=_session_id(ctx),
            route_id=(str(binding["route_id"]) if binding.get("route_id") is not None else None),
            generation=(int(binding["generation"]) if binding.get("generation") is not None else None),
        )
        trigger_path = container.settings.server.endpoint.rstrip("/") + "/x/coordinator/"
        public_base = container.settings.server.public_base_url
        trigger_url = (
            str(public_base).rstrip("/") + trigger_path if public_base is not None else trigger_path
        )
        result.structured_content = {
            "channel_id": channel_id,
            "trigger_url": trigger_url,
            "delivery_lease": delivery["lease_id"],
            **(
                {
                    "route_id": binding["route_id"],
                    "generation": binding.get("generation"),
                    "route_state": binding.get("route_state"),
                }
                if binding.get("route_id") is not None
                else {}
            ),
        }
        result.meta = dict(COORDINATOR_UI_META)
        return result
    async def mount(ctx, params, request_context):
        arguments = params.arguments or {}
        requested_channel = arguments.get("channel_id")
        if isinstance(requested_channel, str) and requested_channel.startswith("cont_"):
            ack = await container.coordinator.model_ack(requested_channel)
            data = dict(ack)
            data["state"] = "acknowledged" if ack.get("acknowledged") else "not_found"
            return to_mcp_result(success(request_context.request_id, data))
        binding = _resolve_destination(container, ctx, arguments)
        channel_id = str(binding["channel_id"])
        if binding.get("route_id") is not None and binding.get("route_state") == "active":
            container.route_registry.request(str(binding["route_id"]))
        delivery = container.coordinator.issue_delivery_lease(
            channel_id,
            session_id=_session_id(ctx),
            route_id=(str(binding["route_id"]) if binding.get("route_id") is not None else None),
            generation=(int(binding["generation"]) if binding.get("generation") is not None else None),
        )
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
            "delivery_lease": delivery["lease_id"],
            **({"route_id": binding["route_id"], "generation": binding.get("generation"), "route_state": binding.get("route_state")} if binding.get("route_id") is not None else {}),
        }
        result.meta = dict(COORDINATOR_UI_META)
        return result

    async def bind_current(ctx, params, request_context):
        from app.api.errors import BridgeError, ErrorCode

        arguments = params.arguments or {}
        route_id = container.route_registry.validate_route_id(arguments["route_id"])
        session_id = _session_id(ctx)
        route = container.route_registry.resolve(route_id)
        if route is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")
        if session_id is not None:
            container.coordinator.unbind_session(session_id)
        binding = _route_binding(container, route, route_state="discovery")
        pending = container.route_registry.prepare_current_bind(
            route_id,
            session_id=session_id,
            allow_project_change=bool(arguments.get("allow_project_change", False)),
        )
        result = to_mcp_result(success(request_context.request_id, {
            "route_id": route_id,
            "state": "discovery_prepared",
        }))
        result = attach_coordinator_ui(result, ctx, binding)
        result.structured_content["route_discovery"] = {
            "route_id": route_id,
            "token": pending["token"],
            "marker": pending["marker"],
        }
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

    async def rollover_prepare(ctx, params, request_context):
        arguments = params.arguments or {}
        route_id = container.route_registry.validate_route_id(arguments["route_id"])
        route = container.route_registry.resolve(route_id)
        if route is None:
            from app.api.errors import BridgeError, ErrorCode
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")
        coordinator_status = await container.coordinator.status(route["channel_id"])
        if coordinator_status.get("state") != "idle":
            from app.api.errors import BridgeError, ErrorCode
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                f"route coordinator is not idle: {coordinator_status.get('state')}",
                retryable=True,
            )
        pending = container.route_registry.prepare_rollover(route_id)
        result = to_mcp_result(success(request_context.request_id, {"route": route, "rollover": pending, "state": "prepared"}))
        trigger_path = container.settings.server.endpoint.rstrip("/") + "/x/coordinator/"
        public_base = container.settings.server.public_base_url
        trigger_url = str(public_base).rstrip("/") + trigger_path if public_base is not None else trigger_path
        result.structured_content = {"channel_id": route["channel_id"], "trigger_url": trigger_url, "rollover": pending}
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

    async def route_list(ctx, params, request_context):
        routes = [
            {
                "route_id": item["route_id"],
                "title": item.get("title") or item["route_id"],
                "project_id": item.get("project_id"),
                "channel_id": item.get("channel_id"),
                "generation": int(item.get("generation", 0)),
                "default": bool(item.get("default", False)),
            }
            for item in container.route_registry.list_routes()
        ]
        return to_mcp_result(success(request_context.request_id, {"routes": routes}))

    async def continue_(ctx, params, request_context):
        arguments = params.arguments or {}
        destination = _resolve_destination(container, ctx, arguments)
        data = await container.coordinator.arm(
            arguments["message"],
            channel_id=str(destination["channel_id"]),
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
        destination = _resolve_destination(container, ctx, arguments)
        channel_id = str(destination["channel_id"])
        message = arguments.get("message")

        repository = container.projects.repositories.get(
            arguments["project_id"], arguments["repository_id"]
        )
        payload = ({"route_id": str(destination["route_id"])} if destination.get("route_id") is not None else {"channel_id": channel_id})
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
        if destination.get("route_id") is not None:
            data["route_id"] = destination["route_id"]
        result = to_mcp_result(success(request_context.request_id, data))
        return attach_coordinator_ui(result, ctx, destination)

    async def exec_and_wake(ctx, params, request_context):
        arguments = params.arguments or {}
        destination = _resolve_destination(container, ctx, arguments)
        channel_id = str(destination["channel_id"])
        repository = container.projects.repositories.get(arguments["project_id"], arguments["repository_id"])
        job = await container.jobs.start_execution(
            repository, arguments["executable"], arguments.get("arguments", []), request_context.request_id,
            timeout_seconds=arguments.get("timeout_seconds", 300),
            output_limit_bytes=arguments.get("output_limit_bytes", 262_144),
            artifacts=arguments.get("artifacts", []), stdin=arguments.get("stdin"),
            idempotency_key=arguments.get("idempotency_key"),
        )
        payload = ({"route_id": str(destination["route_id"])} if destination.get("route_id") is not None else {"channel_id": channel_id})
        if arguments.get("message") is not None:
            payload["message"] = arguments["message"]
        try:
            waiter = await container.jobs.wake_on_jobs_durable(
                repository, (job.job_id,), arguments.get("policy", "all_terminal"), "coordinator", payload
            )
        except Exception:
            try:
                await container.jobs.cancel(repository, job.job_id)
            except Exception:
                pass
            raise
        response = {**job.status_dict(), **waiter, "channel_id": channel_id}
        if destination.get("route_id") is not None:
            response["route_id"] = destination["route_id"]
        result = to_mcp_result(success(request_context.request_id, response))
        return attach_coordinator_ui(result, ctx, destination)

    common_meta = COORDINATOR_UI_META
    return (
        RegisteredTool(
            types.Tool(
                name="coordinator_x_mount",
                description="Mount the coordinator X wake listener for an existing registered logical route (e.g. bridge, eod, ad5xwork) or channel; ordinary workers mount existing routes here without asking the owner for URLs; cached clients may pass an exact cont_... ID as channel_id to ACK only that continuation",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "route_id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{0,30}$"},
                        "channel_id": {
                            "type": "string",
                            "pattern": "^[A-Za-z0-9_-]{1,64}$",
                        },
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
                name="coordinator_route_bind_current",
                description="Bind an existing logical route to this exact physical ChatGPT conversation without asking the owner for a URL; by default it fails closed across projects, while explicit allow_project_change=true authorizes this one marker-verified route migration",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "route_id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{0,30}$"},
                        "allow_project_change": {"type": "boolean", "default": False},
                    },
                    "required": ["route_id"],
                    "additionalProperties": False,
                },
                _meta=common_meta,
            ),
            bind_current,
            "coordinator-x",
        ),
        RegisteredTool(
            types.Tool(
                name="coordinator_route_takeover",
                description="Exceptional/manual route migration only: make this ChatGPT conversation the next generation of a logical route within the same project or bootstrap a new route; ordinary workers must mount existing routes with coordinator_x_mount and never call takeover to start ordinary work",
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
                name="coordinator_route_list",
                description="List registered coordinator logical routes and metadata without changing session binding or default route",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
            route_list,
            "coordinator-x",
        ),
        RegisteredTool(
            types.Tool(
                name="coordinator_route_rollover_prepare",
                description=(
                    "Prepare fail-safe automatic physical-chat rollover without changing the active route; "
                    "Browser Host creates and verifies the successor before committing it."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {"route_id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{0,30}$"}},
                    "required": ["route_id"],
                    "additionalProperties": False,
                },
                _meta=common_meta,
            ),
            rollover_prepare,
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
                        "route_id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{0,30}$"},
                        "channel_id": {
                            "type": "string",
                            "pattern": "^[A-Za-z0-9_-]{1,64}$",
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
                    "Event-driven resilient X continuation for durable jobs. With an explicit route/channel, "
                    "the call renders/refreshes the coordinator MCP App; otherwise coordinator_x_mount supplies "
                    "the existing destination binding. After jobs become terminal, delivery "
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
                        "route_id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{0,30}$"},
                        "channel_id": {
                            "type": "string",
                            "pattern": "^[A-Za-z0-9_-]{1,64}$",
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
                _meta=common_meta,
            ),
            wake_on_jobs,
            "coordinator-x",
        ),
        RegisteredTool(
            types.Tool(
                name="coordinator_exec_and_wake",
                description="Queue one durable repository execution, arm its coordinator waiter, and render/refresh the coordinator MCP App in the same request; cancels the new job if waiter registration fails.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": IDENTIFIER_SCHEMA, "repository_id": IDENTIFIER_SCHEMA,
                        "executable": {"type": "string", "minLength": 1, "maxLength": 4096},
                        "arguments": {"type": "array", "maxItems": 256, "items": {"type": "string", "maxLength": 4096}, "default": []},
                        "timeout_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 3600, "default": 300},
                        "output_limit_bytes": {"type": "integer", "minimum": 1024, "maximum": 1048576, "default": 262144},
                        "artifacts": {"type": "array", "maxItems": 32, "items": ArtifactSettings.model_json_schema(), "default": []},
                        "stdin": {"type": "string", "maxLength": 1048576},
                        "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 128},
                        "route_id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{0,30}$"},
                        "channel_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,64}$"},
                        "message": {"type": "string", "minLength": 1, "maxLength": 200},
                        "policy": {"type": "string", "enum": ["all_terminal", "failure_or_all_terminal"], "default": "all_terminal"},
                    },
                    "required": ["project_id", "repository_id", "executable"],
                    "additionalProperties": False,
                },
                _meta=common_meta,
            ),
            exec_and_wake,
            "coordinator-x",
        ),
    )
