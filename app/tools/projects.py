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
                name="repository_status",
                description="Show structured status for one registered repository",
                inputSchema=repository_schema,
            ),
            repository_status,
            "v1",
        ),
    )

