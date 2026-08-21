from __future__ import annotations

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.api.schemas import IDENTIFIER_SCHEMA
from app.container import ApplicationContainer


SHA_SCHEMA = {"type": "string", "pattern": "^[0-9a-fA-F]{40,64}$"}
HASH_SCHEMA = {"type": "string", "pattern": "^sha256:[0-9a-fA-F]{64}$"}
BRANCH_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 1024}
REMOTE_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 255}


def git_workspace_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    def repository(arguments):
        return container.projects.repositories.get(
            arguments["project_id"], arguments["repository_id"]
        )

    async def git_fetch(ctx, params, request_context):
        arguments = params.arguments
        result = await container.git_workspace.fetch(
            repository(arguments), remote=arguments.get("remote")
        )
        return to_mcp_result(success(request_context.request_id, result.as_dict()))

    async def git_branch_create(ctx, params, request_context):
        arguments = params.arguments
        result = await container.git_workspace.branch_create(
            repository(arguments),
            branch=arguments["branch"],
            start_point=arguments.get("start_point", "HEAD"),
            expected_head=arguments.get("expected_head"),
        )
        return to_mcp_result(success(request_context.request_id, result.as_dict()))

    async def git_branch_switch(ctx, params, request_context):
        arguments = params.arguments
        result = await container.git_workspace.branch_switch(
            repository(arguments),
            branch=arguments["branch"],
            expected_revision=arguments.get("expected_revision"),
        )
        return to_mcp_result(success(request_context.request_id, result.as_dict()))

    async def git_fast_forward(ctx, params, request_context):
        arguments = params.arguments
        result = await container.git_workspace.fast_forward(
            repository(arguments), expected_head=arguments.get("expected_head")
        )
        return to_mcp_result(success(request_context.request_id, result.as_dict()))

    scope = {"project_id": IDENTIFIER_SCHEMA, "repository_id": IDENTIFIER_SCHEMA}
    required = ["project_id", "repository_id"]

    def registered(name, description, properties, extra_required, handler):
        return RegisteredTool(
            types.Tool(
                name=name,
                description=description,
                inputSchema={
                    "type": "object",
                    "properties": {**scope, **properties},
                    "required": required + extra_required,
                    "additionalProperties": False,
                },
            ),
            handler,
            "v1",
        )

    return (
        registered(
            "git_fetch",
            "Fetch one configured Git remote without changing the workspace",
            {"remote": REMOTE_SCHEMA},
            [],
            git_fetch,
        ),
        registered(
            "git_branch_create",
            "Create a local branch without switching",
            {
                "branch": BRANCH_SCHEMA,
                "start_point": {"type": "string", "minLength": 1, "maxLength": 1024},
                "expected_head": SHA_SCHEMA,
            },
            ["branch"],
            git_branch_create,
        ),
        registered(
            "git_branch_switch",
            "Switch a clean repository to an existing local branch",
            {"branch": BRANCH_SCHEMA, "expected_revision": HASH_SCHEMA},
            ["branch"],
            git_branch_switch,
        ),
        registered(
            "git_fast_forward",
            "Fast-forward a clean current branch to its fetched upstream",
            {"expected_head": SHA_SCHEMA},
            [],
            git_fast_forward,
        ),
    )
