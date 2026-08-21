from __future__ import annotations

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.api.schemas import IDENTIFIER_SCHEMA
from app.container import ApplicationContainer


def git_read_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    def repository(arguments):
        return container.projects.repositories.get(
            arguments["project_id"], arguments["repository_id"]
        )

    async def git_log(ctx, params, request_context):
        arguments = params.arguments
        result = await container.git.log(
            repository(arguments),
            revision=arguments.get("revision", "HEAD"),
            max_count=arguments.get("max_count", container.git.DEFAULT_LOG_COUNT),
        )
        return to_mcp_result(success(request_context.request_id, result.as_dict()))

    async def git_show(ctx, params, request_context):
        arguments = params.arguments
        result = await container.git.show(repository(arguments), arguments["revision"])
        return to_mcp_result(success(request_context.request_id, result.as_dict()))

    async def git_diff(ctx, params, request_context):
        arguments = params.arguments
        result = await container.git.diff(
            repository(arguments),
            mode=arguments.get("mode", "working"),
            base=arguments.get("base"),
            target=arguments.get("target"),
            path=arguments.get("path"),
        )
        return to_mcp_result(success(request_context.request_id, result.as_dict()))

    async def git_refs(ctx, params, request_context):
        arguments = params.arguments
        result = await container.git.refs(
            repository(arguments), kind=arguments.get("kind", "all")
        )
        return to_mcp_result(success(request_context.request_id, result.as_dict()))

    base_properties = {
        "project_id": IDENTIFIER_SCHEMA,
        "repository_id": IDENTIFIER_SCHEMA,
    }
    required_repository = ["project_id", "repository_id"]
    revision_schema = {"type": "string", "minLength": 1, "maxLength": 1024}
    definitions = (
        (
            "git_log",
            "List structured commits from a repository revision",
            {
                **base_properties,
                "revision": revision_schema,
                "max_count": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": container.git.MAX_LOG_COUNT,
                    "default": container.git.DEFAULT_LOG_COUNT,
                },
            },
            required_repository,
            git_log,
        ),
        (
            "git_show",
            "Show one structured commit and its bounded patch",
            {**base_properties, "revision": revision_schema},
            required_repository + ["revision"],
            git_show,
        ),
        (
            "git_diff",
            "Show a bounded working, staged, or revision-range diff",
            {
                **base_properties,
                "mode": {
                    "type": "string",
                    "enum": ["working", "staged", "range"],
                    "default": "working",
                },
                "base": revision_schema,
                "target": revision_schema,
                "path": {"type": "string", "minLength": 1},
            },
            required_repository,
            git_diff,
        ),
        (
            "git_refs",
            "List bounded structured repository refs",
            {
                **base_properties,
                "kind": {
                    "type": "string",
                    "enum": ["all", "heads", "tags", "remotes"],
                    "default": "all",
                },
            },
            required_repository,
            git_refs,
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
