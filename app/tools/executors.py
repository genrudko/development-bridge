from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.api.schemas import IDENTIFIER_SCHEMA
from app.container import ApplicationContainer
from app.executors import ExecutorName, ExecutorRequest, TaskKind


def executor_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    def repository(arguments):
        return container.projects.repositories.get(arguments["project_id"], arguments["repository_id"])

    async def executor_status(ctx, params, request_context):
        data = await container.executors.status(repository(params.arguments))
        return to_mcp_result(success(request_context.request_id, data))

    async def executor_start(ctx, params, request_context):
        arguments = params.arguments
        configured = container.settings.executors.antigravity
        request = ExecutorRequest(
            task=arguments["task"], task_kind=TaskKind(arguments["task_kind"]),
            executor=ExecutorName(arguments["executor"]) if arguments.get("executor") else None,
            timeout_seconds=arguments.get("timeout_seconds", configured.task_timeout_seconds),
            output_limit_bytes=arguments.get("output_limit_bytes", configured.output_limit_bytes),
            idempotency_key=arguments.get("idempotency_key"),
        )
        job = await container.executors.start(repository(arguments), request, request_context.request_id)
        return to_mcp_result(success(request_context.request_id, job.status_dict()))

    base = {"project_id": IDENTIFIER_SCHEMA, "repository_id": IDENTIFIER_SCHEMA}
    return (
        RegisteredTool(types.Tool(name="executor_status",
            description="Report normalized repository-scoped executor availability and quota state",
            inputSchema={"type": "object", "properties": base,
                         "required": ["project_id", "repository_id"], "additionalProperties": False}),
            executor_status, "v1"),
        RegisteredTool(types.Tool(name="executor_start",
            description="Select an executor and submit one bounded task to the durable job engine",
            inputSchema={"type": "object", "properties": {**base,
                "task": {"type": "string", "minLength": 1, "maxLength": 65536},
                "task_kind": {"type": "string", "enum": ["implementation", "review", "other"]},
                "executor": {"type": "string", "enum": ["codex", "antigravity"]},
                "timeout_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 3600},
                "output_limit_bytes": {"type": "integer", "minimum": 1024, "maximum": 1048576},
                "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 128}},
                "required": ["project_id", "repository_id", "task", "task_kind"],
                "additionalProperties": False}), executor_start, "v1"),
    )
