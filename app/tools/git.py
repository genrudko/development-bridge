import subprocess

from mcp import types

from app.config import WORKSPACE


git_tools = [
    types.Tool(name="git_status", description="Show git status", inputSchema={"type": "object", "properties": {}}),
    types.Tool(name="git_diff", description="Show git diff", inputSchema={"type": "object", "properties": {}}),
    types.Tool(name="git_branch", description="Show current branch", inputSchema={"type": "object", "properties": {}}),
    types.Tool(
        name="git_log",
        description="Show git history",
        inputSchema={"type": "object", "properties": {"limit": {"type": "integer"}}},
    ),
    types.Tool(
        name="git_commit",
        description="Create git commit",
        inputSchema={
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    ),
    types.Tool(name="git_push", description="Push current branch", inputSchema={"type": "object", "properties": {}}),
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
        "git_diff": ["diff"],
        "git_branch": ["branch", "--show-current"],
        "git_push": ["push"],
    }

    if params.name in commands:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=run_git(commands[params.name]))]
        )

    if params.name == "git_log":
        limit = params.arguments.get("limit", 10)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=run_git(["log", "--oneline", f"-{limit}"]))]
        )

    if params.name == "git_commit":
        message = params.arguments["message"]
        text = run_git(["add", "."]) + run_git(["commit", "-m", message])
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=text)]
        )

    return None

