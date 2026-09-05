from __future__ import annotations

from contextlib import suppress

from mcp import types

from app.api.errors import BridgeError, ErrorCode
from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.api.schemas import IDENTIFIER_SCHEMA
from app.container import ApplicationContainer
from app.coordinator.context import (
    MAX_CONTEXT_CHARS,
    RouteContextStore,
    default_route_context_path,
)
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


def _resolve_destination(container: ApplicationContainer, ctx, arguments: dict, *, bind: bool = True) -> dict:
    from app.api.errors import BridgeError, ErrorCode

    route_id = arguments.get("route_id")
    channel_id = arguments.get("channel_id")
    if route_id is not None:
        route_id = container.route_registry.validate_route_id(route_id)
        route = container.route_registry.resolve(route_id)
        if route is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")
        if not container.route_registry.is_bound(route):
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                f"Route '{route_id}' is unbound; bind a destination before mounting or waking",
                details={"route_id": route_id, "error_code": "ROUTE_UNBOUND"},
            )
        if channel_id is not None and channel_id != route["channel_id"]:
            raise BridgeError(ErrorCode.POLICY_VIOLATION, "route_id and channel_id refer to different destinations")
        binding = _route_binding(container, route)
        return _bind_session(container, ctx, binding) if bind else binding

    if channel_id is not None:
        channel = container.coordinator.validate_channel(channel_id)
        route = container.route_registry.wake_route_for_channel(channel)
        if route is None:
            binding = {"channel_id": channel, "route_state": "explicit"}
            return _bind_session(container, ctx, binding) if bind else binding
        resolved_logical = container.route_registry.resolve(route["route_id"])
        if resolved_logical is not None and not container.route_registry.is_bound(resolved_logical):
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                f"Route '{route['route_id']}' is unbound; bind a destination before mounting or waking",
                details={"route_id": route["route_id"], "error_code": "ROUTE_UNBOUND"},
            )
        if route.get("route_state") != "pending" and not container.route_registry.is_bound(route):
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                f"Route '{route['route_id']}' is unbound; bind a destination before mounting or waking",
                details={"route_id": route["route_id"], "error_code": "ROUTE_UNBOUND"},
            )
        binding = _route_binding(container, route, route_state=str(route.get("route_state", "active")))
        return _bind_session(container, ctx, binding) if bind else binding

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
        if not container.route_registry.is_bound(route):
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                f"Route '{bound_route}' is unbound; bind a destination before mounting or waking",
                details={"route_id": str(bound_route), "error_code": "ROUTE_UNBOUND"},
            )
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
        if binding.get("route_state") == "pending":
            if bound_generation is None:
                raise BridgeError(ErrorCode.POLICY_VIOLATION, "Pending route session has no generation")
            new_binding = _route_binding(container, route)
            return _bind_session(container, ctx, new_binding) if bind else new_binding
    return dict(binding)


def _resolve_mount_destination(container: ApplicationContainer, ctx, arguments: dict, *, bind: bool = True) -> dict:
    """Resolve the mount-only pending-generation exception without weakening wakes."""
    route_id = arguments.get("route_id")
    channel_id = arguments.get("channel_id")
    if route_id is not None or channel_id is None:
        return _resolve_destination(container, ctx, arguments, bind=bind)

    channel = container.coordinator.validate_channel(channel_id)
    route = container.route_registry.mount_route_for_channel(channel)
    if route is None:
        binding = {"channel_id": channel, "route_state": "explicit"}
        return _bind_session(container, ctx, binding) if bind else binding
    if route.get("route_state") == "active" and not container.route_registry.is_bound(route):
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            f"Route '{route['route_id']}' is unbound; bind a destination before mounting",
            details={"route_id": route["route_id"], "error_code": "ROUTE_UNBOUND"},
        )
    binding = _route_binding(container, route, route_state=str(route["route_state"]))
    return _bind_session(container, ctx, binding) if bind else binding


def coordinator_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    route_contexts = RouteContextStore(default_route_context_path(container.route_registry.path))

    async def mount(ctx, params, request_context):
        arguments = params.arguments or {}
        requested_channel = arguments.get("channel_id")
        if isinstance(requested_channel, str) and requested_channel.startswith("cont_"):
            ack = await container.coordinator.model_ack(requested_channel)
            data = dict(ack)
            data["state"] = "acknowledged" if ack.get("acknowledged") else "not_found"
            return to_mcp_result(success(request_context.request_id, data))
        destination = _resolve_mount_destination(container, ctx, arguments, bind=False)
        channel_id = str(destination["channel_id"])
        delivery = container.coordinator.issue_delivery_lease(
            channel_id,
            session_id=_session_id(ctx),
            route_id=(str(destination["route_id"]) if destination.get("route_id") is not None else None),
            generation=(int(destination["generation"]) if destination.get("generation") is not None else None),
        )
        binding = _bind_session(container, ctx, destination)
        if destination.get("route_id") is not None and destination.get("route_state") == "active":
            container.route_registry.request(str(destination["route_id"]))
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
        if container.route_control is not None and binding.get("route_id"):
            route_id = str(binding["route_id"])
            descriptor = container.route_control.issue_control_descriptor(route_id)
            pending_bind = container.route_control.pending_bind_descriptor(
                route_id, session_id=_session_id(ctx)
            )
            if pending_bind is not None:
                descriptor.update(pending_bind)
            result.meta["route_control"] = descriptor
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
        if container.route_control is not None:
            prepared = container.route_control.prepare_bind(
                route_id,
                session_id=session_id,
                allow_project_change=bool(arguments.get("allow_project_change", False)),
            )
        else:
            pending = container.route_registry.prepare_current_bind(
                route_id,
                session_id=session_id,
                allow_project_change=bool(arguments.get("allow_project_change", False)),
            )
            prepared = {
                "route_id": route_id,
                "state": "bind_pending",
                "generation": int(route.get("generation", 0)),
                "operation_id": pending["token"],
                "diagnostic_id": "bind-fallback",
                "operation_url": f"/x/route-control/bind/{pending['token']}",
            }
        safe_data = {
            "route_id": prepared["route_id"],
            "state": prepared["state"],
            "generation": prepared["generation"],
        }
        result = to_mcp_result(success(request_context.request_id, safe_data))
        result.structured_content = safe_data
        rc_meta = {
            "action": "bind",
            "route_id": prepared["route_id"],
            "operation_url": prepared["operation_url"],
            "operation_id": prepared["operation_id"],
            "diagnostic_id": prepared["diagnostic_id"],
            "nonce": prepared["operation_id"],
        }
        if container.route_control is not None:
            descriptor = container.route_control.issue_control_descriptor(prepared["route_id"])
            rc_meta["control_token"] = descriptor["control_token"]
            rc_meta["endpoints"] = descriptor["endpoints"]
        result.meta = {
            **COORDINATOR_UI_META,
            "route_control": rc_meta,
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
        return result

    async def rollover_prepare(ctx, params, request_context):
        arguments = params.arguments or {}
        route_id = container.route_registry.validate_route_id(arguments["route_id"])
        async with container.route_registry.route_lock(route_id):
            route = container.route_registry.resolve(route_id)
            if route is None:
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")
            if not container.route_registry.is_bound(route):
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    f"Route '{route_id}' is unbound; rollover cannot be prepared",
                    details={"route_id": route_id, "error_code": "ROUTE_UNBOUND"},
                )
            generation = int(route.get("generation", 0))
            coordinator_status = await container.coordinator.status(route["channel_id"])
            if coordinator_status.get("state") != "idle":
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    f"route coordinator is not idle: {coordinator_status.get('state')}",
                    retryable=True,
                )
            jobs = getattr(container, "jobs", None)
            if jobs is not None and await jobs.has_durable_waiters(
                handler_name="coordinator",
                payload_match={"route_id": route_id, "generation": generation},
            ):
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    "route has an active durable waiter; rollover cannot be prepared",
                    retryable=True,
                    details={"route_id": route_id, "error_code": "PENDING_WAITER"},
                )
            pending = container.route_registry.prepare_rollover(route_id)
        safe_data = {
            "route_id": route_id,
            "state": "prepared",
            "generation": int(route.get("generation", 0)),
            "target_generation": int(pending["target_generation"]),
            "channel_id": route["channel_id"],
        }
        result = to_mcp_result(success(request_context.request_id, safe_data))
        trigger_path = container.settings.server.endpoint.rstrip("/") + "/x/coordinator/"
        public_base = container.settings.server.public_base_url
        trigger_url = str(public_base).rstrip("/") + trigger_path if public_base is not None else trigger_path
        result.structured_content = {**safe_data, "trigger_url": trigger_url}
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
        routes = container.route_registry.list_safe_routes()
        return to_mcp_result(success(request_context.request_id, {"routes": routes}))

    async def route_control_status(ctx, params, request_context):
        arguments = params.arguments or {}
        route_id = container.route_registry.validate_route_id(arguments["route_id"])
        if container.route_control is None:
            from app.api.errors import BridgeError, ErrorCode
            raise BridgeError(ErrorCode.INTERNAL_ERROR, "Route control is not configured")
        data = container.route_control.safe_status(route_id)
        result = to_mcp_result(success(request_context.request_id, data))
        result.structured_content = dict(data)
        return result

    async def route_control_diagnostic(ctx, params, request_context):
        arguments = params.arguments or {}
        diag_id = str(arguments.get("diagnostic_id") or "").strip()
        if not diag_id:
            from app.api.errors import BridgeError, ErrorCode
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "diagnostic_id is required")
        if container.route_control is None:
            from app.api.errors import BridgeError, ErrorCode
            raise BridgeError(ErrorCode.INTERNAL_ERROR, "Route control is not configured")
        trace = container.route_control.trace_store.sanitized(diag_id)
        if trace is None:
            from app.api.errors import BridgeError, ErrorCode
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"diagnostic trace not found: {diag_id}")
        result = to_mcp_result(success(request_context.request_id, trace))
        result.structured_content = dict(trace)
        return result

    async def continue_(ctx, params, request_context):
        arguments = params.arguments or {}
        destination = _resolve_destination(container, ctx, arguments)
        route_id = destination.get("route_id")
        if route_id is not None:
            route_id_str = str(route_id)
            async with container.route_registry.route_lock(route_id_str):
                route = container.route_registry.require_wakeable_route(
                    route_id_str,
                    expected_generation=int(destination.get("generation", 0)),
                    expected_channel=str(destination.get("channel_id")),
                )
                channel_id = str(route["channel_id"])
                data = await container.coordinator.arm(
                    arguments["message"],
                    channel_id=channel_id,
                    delay_seconds=arguments.get("delay_seconds", 12),
                    conflict=arguments.get("conflict", "coalesce"),
                )
        else:
            channel_id = str(destination["channel_id"])
            data = await container.coordinator.arm(
                arguments["message"],
                channel_id=channel_id,
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
        route_id = destination.get("route_id")
        if route_id is not None:
            route_id_str = str(route_id)
            async with container.route_registry.route_lock(route_id_str):
                route = container.route_registry.require_wakeable_route(
                    route_id_str,
                    expected_generation=int(destination.get("generation", 0)),
                    expected_channel=str(destination.get("channel_id")),
                )
                gen = int(route["generation"])
                chan = str(route["channel_id"])
                payload = {
                    "route_id": route_id_str,
                    "generation": gen,
                    "channel_id": chan,
                }
                if message is not None:
                    payload["message"] = message
                data = await container.jobs.wake_on_jobs_durable(
                    repository,
                    tuple(arguments["job_ids"]),
                    arguments.get("policy", "all_terminal"),
                    "coordinator",
                    payload,
                )
                data["channel_id"] = chan
                data["route_id"] = route_id_str
        else:
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
        result = to_mcp_result(success(request_context.request_id, data))
        return result

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
        route_id = destination.get("route_id")
        if route_id is not None:
            route_id_str = str(route_id)
            async with container.route_registry.route_lock(route_id_str):
                try:
                    route = container.route_registry.require_wakeable_route(
                        route_id_str,
                        expected_generation=int(destination.get("generation", 0)),
                        expected_channel=str(destination.get("channel_id")),
                    )
                except BridgeError:
                    with suppress(Exception):
                        await container.jobs.cancel(repository, job.job_id)
                    raise
                gen = int(route["generation"])
                chan = str(route["channel_id"])
                payload = {
                    "route_id": route_id_str,
                    "generation": gen,
                    "channel_id": chan,
                }
                if arguments.get("message") is not None:
                    payload["message"] = arguments["message"]
                try:
                    waiter = await container.jobs.wake_on_jobs_durable(
                        repository, (job.job_id,), arguments.get("policy", "all_terminal"), "coordinator", payload
                    )
                except Exception:
                    with suppress(Exception):
                        await container.jobs.cancel(repository, job.job_id)
                    raise
                response = {**job.status_dict(), **waiter, "channel_id": chan, "route_id": route_id_str}
        else:
            payload = {"channel_id": channel_id}
            if arguments.get("message") is not None:
                payload["message"] = arguments["message"]
            try:
                waiter = await container.jobs.wake_on_jobs_durable(
                    repository, (job.job_id,), arguments.get("policy", "all_terminal"), "coordinator", payload
                )
            except Exception:
                with suppress(Exception):
                    await container.jobs.cancel(repository, job.job_id)
                raise
            response = {**job.status_dict(), **waiter, "channel_id": channel_id}
        result = to_mcp_result(success(request_context.request_id, response))
        return result



    common_meta = COORDINATOR_UI_META
    return (
        RegisteredTool(
            types.Tool(
                name="coordinator_x_mount",
                description="Mount the single persistent coordinator MCP App for this chat and bind its X wake listener to an existing registered logical route (e.g. bridge, eod, ad5xwork) or channel. Mount once per chat; status and wake tools are widgetless and do not require remounting. Cached clients may pass an exact cont_... ID as channel_id to ACK only that continuation",
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
                description="Bind an existing logical route to this exact physical ChatGPT conversation through the OOB bind-card/openExternal flow. Invoke this session-bound tool directly, not through bridge_call; physical ChatGPT URLs, IDs, sessions, and control tokens stay outside model-visible chat. Cross-project changes fail closed unless allow_project_change=true explicitly authorizes this one migration.",
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
                name="coordinator_route_control_status",
                description="Read-only widgetless logical status for a registered coordinator route (generation, binding state, pending wake counts, last operation) without physical chat identity or rendering another coordinator card",
                inputSchema={
                    "type": "object",
                    "properties": {"route_id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{0,30}$"}},
                    "required": ["route_id"],
                    "additionalProperties": False,
                },
            ),
            route_control_status,
            "coordinator-x",
        ),
        RegisteredTool(
            types.Tool(
                name="coordinator_route_control_diagnostic",
                description="Read-only sanitized diagnostic trace for a route-control operation; never returns raw chat identity, tokens, or URLs",
                inputSchema={
                    "type": "object",
                    "properties": {"diagnostic_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,64}$"}},
                    "required": ["diagnostic_id"],
                    "additionalProperties": False,
                },
            ),
            route_control_diagnostic,
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
                    "Event-driven resilient X continuation for durable jobs. Mount coordinator_x_mount once for the chat; "
                    "this widgetless call uses the existing destination binding and does not render a new coordinator MCP App. "
                    "After jobs become terminal, delivery "
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
            ),
            wake_on_jobs,
            "coordinator-x",
        ),
        RegisteredTool(
            types.Tool(
                name="coordinator_exec_and_wake",
                description="Queue one durable repository execution and arm its coordinator waiter without rendering a new coordinator MCP App; mount coordinator_x_mount once for the chat first. Cancels the new job if waiter registration fails.",
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
            ),
            exec_and_wake,
            "coordinator-x",
        ),
    )
