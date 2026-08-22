from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from urllib.parse import urlencode

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from .models import (
    BridgeAccessToken,
    BridgeAuthorizationCode,
    BridgeRefreshToken,
    PendingAuthorization,
)
from .store import OAuthStore


OWNER_SUBJECT = "owner"


def create_owner_verifier(password: str, *, salt: bytes | None = None) -> str:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=actual_salt, n=2**14, r=8, p=1, dklen=32
    )
    return "scrypt$16384$8$1${}${}".format(
        base64.urlsafe_b64encode(actual_salt).decode().rstrip("="),
        base64.urlsafe_b64encode(digest).decode().rstrip("="),
    )


def verify_owner_password(password: str, verifier: str) -> bool:
    try:
        algorithm, n, r, p, encoded_salt, encoded_digest = verifier.split("$")
        if algorithm != "scrypt":
            return False
        salt = _decode_base64(encoded_salt)
        expected = _decode_base64(encoded_digest)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def _decode_base64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class BridgeOAuthProvider(
    OAuthAuthorizationServerProvider[
        BridgeAuthorizationCode, BridgeRefreshToken, BridgeAccessToken
    ]
):
    def __init__(
        self,
        store: OAuthStore,
        *,
        issuer_url: str,
        resource_url: str,
        owner_verifier: str,
        access_token_ttl_seconds: int,
        refresh_token_ttl_seconds: int,
    ) -> None:
        self.store = store
        self.issuer_url = issuer_url.rstrip("/")
        self.resource_url = resource_url
        self.owner_verifier = owner_verifier
        self.access_token_ttl_seconds = access_token_ttl_seconds
        self.refresh_token_ttl_seconds = refresh_token_ttl_seconds

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.store.client(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self.store.save_client(client_info)

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        if params.resource != self.resource_url:
            raise AuthorizeError("invalid_target", "Unexpected OAuth resource")
        request_id = secrets.token_urlsafe(32)
        self.store.save_pending(
            request_id,
            PendingAuthorization(
                client_id=client.client_id,
                state=params.state,
                scopes=params.scopes or ["bridge"],
                code_challenge=params.code_challenge,
                redirect_uri=str(params.redirect_uri),
                redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
                resource=self.resource_url,
                expires_at=int(time.time()) + 300,
            ),
        )
        return f"{self.issuer_url}/oauth/approve?{urlencode({'request_id': request_id})}"

    def pending_authorization(self, request_id: str) -> PendingAuthorization | None:
        return self.store.pending(request_id)

    def approve(self, request_id: str, password: str) -> str | None:
        if not verify_owner_password(password, self.owner_verifier):
            return None
        pending = self.store.consume_pending(request_id)
        if pending is None:
            return None
        code = secrets.token_urlsafe(32)
        self.store.save_code(
            code,
            BridgeAuthorizationCode(
                code=code,
                scopes=pending.scopes,
                expires_at=time.time() + 300,
                client_id=pending.client_id,
                code_challenge=pending.code_challenge,
                redirect_uri=pending.redirect_uri,
                redirect_uri_provided_explicitly=(
                    pending.redirect_uri_provided_explicitly
                ),
                resource=pending.resource,
                subject=OWNER_SUBJECT,
            ),
        )
        query = {"code": code}
        if pending.state is not None:
            query["state"] = pending.state
        separator = "&" if "?" in pending.redirect_uri else "?"
        return pending.redirect_uri + separator + urlencode(query)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> BridgeAuthorizationCode | None:
        return self.store.code(authorization_code)

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: BridgeAuthorizationCode,
    ) -> OAuthToken:
        consumed = self.store.consume_code(authorization_code.code)
        if consumed is None or consumed.client_id != client.client_id:
            raise TokenError("invalid_grant", "Authorization code is no longer valid")
        return self._issue_tokens(client.client_id, consumed.scopes, consumed.resource)

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> BridgeRefreshToken | None:
        return self.store.refresh_token(refresh_token)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: BridgeRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        consumed = self.store.consume_refresh_token(refresh_token.token)
        if consumed is None or consumed.client_id != client.client_id:
            raise TokenError("invalid_grant", "Refresh token is no longer valid")
        return self._issue_tokens(
            client.client_id, scopes, consumed.resource, family_id=consumed.family_id
        )

    async def load_access_token(self, token: str) -> BridgeAccessToken | None:
        access_token = self.store.access_token(token)
        if access_token is None or access_token.resource != self.resource_url:
            return None
        return access_token

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        if isinstance(token, (BridgeAccessToken, BridgeRefreshToken)):
            self.store.revoke(token)

    def _issue_tokens(
        self,
        client_id: str,
        scopes: list[str],
        resource: str | None,
        *,
        family_id: str | None = None,
    ) -> OAuthToken:
        if resource != self.resource_url or "bridge" not in scopes:
            raise TokenError("invalid_target", "Unexpected OAuth resource or scope")
        now = int(time.time())
        token_family = family_id or secrets.token_urlsafe(24)
        access = BridgeAccessToken(
            token=secrets.token_urlsafe(32),
            client_id=client_id,
            scopes=scopes,
            expires_at=now + self.access_token_ttl_seconds,
            resource=self.resource_url,
            subject=OWNER_SUBJECT,
            claims={"iss": self.issuer_url},
            family_id=token_family,
        )
        refresh = BridgeRefreshToken(
            token=secrets.token_urlsafe(32),
            client_id=client_id,
            scopes=scopes,
            expires_at=now + self.refresh_token_ttl_seconds,
            subject=OWNER_SUBJECT,
            resource=self.resource_url,
            family_id=token_family,
        )
        self.store.save_access_token(access)
        self.store.save_refresh_token(refresh)
        return OAuthToken(
            access_token=access.token,
            expires_in=self.access_token_ttl_seconds,
            scope=" ".join(scopes),
            refresh_token=refresh.token,
        )
