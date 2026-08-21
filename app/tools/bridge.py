from __future__ import annotations

from mcp import types

from app.api.registry import RegisteredTool
from app.api.results import success, to_mcp_result
from app.container import ApplicationContainer


def bridge_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    async def bridge_info(ctx, params, request_context):
        return to_mcp_result(
            success(
                request_context.request_id,
                {
                    "name": container.settings.server.name,
                    "version": "1.0.0",
                    "api_version": "1.0",
                    "capabilities": [
                        "multi-project",
                        "repository-status",
                        "repository-files",
                        "git-read",
                        "controlled-changes",
                        "tasks-jobs",
                        "git-write",
                    ],
                    "project_count": len(container.projects.list()),
                },
            )
        )

    return (
        RegisteredTool(
            definition=types.Tool(
                name="bridge_info",
                description="Describe Development Bridge and its capabilities",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
            handler=bridge_info,
            source="v1",
        ),
    )
