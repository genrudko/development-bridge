from __future__ import annotations

import base64
import hashlib
from dataclasses import replace
from urllib.parse import parse_qs, urlparse

import httpx2
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.auth import create_owner_verifier
from app.container import build_container
from app.knowledge.telegram import TelegramAttachment
from app.runtime import create_server
from app.settings import BridgeSettings
from app.transport import create_streamable_http_app
from tests.fixtures.telegram_adapter import FakeTelegramAdapter, message as telegram_message


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "auth_method", ["none", "client_secret_post", "client_secret_basic"]
)
async def test_full_oauth_flow_supports_public_and_confidential_clients(
    tmp_path, auth_method
):
    settings = BridgeSettings.model_validate(
        {
            "oauth": {
                "enabled": True,
                "issuer_url": "http://127.0.0.1",
                "resource_url": "http://127.0.0.1/mcp",
                "database_path": tmp_path / "oauth.sqlite3",
                "owner_verifier": create_owner_verifier("owner-password"),
            }
        }
    )
    container = build_container(settings)
    app = create_streamable_http_app(create_server(container), settings, container)
    transport = httpx2.ASGITransport(app=app)
    verifier = "v" * 64

    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1",
            follow_redirects=False,
        ) as client:
            registration = await client.post(
                "/register",
                json={
                    "client_name": "OAuth integration test",
                    "redirect_uris": ["https://chatgpt.com/test-callback"],
                    "token_endpoint_auth_method": auth_method,
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "scope": "bridge",
                },
            )
            assert registration.status_code == 201
            registered = registration.json()
            client_id = registered["client_id"]
            client_secret = registered.get("client_secret")
            assert (client_secret is None) is (auth_method == "none")

            rejected_redirect = await client.get(
                "/authorize",
                params={
                    "client_id": client_id,
                    "redirect_uri": "https://attacker.example/callback",
                    "response_type": "code",
                    "code_challenge": pkce_challenge(verifier),
                    "code_challenge_method": "S256",
                    "scope": "bridge",
                    "resource": "http://127.0.0.1/mcp",
                },
            )
            assert rejected_redirect.status_code == 400

            authorization = await client.get(
                "/authorize",
                params={
                    "client_id": client_id,
                    "redirect_uri": "https://chatgpt.com/test-callback",
                    "response_type": "code",
                    "code_challenge": pkce_challenge(verifier),
                    "code_challenge_method": "S256",
                    "state": "expected-state",
                    "scope": "bridge",
                    "resource": "http://127.0.0.1/mcp",
                },
            )
            approval_url = authorization.headers["location"]
            assert approval_url.startswith("http://127.0.0.1/oauth/approve?")
            approval = await client.get(approval_url)
            assert approval.status_code == 200

            request_id = parse_qs(urlparse(approval_url).query)["request_id"][0]
            approved = await client.post(
                "/oauth/approve",
                data={"request_id": request_id, "password": "owner-password"},
            )
            callback = approved.headers["location"]
            callback_query = parse_qs(urlparse(callback).query)
            assert callback_query["state"] == ["expected-state"]

            token_data = {
                "grant_type": "authorization_code",
                "code": callback_query["code"][0],
                "redirect_uri": "https://chatgpt.com/test-callback",
                "client_id": client_id,
                "code_verifier": verifier,
                "resource": "http://127.0.0.1/mcp",
            }
            token_headers = {}
            if auth_method == "client_secret_post":
                token_data["client_secret"] = client_secret
            elif auth_method == "client_secret_basic":
                credentials = base64.b64encode(
                    f"{client_id}:{client_secret}".encode()
                ).decode()
                token_headers["Authorization"] = f"Basic {credentials}"

            wrong_resource = {**token_data, "resource": "http://127.0.0.1/other"}
            rejected = await client.post(
                "/token", data=wrong_resource, headers=token_headers
            )
            assert rejected.status_code == 400
            assert rejected.json()["error"] == "invalid_target"

            wrong_verifier = {**token_data, "code_verifier": "wrong"}
            rejected = await client.post(
                "/token", data=wrong_verifier, headers=token_headers
            )
            assert rejected.status_code == 400
            assert rejected.json()["error"] == "invalid_grant"

            token_response = await client.post(
                "/token", data=token_data, headers=token_headers
            )
            assert token_response.status_code == 200
            tokens = token_response.json()
            assert tokens["scope"] == "bridge"
            assert tokens["refresh_token"]

            client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
            async with streamable_http_client(
                "http://127.0.0.1/mcp", http_client=client
            ) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    initialized = await session.initialize()
                    assert initialized.server_info.name == "development-bridge"

            artifact = await client.get(
                "/mcp/artifacts/project/repository/job_" + "1" * 32 + "/report"
            )
            assert artifact.status_code == 404

            refresh_data = {
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": client_id,
                "resource": "http://127.0.0.1/mcp",
            }
            if auth_method == "client_secret_post":
                refresh_data["client_secret"] = client_secret
            rejected_refresh = await client.post(
                "/token",
                data={**refresh_data, "resource": "http://127.0.0.1/other"},
                headers=token_headers,
            )
            assert rejected_refresh.status_code == 400
            assert rejected_refresh.json()["error"] == "invalid_target"
            refreshed = await client.post(
                "/token", data=refresh_data, headers=token_headers
            )
            assert refreshed.status_code == 200
            refreshed_tokens = refreshed.json()
            assert refreshed_tokens["refresh_token"] != tokens["refresh_token"]
            replayed = await client.post(
                "/token", data=refresh_data, headers=token_headers
            )
            assert replayed.status_code == 400

            revocation_data = {
                "token": refreshed_tokens["refresh_token"],
                "token_type_hint": "refresh_token",
                "client_id": client_id,
            }
            if auth_method == "client_secret_post":
                revocation_data["client_secret"] = client_secret
            revoked = await client.post(
                "/revoke", data=revocation_data, headers=token_headers
            )
            assert revoked.status_code == 200
            client.headers["Authorization"] = (
                f"Bearer {refreshed_tokens['access_token']}"
            )
            rejected_mcp = await client.post("/mcp")
            assert rejected_mcp.status_code == 401


@pytest.mark.asyncio
async def test_artifact_download_requires_the_same_bearer_token(tmp_path):
    settings = BridgeSettings.model_validate(
        {
            "oauth": {
                "enabled": True,
                "issuer_url": "http://127.0.0.1",
                "resource_url": "http://127.0.0.1/mcp",
                "database_path": tmp_path / "oauth.sqlite3",
                "owner_verifier": create_owner_verifier("owner-password"),
            }
        }
    )
    container = build_container(settings)
    app = create_streamable_http_app(create_server(container), settings, container)

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.get(
            "/mcp/artifacts/project/repository/job_" + "1" * 32 + "/report"
        )

    assert response.status_code == 401
    assert "resource_metadata=" in response.headers["www-authenticate"]


@pytest.mark.asyncio
async def test_knowledge_attachment_download_requires_the_same_bearer_token(tmp_path):
    settings = BridgeSettings.model_validate({
        "oauth": {
            "enabled": True,
            "issuer_url": "http://127.0.0.1",
            "resource_url": "http://127.0.0.1/mcp",
            "database_path": tmp_path / "oauth.sqlite3",
            "owner_verifier": create_owner_verifier("owner-password"),
        },
        "knowledge": {
            "database_path": tmp_path / "knowledge.sqlite3",
            "attachment_directory": tmp_path / "attachments",
        },
    })
    container = build_container(settings)
    app = create_streamable_http_app(create_server(container), settings, container)

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.get(
            "/mcp/knowledge/attachments/telegram-example/1/document-example"
        )

    assert response.status_code == 401
    assert "resource_metadata=" in response.headers["www-authenticate"]


@pytest.mark.asyncio
async def test_valid_export_token_bypasses_oauth_but_not_attachment_validation(tmp_path):
    attachment_message = replace(
        telegram_message(5),
        attachments=(TelegramAttachment("document", {
            "telegram_media_id": "export-5", "mime_type": "application/octet-stream",
            "file_name": "firmware.bin", "size": 6,
        }),),
    )
    adapter = FakeTelegramAdapter(
        [attachment_message], attachment_bytes={"document-export-5": b"binary"}
    )
    settings = BridgeSettings.model_validate({
        "server": {"public_base_url": "https://bridge.example"},
        "oauth": {
            "enabled": True,
            "issuer_url": "http://127.0.0.1",
            "resource_url": "http://127.0.0.1/mcp",
            "database_path": tmp_path / "oauth.sqlite3",
            "owner_verifier": create_owner_verifier("owner-password"),
        },
        "knowledge": {
            "database_path": tmp_path / "knowledge.sqlite3",
            "attachment_directory": tmp_path / "attachments",
        },
    })
    container = build_container(settings, telegram_adapter=adapter)
    added = await container.telegram_knowledge.source_add("@ad5x_community")
    exported = await container.knowledge_attachment_exports.export(
        added["source_id"], "5", "document-export-5"
    )
    app = create_streamable_http_app(create_server(container), settings, container)

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.get(urlparse(exported["export_url"]).path)
        protected = await client.get(
            "/mcp/knowledge/attachments/" + added["source_id"]
            + "/5/document-export-5"
        )

    assert response.status_code == 200
    assert response.content == b"binary"
    assert protected.status_code == 401
