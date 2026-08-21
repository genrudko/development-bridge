from __future__ import annotations

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.api.schemas import IDENTIFIER_SCHEMA
from app.container import ApplicationContainer


def file_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    def repository(arguments):
        return container.projects.repositories.get(
            arguments["project_id"], arguments["repository_id"]
        )

    async def file_list(ctx, params, request_context):
        arguments = params.arguments
        entries = container.files.list(
            repository(arguments),
            arguments.get("path", ""),
            recursive=arguments.get("recursive", False),
        )
        return to_mcp_result(
            success(
                request_context.request_id,
                {"entries": [entry.as_dict() for entry in entries]},
            )
        )

    async def file_read(ctx, params, request_context):
        arguments = params.arguments
        content = container.files.read(repository(arguments), arguments["path"])
        return to_mcp_result(
            success(
                request_context.request_id,
                {"path": arguments["path"], "content": content},
            )
        )

    async def file_search(ctx, params, request_context):
        arguments = params.arguments
        matches = container.files.search(
            repository(arguments),
            arguments["query"],
            arguments.get("path", ""),
            max_results=arguments.get(
                "max_results", container.files.MAX_SEARCH_RESULTS
            ),
            case_sensitive=arguments.get("case_sensitive", True),
        )
        return to_mcp_result(
            success(
                request_context.request_id,
                {"matches": [match.as_dict() for match in matches]},
            )
        )

    base_properties = {
        "project_id": IDENTIFIER_SCHEMA,
        "repository_id": IDENTIFIER_SCHEMA,
    }
    required_repository = ["project_id", "repository_id"]
    definitions = (
        (
            "file_list",
            "List files within a registered repository",
            {
                **base_properties,
                "path": {"type": "string"},
                "recursive": {"type": "boolean", "default": False},
            },
            required_repository,
            file_list,
        ),
        (
            "file_read",
            "Read a UTF-8 text file within a registered repository",
            {**base_properties, "path": {"type": "string", "minLength": 1}},
            required_repository + ["path"],
            file_read,
        ),
        (
            "file_search",
            "Search UTF-8 text files within a registered repository",
            {
                **base_properties,
                "query": {"type": "string", "minLength": 1},
                "path": {"type": "string"},
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 100,
                },
                "case_sensitive": {"type": "boolean", "default": True},
            },
            required_repository + ["query"],
            file_search,
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
