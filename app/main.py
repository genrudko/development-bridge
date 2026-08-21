import uvicorn

from app.container import build_container
from app.runtime import create_server
from app.transport import create_streamable_http_app
from app.tools.registry import build_tool_registry


container = build_container()
server = create_server(container)
TOOLS = build_tool_registry(container).definitions
app = create_streamable_http_app(server, container.settings, container)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=container.settings.server.host,
        port=container.settings.server.port,
    )
