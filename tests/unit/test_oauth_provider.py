from __future__ import annotations

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest
from mcp.server.auth.provider import AuthorizationParams, TokenError
from mcp.shared.auth import OAuthClientInformationFull

from app.auth import BridgeOAuthProvider, OAuthStore, create_owner_verifier


def challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def configured(tmp_path):
    store = OAuthStore(tmp_path / "oauth.sqlite3")
    store.initialize()
    provider = BridgeOAuthProvider(
        store,
        issuer_url="https://bridge.example",
        resource_url="https://bridge.example/mcp",
        owner_verifier=create_owner_verifier("owner-password", salt=b"0" * 16),
        access_token_ttl_seconds=900,
        refresh_token_ttl_seconds=3600,
    )
    client = OAuthClientInformationFull(
        client_id="public-client",
        redirect_uris=["https://chatgpt.com/callback"],
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        scope="bridge",
    )
    store.save_client(client)
    return provider, client


@pytest.mark.asyncio
async def test_provider_issues_audience_bound_tokens_and_rotates_refresh(tmp_path):
    provider, client = configured(tmp_path)
    redirect = await provider.authorize(
        client,
        AuthorizationParams(
            state="state",
            scopes=["bridge"],
            code_challenge=challenge("verifier"),
            redirect_uri="https://chatgpt.com/callback",
            redirect_uri_provided_explicitly=True,
            resource="https://bridge.example/mcp",
        ),
    )
    request_id = parse_qs(urlparse(redirect).query)["request_id"][0]

    assert provider.approve(request_id, "wrong") is None
    callback = provider.approve(request_id, "owner-password")
    code = parse_qs(urlparse(callback).query)["code"][0]
    authorization_code = await provider.load_authorization_code(client, code)
    first = await provider.exchange_authorization_code(client, authorization_code)
    access = await provider.load_access_token(first.access_token)

    assert access is not None
    assert access.resource == "https://bridge.example/mcp"
    assert access.subject == "owner"
    assert first.refresh_token is not None

    refresh = await provider.load_refresh_token(client, first.refresh_token)
    second = await provider.exchange_refresh_token(client, refresh, ["bridge"])
    assert second.refresh_token != first.refresh_token
    assert await provider.load_refresh_token(client, first.refresh_token) is None

    with pytest.raises(TokenError):
        await provider.exchange_refresh_token(client, refresh, ["bridge"])


@pytest.mark.asyncio
async def test_provider_rejects_an_authorization_for_another_resource(tmp_path):
    provider, client = configured(tmp_path)

    with pytest.raises(Exception, match="Unexpected OAuth resource"):
        await provider.authorize(
            client,
            AuthorizationParams(
                state=None,
                scopes=["bridge"],
                code_challenge=challenge("verifier"),
                redirect_uri="https://chatgpt.com/callback",
                redirect_uri_provided_explicitly=True,
                resource="https://other.example/mcp",
            ),
        )
