from __future__ import annotations

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.api.schemas import IDENTIFIER_SCHEMA
from app.container import ApplicationContainer


JOB_ID_SCHEMA = {"type": "string", "pattern": "^job_[0-9a-f]{32}$"}


def job_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    def repository(arguments):
        return container.projects.repositories.get(
            arguments["project_id"], arguments["repository_id"]
        )

    async def task_list(ctx, params, request_context):
        profiles = container.jobs.list_tasks(repository(params.arguments))
        return to_mcp_result(
            success(
                request_context.request_id,
                {"tasks": [profile.public_dict() for profile in profiles]},
            )
        )

    async def task_start(ctx, params, request_context):
        arguments = params.arguments
        job = await container.jobs.start_task(
            repository(arguments),
            arguments["task_id"],
            request_context.request_id,
            idempotency_key=arguments.get("idempotency_key"),
        )
        return to_mcp_result(success(request_context.request_id, job.status_dict()))

    async def job_status(ctx, params, request_context):
        arguments = params.arguments
        job = container.jobs.status(repository(arguments), arguments["job_id"])
        return to_mcp_result(success(request_context.request_id, job.status_dict()))

    async def job_output(ctx, params, request_context):
        arguments = params.arguments
        job = container.jobs.output(repository(arguments), arguments["job_id"])
        return to_mcp_result(success(request_context.request_id, job.output_dict()))

    async def job_cancel(ctx, params, request_context):
        arguments = params.arguments
        job = await container.jobs.cancel(repository(arguments), arguments["job_id"])
        return to_mcp_result(success(request_context.request_id, job.status_dict()))

    base_properties = {
        "project_id": IDENTIFIER_SCHEMA,
        "repository_id": IDENTIFIER_SCHEMA,
    }
    repository_required = ["project_id", "repository_id"]
    definitions = (
        (
            "task_list",
            "List registered tasks for a repository",
            base_properties,
            repository_required,
            task_list,
        ),
        (
            "task_start",
            "Start a registered repository task",
            {
                **base_properties,
                "task_id": IDENTIFIER_SCHEMA,
                "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            repository_required + ["task_id"],
            task_start,
        ),
        *(
            (
                name,
                description,
                {**base_properties, "job_id": JOB_ID_SCHEMA},
                repository_required + ["job_id"],
                handler,
            )
            for name, description, handler in (
                ("job_status", "Show durable job status", job_status),
                ("job_output", "Read bounded accumulated job output", job_output),
                ("job_cancel", "Cancel a queued or running job", job_cancel),
            )
        ),
    )
    return tuple(
        RegisteredTool(
            types.Tool(
                name=name,
                description=description,
                inputSchema={
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            ),
            handler,
            "v1",
        )
        for name, description, properties, required, handler in definitions
    )
