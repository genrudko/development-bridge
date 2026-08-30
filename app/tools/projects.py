from __future__ import annotations

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.api.schemas import IDENTIFIER_SCHEMA
from app.container import ApplicationContainer


def project_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    async def project_list(ctx, params, request_context):
        projects = [
            {
                "id": project.id,
                "name": project.name,
                "repository_count": len(project.repositories),
            }
            for project in container.projects.list()
        ]
        return to_mcp_result(success(request_context.request_id, {"projects": projects}))

    async def project_describe(ctx, params, request_context):
        project = container.projects.get(params.arguments["project_id"])
        repositories = [
            {
                "id": repository.id,
                "type": "git",
                "capabilities": repository.capabilities.as_dict(),
            }
            for repository in project.repositories
        ]
        return to_mcp_result(
            success(
                request_context.request_id,
                {"id": project.id, "name": project.name, "repositories": repositories},
            )
        )

    async def repository_status(ctx, params, request_context):
        repository = container.projects.repositories.get(
            params.arguments["project_id"], params.arguments["repository_id"]
        )
        status = await container.git.repository_status(repository)
        data = status.as_dict()
        revision = data.pop("revision")
        return to_mcp_result(
            success(request_context.request_id, data, revision=revision)
        )

    async def repository_clone(ctx, params, request_context):
        arguments = params.arguments
        data = await container.managed_repositories.clone(
            arguments["project_id"],
            arguments["repository_id"],
            arguments["url"],
            arguments.get("depth", 50),
            arguments.get("ref"),
            retention=arguments.get("retention"),
        )
        return to_mcp_result(success(request_context.request_id, data))


    async def repository_retention_set(ctx, params, request_context):
        arguments = params.arguments
        data = await container.managed_repositories.set_retention(
            arguments["project_id"], arguments["repository_id"], arguments["retention"]
        )
        return to_mcp_result(success(request_context.request_id, data))

    async def repository_gc_plan(ctx, params, request_context):
        arguments = params.arguments or {}
        data = await container.managed_repositories.gc_plan(
            arguments.get("project_id"),
            cache_days=arguments.get("cache_days", 30),
            ephemeral_days=arguments.get("ephemeral_days", 14),
        )
        return to_mcp_result(success(request_context.request_id, data))

    async def repository_gc_apply(ctx, params, request_context):
        arguments = params.arguments or {}

        async def apply_gc():
            return await container.managed_repositories.gc_apply(
                arguments.get("project_id"),
                cache_days=arguments.get("cache_days", 30),
                ephemeral_days=arguments.get("ephemeral_days", 14),
                max_groups=arguments.get("max_groups", 4),
                confirm=arguments.get("confirm", False),
            )

        data = await container.jobs.run_when_globally_idle(
            apply_gc, operation_name="repository_gc_apply"
        )
        return to_mcp_result(success(request_context.request_id, data))

    project_schema = {
        "type": "object",
        "properties": {"project_id": IDENTIFIER_SCHEMA},
        "required": ["project_id"],
        "additionalProperties": False,
    }
    repository_schema = {
        "type": "object",
        "properties": {
            "project_id": IDENTIFIER_SCHEMA,
            "repository_id": IDENTIFIER_SCHEMA,
        },
        "required": ["project_id", "repository_id"],
        "additionalProperties": False,
    }
    return (
        RegisteredTool(
            types.Tool(
                name="project_list",
                description="List projects available to the current client",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
            project_list,
            "v1",
        ),
        RegisteredTool(
            types.Tool(
                name="project_describe",
                description="Describe one registered project",
                inputSchema=project_schema,
            ),
            project_describe,
            "v1",
        ),
        RegisteredTool(
            types.Tool(
                name="repository_clone",
                description=(
                    "Clone and register a managed read-only external Git repository"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": IDENTIFIER_SCHEMA,
                        "repository_id": IDENTIFIER_SCHEMA,
                        "url": {"type": "string", "minLength": 1, "maxLength": 2048},
                        "ref": {"type": "string", "minLength": 1, "maxLength": 1024},
                        "depth": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10000,
                            "default": 50,
                        },
                        "retention": {
                            "type": "string",
                            "enum": ["pinned", "cache", "ephemeral"],
                            "default": "cache",
                        },
                    },
                    "required": ["project_id", "repository_id", "url"],
                    "additionalProperties": False,
                },
            ),
            repository_clone,
            "v1",
        ),
        RegisteredTool(
            types.Tool(
                name="repository_retention_set",
                description="Set retention policy for one managed repository",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": IDENTIFIER_SCHEMA,
                        "repository_id": IDENTIFIER_SCHEMA,
                        "retention": {
                            "type": "string",
                            "enum": ["pinned", "cache", "ephemeral"],
                        },
                    },
                    "required": ["project_id", "repository_id", "retention"],
                    "additionalProperties": False,
                },
            ),
            repository_retention_set,
            "v1",
        ),
        RegisteredTool(
            types.Tool(
                name="repository_gc_plan",
                description=(
                    "Plan conservative managed-reference garbage collection without deleting data"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": IDENTIFIER_SCHEMA,
                        "cache_days": {
                            "type": "integer", "minimum": 1, "maximum": 3650, "default": 30
                        },
                        "ephemeral_days": {
                            "type": "integer", "minimum": 1, "maximum": 3650, "default": 14
                        },
                    },
                    "additionalProperties": False,
                },
            ),
            repository_gc_plan,
            "v1",
        ),
        RegisteredTool(
            types.Tool(
                name="repository_gc_apply",
                description=(
                    "Delete a bounded set of stale clean managed-reference storage groups; "
                    "requires confirm=true and global durable-job idleness"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": IDENTIFIER_SCHEMA,
                        "cache_days": {
                            "type": "integer", "minimum": 1, "maximum": 3650, "default": 30
                        },
                        "ephemeral_days": {
                            "type": "integer", "minimum": 1, "maximum": 3650, "default": 14
                        },
                        "max_groups": {
                            "type": "integer", "minimum": 1, "maximum": 32, "default": 4
                        },
                        "confirm": {"type": "boolean"},
                    },
                    "required": ["confirm"],
                    "additionalProperties": False,
                },
            ),
            repository_gc_apply,
            "v1",
        ),
        RegisteredTool(
            types.Tool(
                name="repository_status",
                description="Show structured status for one registered repository",
                inputSchema=repository_schema,
            ),
            repository_status,
            "v1",
        ),
    )
