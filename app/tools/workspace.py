import os

import patch_ng
from mcp import types

from app.config import WORKSPACE


workspace_tools = [
    types.Tool(
        name="workspace_status",
        description="Show workspace status",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="read_file",
        description="Read file from workspace",
        inputSchema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    ),
    types.Tool(
        name="apply_patch",
        description="Apply unified diff patch",
        inputSchema={
            "type": "object",
            "properties": {"patch": {"type": "string"}},
            "required": ["patch"],
        },
    ),
]


async def workspace_call(ctx, params):
    if params.name == "workspace_status":
        return types.CallToolResult(
            content=[
                types.TextContent(type="text", text=f"workspace: {WORKSPACE}")
            ]
        )

    if params.name == "read_file":
        path = params.arguments["path"]
        full = os.path.join(WORKSPACE, path)

        with open(full, "r", encoding="utf-8") as file:
            data = file.read()

        return types.CallToolResult(
            content=[types.TextContent(type="text", text=data)]
        )

    if params.name == "apply_patch":
        patch_text = params.arguments["patch"]
        patch = patch_ng.fromstring(patch_text)

        if not patch:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text="Invalid patch")],
                isError=True,
            )

        result = patch.apply(root=WORKSPACE)

        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text="Patch applied" if result else "Patch failed",
                )
            ]
        )

    return None

