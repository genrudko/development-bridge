from github import Github
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

    if not GITHUB_TOKEN:
        text = "GitHub token missing"
    else:
        github = Github(GITHUB_TOKEN)
        user = github.get_user()
        text = f"GitHub connected: {user.login}"

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)]
    )

