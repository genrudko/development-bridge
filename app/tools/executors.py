from mcp import types

from app.api.errors import BridgeError, ErrorCode
from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.api.schemas import IDENTIFIER_SCHEMA
from app.container import ApplicationContainer
from app.executors import ExecutorName, ExecutorRequest, TaskKind
from app.settings import (
    AntigravityExecutorSettings,
    ClineExecutorSettings,
    OpenRouterExecutorSettings,
)

_MODEL_EXECUTORS = (ExecutorName.OPENROUTER, ExecutorName.CLINE)


def _configured_settings(
    container: ApplicationContainer, executor_name: ExecutorName | None
) -> AntigravityExecutorSettings | OpenRouterExecutorSettings | ClineExecutorSettings:
    executors = container.settings.executors
    if executor_name is ExecutorName.OPENROUTER:
        return executors.openrouter
    if executor_name is ExecutorName.CLINE:
        return executors.cline
    return executors.antigravity


def executor_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    def repository(arguments):
        return container.projects.repositories.get(arguments["project_id"], arguments["repository_id"])

    async def executor_status(ctx, params, request_context):
        data = await container.executors.status(repository(params.arguments))
        return to_mcp_result(success(request_context.request_id, data))

    async def executor_start(ctx, params, request_context):
        arguments = params.arguments
        executor_name = ExecutorName(arguments["executor"]) if arguments.get("executor") else None
        configured = _configured_settings(container, executor_name)
        model = arguments.get("model")
        if model is not None and executor_name not in _MODEL_EXECUTORS:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "model parameter is only supported for the openrouter and cline executors",
            )
        request = ExecutorRequest(
            task=arguments["task"], task_kind=TaskKind(arguments["task_kind"]),
            executor=executor_name,
            timeout_seconds=arguments.get("timeout_seconds", configured.task_timeout_seconds),
            output_limit_bytes=arguments.get("output_limit_bytes", configured.output_limit_bytes),
            idempotency_key=arguments.get("idempotency_key"),
            model=model,
            worktree_branch=arguments.get("worktree_branch"),
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
                "executor": {"type": "string", "enum": ["codex", "antigravity", "openrouter", "cline"]},
                "model": {"type": "string", "minLength": 1, "maxLength": 128},
                "worktree_branch": {"type": "string", "minLength": 1, "maxLength": 1024},
                "timeout_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 3600},
                "output_limit_bytes": {"type": "integer", "minimum": 1024, "maximum": 1048576},
                "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 128}},
                "required": ["project_id", "repository_id", "task", "task_kind"],
                "additionalProperties": False}), executor_start, "v1"),
    )
