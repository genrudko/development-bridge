from __future__ import annotations

import httpx2
import pytest

from app.auth import create_owner_verifier
from app.container import build_container
from app.runtime import create_server
from app.settings import BridgeSettings
from app.transport import create_streamable_http_app


def oauth_settings(tmp_path):
    return BridgeSettings.model_validate(
        {
            "oauth": {
                "enabled": True,
                "issuer_url": "http://127.0.0.1",
                "resource_url": "http://127.0.0.1/mcp",
                "database_path": tmp_path / "oauth.sqlite3",
                "owner_verifier": create_owner_verifier("password"),
            }
        }
    )


@pytest.mark.asyncio
async def test_oauth_discovery_advertises_dcr_pkce_refresh_and_public_clients(tmp_path):
    settings = oauth_settings(tmp_path)
    container = build_container(settings)
    app = create_streamable_http_app(create_server(container), settings, container)

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        protected = await client.get("/.well-known/oauth-protected-resource/mcp")
        authorization = await client.get("/.well-known/oauth-authorization-server")
        unauthenticated = await client.post("/mcp")

    assert protected.json() == {
        "resource": "http://127.0.0.1/mcp",
        "authorization_servers": ["http://127.0.0.1"],
        "scopes_supported": ["bridge"],
        "bearer_methods_supported": ["header"],
    }
    metadata = authorization.json()
    assert metadata["registration_endpoint"] == "http://127.0.0.1/register"
    assert metadata["grant_types_supported"] == ["authorization_code", "refresh_token"]
    assert metadata["code_challenge_methods_supported"] == ["S256"]
    assert set(metadata["token_endpoint_auth_methods_supported"]) == {
        "none",
        "client_secret_basic",
        "client_secret_post",
    }
    assert unauthenticated.status_code == 401
    assert "resource_metadata=" in unauthenticated.headers["www-authenticate"]
