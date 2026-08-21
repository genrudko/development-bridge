from __future__ import annotations

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.api.schemas import IDENTIFIER_SCHEMA
from app.container import ApplicationContainer


HASH_SCHEMA = {"type": "string", "pattern": "^sha256:[0-9a-fA-F]{64}$"}
PATH_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 4096}
CONTENT_SCHEMA = {"type": "string", "maxLength": 1048576}


def _operation_schema() -> dict:
    return {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "type": {"const": "create"},
                    "path": PATH_SCHEMA,
                    "content": CONTENT_SCHEMA,
                },
                "required": ["type", "path", "content"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "type": {"const": "update"},
                    "path": PATH_SCHEMA,
                    "content": CONTENT_SCHEMA,
                    "expected_sha256": HASH_SCHEMA,
                },
                "required": ["type", "path", "content", "expected_sha256"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "type": {"const": "delete"},
                    "path": PATH_SCHEMA,
                    "expected_sha256": HASH_SCHEMA,
                },
                "required": ["type", "path", "expected_sha256"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "type": {"const": "rename"},
                    "source": PATH_SCHEMA,
                    "destination": PATH_SCHEMA,
                    "expected_sha256": HASH_SCHEMA,
                },
                "required": ["type", "source", "destination", "expected_sha256"],
                "additionalProperties": False,
            },
        ]
    }


def change_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    def repository(arguments):
        return container.projects.repositories.get(
            arguments["project_id"], arguments["repository_id"]
        )

    async def change_plan(ctx, params, request_context):
        arguments = params.arguments
        plan = await container.changes.plan(
            repository(arguments),
            arguments["operations"],
            base_revision=arguments.get("base_revision"),
        )
        return to_mcp_result(success(request_context.request_id, plan.as_dict()))

    async def change_apply(ctx, params, request_context):
        arguments = params.arguments
        result = await container.changes.apply(
            repository(arguments),
            plan_id=arguments["plan_id"],
            base_revision=arguments["base_revision"],
            operations=arguments["operations"],
        )
        return to_mcp_result(success(request_context.request_id, result.as_dict()))

    base_properties = {
        "project_id": IDENTIFIER_SCHEMA,
        "repository_id": IDENTIFIER_SCHEMA,
        "base_revision": HASH_SCHEMA,
        "operations": {
            "type": "array",
            "minItems": 1,
            "maxItems": container.changes.MAX_OPERATIONS,
            "items": _operation_schema(),
        },
    }
    repository_required = ["project_id", "repository_id"]
    summary_schema = {
        "type": "object",
        "properties": {
            kind: {"type": "integer", "minimum": 0}
            for kind in ("create", "update", "delete", "rename")
        },
        "required": ["create", "update", "delete", "rename"],
        "additionalProperties": False,
    }
    return (
        RegisteredTool(
            types.Tool(
                name="change_plan",
                description="Validate and normalize a repository change plan",
                inputSchema={
                    "type": "object",
                    "properties": base_properties,
                    "required": repository_required + ["operations"],
                    "additionalProperties": False,
                },
            ),
            change_plan,
            "v1",
        ),
        RegisteredTool(
            types.Tool(
                name="change_apply",
                description="Apply a validated repository change plan once",
                inputSchema={
                    "type": "object",
                    "properties": {
                        **base_properties,
                        "plan_id": HASH_SCHEMA,
                        "summary": summary_schema,
                    },
                    "required": repository_required
                    + ["plan_id", "base_revision", "operations"],
                    "additionalProperties": False,
                },
            ),
            change_apply,
            "v1",
        ),
    )
