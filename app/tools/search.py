import subprocess

from mcp import types

from app.config import WORKSPACE


search_tools = [
    types.Tool(
        name="search_workspace",
        description="Search text in workspace",
        inputSchema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
]


async def search_call(ctx, params):
    if params.name != "search_workspace":
        return None

    query = params.arguments.get("query")
    if not query:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="query required")],
            isError=True,
        )

    result = subprocess.run(
        ["grep", "-R", "-n", query, "."],
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
    )
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=result.stdout or "No matches")]
    )

