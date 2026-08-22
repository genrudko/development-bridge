from __future__ import annotations

import sqlite3
import time

from app.auth.models import BridgeAccessToken, BridgeRefreshToken
from app.auth.store import OAuthStore


def test_store_persists_only_token_digests_and_consumes_refresh_tokens(tmp_path):
    store = OAuthStore(tmp_path / "oauth.sqlite3")
    store.initialize()
    now = int(time.time())
    access = BridgeAccessToken(
        token="access-secret",
        client_id="client",
        scopes=["bridge"],
        expires_at=now + 60,
        resource="https://bridge.example/mcp",
        subject="owner",
        family_id="family",
    )
    refresh = BridgeRefreshToken(
        token="refresh-secret",
        client_id="client",
        scopes=["bridge"],
        expires_at=now + 60,
        resource="https://bridge.example/mcp",
        subject="owner",
        family_id="family",
    )

    store.save_access_token(access)
    store.save_refresh_token(refresh)

    database = (tmp_path / "oauth.sqlite3").read_bytes()
    assert b"access-secret" not in database
    assert b"refresh-secret" not in database
    assert store.access_token("access-secret") == access
    assert store.consume_refresh_token("refresh-secret") == refresh
    assert store.consume_refresh_token("refresh-secret") is None


def test_expired_tokens_are_not_loaded(tmp_path):
    store = OAuthStore(tmp_path / "oauth.sqlite3")
    store.initialize()
    store.save_access_token(
        BridgeAccessToken(
            token="expired",
            client_id="client",
            scopes=["bridge"],
            expires_at=int(time.time()) - 1,
            resource="https://bridge.example/mcp",
            family_id="family",
        )
    )

    assert store.access_token("expired") is None
    assert (tmp_path / "oauth.sqlite3").stat().st_mode & 0o777 == 0o600

    with sqlite3.connect(tmp_path / "oauth.sqlite3") as connection:
        count = connection.execute(
            "SELECT count(*) FROM oauth_access_tokens"
        ).fetchone()[0]
    assert count == 1
