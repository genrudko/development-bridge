import subprocess

from mcp import types

from app.config import WORKSPACE


execution_tools = [
    types.Tool(
        name="run_command",
        description="Run safe command",
        inputSchema={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    )
]

ALLOWED = ["python", "pytest", "ls", "find", "grep"]


async def execution_call(ctx, params):
    if params.name != "run_command":
        return None

    command = params.arguments["command"]
    if not any(command.startswith(item) for item in ALLOWED):
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="Command blocked")],
            isError=True,
        )

    result = subprocess.run(
        command,
        shell=True,
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
    )
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=result.stdout + result.stderr)]
    )

