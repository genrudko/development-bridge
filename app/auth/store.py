from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from mcp.shared.auth import OAuthClientInformationFull

from .models import (
    BridgeAccessToken,
    BridgeAuthorizationCode,
    BridgeRefreshToken,
    PendingAuthorization,
)


def token_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class OAuthStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(
                self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
        except FileExistsError:
            os.chmod(self._path, 0o600)
        else:
            os.close(descriptor)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS oauth_clients (
                    client_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_pending_authorizations (
                    request_digest TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_authorization_codes (
                    code_digest TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_access_tokens (
                    token_digest TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    family_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_refresh_tokens (
                    token_digest TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    family_id TEXT NOT NULL
                );
                """
            )

    def save_client(self, client: OAuthClientInformationFull) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO oauth_clients (client_id, data) VALUES (?, ?)",
                (client.client_id, client.model_dump_json()),
            )

    def client(self, client_id: str) -> OAuthClientInformationFull | None:
        data = self._value(
            "SELECT data FROM oauth_clients WHERE client_id = ?", client_id
        )
        return None if data is None else OAuthClientInformationFull.model_validate_json(data)

    def save_pending(self, request_id: str, pending: PendingAuthorization) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO oauth_pending_authorizations
                    (request_digest, data, expires_at) VALUES (?, ?, ?)
                """,
                (token_digest(request_id), pending.model_dump_json(), pending.expires_at),
            )

    def pending(self, request_id: str) -> PendingAuthorization | None:
        data = self._unexpired_value(
            "oauth_pending_authorizations", "request_digest", token_digest(request_id)
        )
        return None if data is None else PendingAuthorization.model_validate_json(data)

    def consume_pending(self, request_id: str) -> PendingAuthorization | None:
        return self._consume(
            "oauth_pending_authorizations",
            "request_digest",
            token_digest(request_id),
            PendingAuthorization,
        )

    def save_code(self, code: str, value: BridgeAuthorizationCode) -> None:
        self._save_token(
            "oauth_authorization_codes",
            "code_digest",
            code,
            value.model_dump_json(exclude={"code"}),
            value.expires_at,
        )

    def code(self, code: str) -> BridgeAuthorizationCode | None:
        data = self._unexpired_value(
            "oauth_authorization_codes", "code_digest", token_digest(code)
        )
        return (
            None
            if data is None
            else BridgeAuthorizationCode.model_validate({**json.loads(data), "code": code})
        )

    def consume_code(self, code: str) -> BridgeAuthorizationCode | None:
        value = self._consume(
            "oauth_authorization_codes",
            "code_digest",
            token_digest(code),
            BridgeAuthorizationCode,
            secret_field="code",
            secret=code,
        )
        return value

    def save_access_token(self, value: BridgeAccessToken) -> None:
        assert value.expires_at is not None
        self._save_token(
            "oauth_access_tokens",
            "token_digest",
            value.token,
            value.model_dump_json(exclude={"token"}),
            value.expires_at,
            value.family_id,
        )

    def access_token(self, token: str) -> BridgeAccessToken | None:
        data = self._unexpired_value(
            "oauth_access_tokens", "token_digest", token_digest(token)
        )
        return self._with_secret(BridgeAccessToken, data, "token", token)

    def save_refresh_token(self, value: BridgeRefreshToken) -> None:
        assert value.expires_at is not None
        self._save_token(
            "oauth_refresh_tokens",
            "token_digest",
            value.token,
            value.model_dump_json(exclude={"token"}),
            value.expires_at,
            value.family_id,
        )

    def refresh_token(self, token: str) -> BridgeRefreshToken | None:
        data = self._unexpired_value(
            "oauth_refresh_tokens", "token_digest", token_digest(token)
        )
        return self._with_secret(BridgeRefreshToken, data, "token", token)

    def consume_refresh_token(self, token: str) -> BridgeRefreshToken | None:
        return self._consume(
            "oauth_refresh_tokens",
            "token_digest",
            token_digest(token),
            BridgeRefreshToken,
            secret_field="token",
            secret=token,
        )

    def revoke(self, token: BridgeAccessToken | BridgeRefreshToken) -> None:
        with self._connect() as connection:
            for table in ("oauth_access_tokens", "oauth_refresh_tokens"):
                connection.execute(
                    f"DELETE FROM {table} WHERE family_id = ?", (token.family_id,)
                )

    def _save_token(
        self, table, key, raw_value, data, expires_at, family_id=None
    ) -> None:
        columns = f"{key}, data, expires_at"
        placeholders = "?, ?, ?"
        values = [token_digest(raw_value), data, expires_at]
        if family_id is not None:
            columns += ", family_id"
            placeholders += ", ?"
            values.append(family_id)
        with self._connect() as connection:
            connection.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                values,
            )

    def _unexpired_value(self, table: str, key: str, digest: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT data FROM {table} WHERE {key} = ? "
                "AND expires_at >= unixepoch()",
                (digest,),
            ).fetchone()
        return None if row is None else str(row[0])

    def _consume(
        self, table, key, digest, model, *, secret_field=None, secret=None
    ):
        with self._connect() as connection:
            row = connection.execute(
                f"DELETE FROM {table} WHERE {key} = ? AND expires_at >= unixepoch() "
                "RETURNING data",
                (digest,),
            ).fetchone()
        if row is None:
            return None
        if secret_field is None:
            return model.model_validate_json(row[0])
        return self._with_secret(model, str(row[0]), secret_field, secret)

    @staticmethod
    def _with_secret(model, data, field, secret):
        if data is None:
            return None
        return model.model_validate({**json.loads(data), field: secret})

    def _value(self, query: str, value: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(query, (value,)).fetchone()
        return None if row is None else str(row[0])

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self._path, timeout=5)
        try:
            connection.execute("PRAGMA journal_mode=DELETE")
            yield connection
            connection.commit()
        finally:
            connection.close()
