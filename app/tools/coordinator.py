from __future__ import annotations

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.api.schemas import IDENTIFIER_SCHEMA
from app.container import ApplicationContainer
from app.tools.jobs import JOB_ID_SCHEMA

COORDINATOR_UI_URI = "ui://development-bridge/coordinator-x-v1.html"
COORDINATOR_UI_META = {
    "ui": {"resourceUri": COORDINATOR_UI_URI},
    "ui/resourceUri": COORDINATOR_UI_URI,
    "openai/outputTemplate": COORDINATOR_UI_URI,
}


def coordinator_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    async def mount(ctx, params, request_context):
        channel_id = container.coordinator.validate_channel(
            (params.arguments or {}).get("channel_id", "coordinator")
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
        }
        result.meta = dict(COORDINATOR_UI_META)
        return result

    async def takeover(ctx, params, request_context):
        arguments = params.arguments or {}
        route = container.route_registry.takeover(
            arguments["route_id"], arguments["url"], arguments.get("title"),
            make_default=arguments.get("make_default", True),
        )
        result = to_mcp_result(success(request_context.request_id, route))
        trigger_path = container.settings.server.endpoint.rstrip("/") + "/x/coordinator/"
        public_base = container.settings.server.public_base_url
        trigger_url = str(public_base).rstrip("/") + trigger_path if public_base is not None else trigger_path
        result.structured_content = {"channel_id": route["channel_id"], "trigger_url": trigger_url}
        result.meta = dict(COORDINATOR_UI_META)
        return result

    async def continue_(ctx, params, request_context):
        arguments = params.arguments or {}
        data = await container.coordinator.arm(
            arguments["message"],
            channel_id=arguments.get("channel_id", "coordinator"),
            delay_seconds=arguments.get("delay_seconds", 12),
            conflict=arguments.get("conflict", "coalesce"),
        )
        return to_mcp_result(success(request_context.request_id, data))

    async def wake_on_jobs(ctx, params, request_context):
        arguments = params.arguments or {}
        channel_id = container.coordinator.validate_channel(
            arguments.get("channel_id", "coordinator")
        )
        message = arguments.get("message")

        async def wake(jobs, reason):
            job_ids = ",".join(job.job_id for job in jobs)
            suffix = f"; message={message}" if message else ""
            await container.coordinator.arm(
                f"jobs={job_ids}; reason={reason}{suffix}",
                channel_id=channel_id,
                delay_seconds=0,
                conflict="coalesce",
            )

        repository = container.projects.repositories.get(
            arguments["project_id"], arguments["repository_id"]
        )
        data = await container.jobs.wake_on_jobs(
            repository,
            tuple(arguments["job_ids"]),
            arguments.get("policy", "all_terminal"),
            wake,
        )
        data["channel_id"] = channel_id
        return to_mcp_result(success(request_context.request_id, data))

    common_meta = COORDINATOR_UI_META
    return (
        RegisteredTool(
            types.Tool(
                name="coordinator_x_mount",
                description="Mount the coordinator X wake listener for this chat/channel before arming wakes",
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
                name="coordinator_wake_on_jobs",
                description=(
                    "Event-driven one-shot X wake for durable jobs. Requires an active "
                    "coordinator_x_mount for the same channel; end the model turn after "
                    "registering, then read job_status/job_output in the fresh turn. "
                    "Waiters are process-local and do not survive a Bridge restart."
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
                            "type": "string", "minLength": 1, "maxLength": 200
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
