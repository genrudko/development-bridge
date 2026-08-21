from app.integrations.github import github_status_text
from mcp import types

from app.config import GITHUB_TOKEN


github_tools = [
    types.Tool(
        name="github_status",
        description="Check GitHub connection",
        inputSchema={"type": "object", "properties": {}},
    )
]


async def github_call(ctx, params):
    if params.name != "github_status":
        return None

    text = github_status_text(GITHUB_TOKEN)

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)]
    )

