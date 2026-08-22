from __future__ import annotations

from mcp.server.auth.provider import AccessToken, AuthorizationCode, RefreshToken
from pydantic import BaseModel


class BridgeAuthorizationCode(AuthorizationCode):
    pass


class BridgeRefreshToken(RefreshToken):
    resource: str
    family_id: str


class BridgeAccessToken(AccessToken):
    family_id: str


class PendingAuthorization(BaseModel):
    client_id: str
    state: str | None
    scopes: list[str]
    code_challenge: str
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    resource: str
    expires_at: int
