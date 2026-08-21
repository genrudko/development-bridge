import subprocess

from mcp import types

from app.config import WORKSPACE


git_tools = [
    types.Tool(name="git_status", description="Show git status", inputSchema={"type": "object", "properties": {}}),
    types.Tool(name="git_branch", description="Show current branch", inputSchema={"type": "object", "properties": {}}),
]


def run_git(args):
    result = subprocess.run(
        ["git"] + args,
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return result.stderr

    return result.stdout or "OK"


async def git_call(ctx, params):
    commands = {
        "git_status": ["status", "--short"],
        "git_branch": ["branch", "--show-current"],
    }

    if params.name in commands:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=run_git(commands[params.name]))]
        )

    return None
