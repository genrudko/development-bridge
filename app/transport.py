from __future__ import annotations

from mcp.server import Server
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from app.settings import BridgeSettings


def create_streamable_http_app(
    server: Server,
    settings: BridgeSettings,
) -> Starlette:
    return server.streamable_http_app(
        streamable_http_path=settings.server.endpoint,
        transport_security=TransportSecuritySettings(
            allowed_hosts=list(settings.server.allowed_hosts)
        ),
    )

