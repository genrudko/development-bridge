from __future__ import annotations

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.api.schemas import IDENTIFIER_SCHEMA
from app.container import ApplicationContainer


def command_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    async def run_command(ctx, params, request_context):
        arguments = params.arguments
        repository = container.projects.repositories.get(
            arguments["project_id"], arguments["repository_id"]
        )
        data = await container.commands.run(
            repository,
            arguments["executable"],
            arguments.get("arguments", []),
            timeout_seconds=arguments.get("timeout_seconds", 10),
            output_limit_bytes=arguments.get("output_limit_bytes", 65_536),
        )
        return to_mcp_result(success(request_context.request_id, data))

    return (
        RegisteredTool(
            types.Tool(
                name="run_command",
                description=(
                    "Run structured argv synchronously only when the global durable job "
                    "queue is idle"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": IDENTIFIER_SCHEMA,
                        "repository_id": IDENTIFIER_SCHEMA,
                        "executable": {
                            "type": "string", "minLength": 1, "maxLength": 4096,
                        },
                        "arguments": {
                            "type": "array", "maxItems": 256,
                            "items": {"type": "string", "maxLength": 4096},
                            "default": [],
                        },
                        "timeout_seconds": {
                            "type": "number", "exclusiveMinimum": 0,
                            "maximum": 30, "default": 10,
                        },
                        "output_limit_bytes": {
                            "type": "integer", "minimum": 1024,
                            "maximum": 65536, "default": 65536,
                        },
                    },
                    "required": ["project_id", "repository_id", "executable"],
                    "additionalProperties": False,
                },
            ),
            run_command,
            "v1",
        ),
    )
