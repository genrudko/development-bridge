from __future__ import annotations

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.api.schemas import IDENTIFIER_SCHEMA
from app.container import ApplicationContainer


HASH_SCHEMA = {"type": "string", "pattern": "^sha256:[0-9a-fA-F]{64}$"}
SHA_SCHEMA = {"type": "string", "pattern": "^[0-9a-fA-F]{40,64}$"}
BRANCH_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 1024}
REMOTE_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 255}


def git_write_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    def repository(arguments):
        return container.projects.repositories.get(
            arguments["project_id"], arguments["repository_id"]
        )

    async def git_stage(ctx, params, request_context):
        arguments = params.arguments
        result = await container.git_write.stage(
            repository(arguments),
            arguments["paths"],
            base_revision=arguments.get("base_revision"),
        )
        return to_mcp_result(success(request_context.request_id, result.as_dict()))

    async def git_commit(ctx, params, request_context):
        arguments = params.arguments
        result = await container.git_write.commit(
            repository(arguments),
            message=arguments["message"],
            idempotency_key=arguments["idempotency_key"],
            expected_head=arguments.get("expected_head"),
            expected_index_revision=arguments.get("expected_index_revision"),
        )
        return to_mcp_result(success(request_context.request_id, result.as_dict()))

    async def git_push_plan(ctx, params, request_context):
        arguments = params.arguments
        result = await container.git_write.push_plan(
            repository(arguments),
            remote=arguments.get("remote"),
            remote_branch=arguments.get("remote_branch"),
        )
        return to_mcp_result(success(request_context.request_id, result.as_dict()))

    async def git_push(ctx, params, request_context):
        arguments = params.arguments
        result = await container.git_write.push(
            repository(arguments),
            plan_id=arguments["plan_id"],
            local_branch=arguments["local_branch"],
            local_head=arguments["local_head"],
            remote=arguments["remote"],
            remote_branch=arguments["remote_branch"],
            remote_head=arguments["remote_head"],
            set_upstream=arguments["set_upstream"],
            idempotency_key=arguments["idempotency_key"],
        )
        return to_mcp_result(success(request_context.request_id, result.as_dict()))

    scope = {
        "project_id": IDENTIFIER_SCHEMA,
        "repository_id": IDENTIFIER_SCHEMA,
    }
    required_scope = ["project_id", "repository_id"]

    def registered(name, description, properties, required, handler):
        return RegisteredTool(
            types.Tool(
                name=name,
                description=description,
                inputSchema={
                    "type": "object",
                    "properties": {**scope, **properties},
                    "required": required_scope + required,
                    "additionalProperties": False,
                },
            ),
            handler,
            "v1",
        )

    return (
        registered(
            "git_stage",
            "Stage explicit repository paths",
            {
                "base_revision": HASH_SCHEMA,
                "paths": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": container.git_write.MAX_PATHS,
                    "uniqueItems": True,
                    "items": {"type": "string", "minLength": 1, "maxLength": 4096},
                },
            },
            ["paths"],
            git_stage,
        ),
        registered(
            "git_commit",
            "Commit the explicitly prepared Git index",
            {
                "message": {"type": "string", "minLength": 1, "maxLength": container.git_write.MAX_MESSAGE_BYTES},
                "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 200},
                "expected_head": SHA_SCHEMA,
                "expected_index_revision": HASH_SCHEMA,
            },
            ["message", "idempotency_key"],
            git_commit,
        ),
        registered(
            "git_push_plan",
            "Describe an exact non-force push without changing remote refs",
            {"remote": REMOTE_SCHEMA, "remote_branch": BRANCH_SCHEMA},
            [],
            git_push_plan,
        ),
        registered(
            "git_push",
            "Execute an unchanged non-force push plan",
            {
                "plan_id": HASH_SCHEMA,
                "local_branch": BRANCH_SCHEMA,
                "local_head": SHA_SCHEMA,
                "remote": REMOTE_SCHEMA,
                "remote_branch": BRANCH_SCHEMA,
                "remote_head": {"anyOf": [SHA_SCHEMA, {"type": "null"}]},
                "set_upstream": {"type": "boolean"},
                "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 200},
            },
            ["plan_id", "local_branch", "local_head", "remote", "remote_branch", "remote_head", "set_upstream", "idempotency_key"],
            git_push,
        ),
    )
