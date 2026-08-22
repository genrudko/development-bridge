from __future__ import annotations

from urllib.parse import quote

from mcp import types
from mcp.server.mcpserver.utilities.types import Image

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.api.schemas import IDENTIFIER_SCHEMA
from app.container import ApplicationContainer
from app.jobs import read_visual_artifact


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

    async def job_artifact_list(ctx, params, request_context):
        arguments = params.arguments
        artifacts = container.jobs.list_artifacts(
            repository(arguments), arguments["job_id"]
        )
        base = container.settings.server.endpoint.rstrip("/") + "/artifacts"
        prefix = "/".join(
            quote(arguments[key], safe="")
            for key in ("project_id", "repository_id", "job_id")
        )
        return to_mcp_result(
            success(
                request_context.request_id,
                {
                    "job_id": arguments["job_id"],
                    "artifacts": [
                        artifact.public_dict(
                            download_path=(
                                f"{base}/{prefix}/{quote(artifact.artifact_id, safe='')}"
                                if artifact.available
                                else None
                            )
                        )
                        for artifact in artifacts
                    ],
                },
            )
        )

    async def job_artifact_view(ctx, params, request_context):
        arguments = params.arguments
        artifact, path = container.jobs.artifact_file(
            repository(arguments), arguments["job_id"], arguments["artifact_id"]
        )
        image_bytes = read_visual_artifact(artifact, path)
        result = to_mcp_result(
            success(
                request_context.request_id,
                {
                    "job_id": arguments["job_id"],
                    "artifact": artifact.public_dict(),
                },
            )
        )
        image_format = {
            "image/png": "png",
            "image/jpeg": "jpeg",
            "image/webp": "webp",
        }[artifact.media_type]
        result.content.append(
            Image(data=image_bytes, format=image_format).to_image_content()
        )
        return result

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
                (
                    "job_artifact_list",
                    "List immutable artifacts captured for a job",
                    job_artifact_list,
                ),
            )
        ),
        (
            "job_artifact_view",
            "View an immutable image artifact through MCP",
            {
                **base_properties,
                "job_id": JOB_ID_SCHEMA,
                "artifact_id": IDENTIFIER_SCHEMA,
            },
            repository_required + ["job_id", "artifact_id"],
            job_artifact_view,
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
