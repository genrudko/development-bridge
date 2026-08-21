import uvicorn

from mcp import types
from mcp.server import Server

from app.tools import TOOLS, call_tool


server = Server("development-mcp")


async def list_tools(ctx, params):
    return types.ListToolsResult(tools=TOOLS)


async def handle_tool(ctx, params):
    result = await call_tool(ctx, params)

    if result is None:
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=f"Unknown tool: {params.name}",
                )
            ],
            isError=True,
        )

    return result


server.add_request_handler(
    "tools/list",
    types.PaginatedRequestParams,
    list_tools,
)

server.add_request_handler(
    "tools/call",
    types.CallToolRequestParams,
    handle_tool,
)

app = server.streamable_http_app()


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8789,
    )

