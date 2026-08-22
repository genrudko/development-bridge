from __future__ import annotations

from typing import Literal

from mcp.server.auth.handlers.revoke import RevocationErrorResponse
from mcp.server.auth.handlers.token import TokenErrorResponse, TokenHandler
from mcp.server.auth.json_response import PydanticJSONResponse
from mcp.server.auth.middleware.client_auth import AuthenticationError, ClientAuthenticator
from pydantic import BaseModel, ValidationError
from starlette.requests import Request
from starlette.responses import Response

from .provider import BridgeOAuthProvider


class ResourceBoundTokenHandler(TokenHandler):
    def __init__(self, *args, resource_url: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.resource_url = resource_url

    async def handle(self, request: Request):
        form = await request.form()
        if form.get("resource") != self.resource_url:
            return self.response(
                TokenErrorResponse(
                    error="invalid_target",
                    error_description="Unexpected OAuth resource",
                )
            )
        return await super().handle(request)


class BridgeRevocationRequest(BaseModel):
    token: str
    token_type_hint: Literal["access_token", "refresh_token"] | None = None
    client_id: str
    client_secret: str | None = None


class PublicClientRevocationHandler:
    def __init__(self, provider: BridgeOAuthProvider) -> None:
        self.provider = provider
        self.client_authenticator = ClientAuthenticator(provider)

    async def handle(self, request: Request) -> Response:
        try:
            client = await self.client_authenticator.authenticate_request(request)
        except AuthenticationError as error:
            return PydanticJSONResponse(
                status_code=401,
                content=RevocationErrorResponse(
                    error="unauthorized_client", error_description=error.message
                ),
            )
        try:
            revocation = BridgeRevocationRequest.model_validate(
                dict(await request.form())
            )
        except ValidationError:
            return PydanticJSONResponse(
                status_code=400,
                content=RevocationErrorResponse(
                    error="invalid_request", error_description="Invalid revocation request"
                ),
            )
        token = None
        if revocation.token_type_hint != "refresh_token":
            token = await self.provider.load_access_token(revocation.token)
        if token is None:
            token = await self.provider.load_refresh_token(client, revocation.token)
        if token is not None and token.client_id == client.client_id:
            await self.provider.revoke_token(token)
        return Response(
            status_code=200,
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )
