from __future__ import annotations

import time
from pathlib import PurePosixPath

from mcp.server import Server
from mcp.server.auth.handlers.metadata import MetadataHandler
from mcp.server.auth.middleware.client_auth import ClientAuthenticator
from mcp.server.auth.middleware.bearer_auth import RequireAuthMiddleware
from mcp.server.auth.provider import ProviderTokenVerifier
from mcp.server.auth.routes import (
    build_metadata,
    build_resource_metadata_url,
    cors_middleware,
)
from mcp.server.auth.settings import (
    AuthSettings,
    ClientRegistrationOptions,
    RevocationOptions,
)
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route, request_response

from app.api.context import new_request_context
from app.api.errors import BridgeError, ErrorCode
from app.auth import (
    PublicClientRevocationHandler,
    ResourceBoundTokenHandler,
    approval_route,
)
from app.audit import AuditEvent, AuditOutcome
from app.container import ApplicationContainer
from app.settings import BridgeSettings


def create_streamable_http_app(
    server: Server,
    settings: BridgeSettings,
    container: ApplicationContainer,
) -> Starlette:
    async def artifact_download(request: Request):
        context = new_request_context()
        started = time.perf_counter()
        outcome = AuditOutcome.SUCCESS
        error_code = None
        project_id = request.path_params["project_id"]
        repository_id = request.path_params["repository_id"]
        try:
            if not _host_allowed(request.headers.get("host", ""), settings):
                outcome = AuditOutcome.ERROR
                error_code = ErrorCode.PERMISSION_DENIED.value
                return JSONResponse({"error": "Host is not allowed"}, status_code=421)
            repository = container.projects.repositories.get(project_id, repository_id)
            artifact, path = container.jobs.artifact_file(
                repository,
                request.path_params["job_id"],
                request.path_params["artifact_id"],
            )
            assert artifact.sha256 is not None
            return FileResponse(
                path,
                media_type=artifact.media_type,
                filename=PurePosixPath(artifact.path).name,
                headers={"ETag": f'"{artifact.sha256}"'},
            )
        except BridgeError as error:
            outcome = AuditOutcome.ERROR
            error_code = error.code.value
            status = 403 if error.code is ErrorCode.PERMISSION_DENIED else 404
            return JSONResponse({"error": "Artifact is not available"}, status_code=status)
        except OSError:
            outcome = AuditOutcome.ERROR
            error_code = ErrorCode.ARTIFACT_NOT_FOUND.value
            return JSONResponse({"error": "Artifact is not available"}, status_code=404)
        finally:
            await container.audit.emit(
                AuditEvent(
                    request_id=context.request_id,
                    tool="job_artifact_download",
                    outcome=outcome,
                    duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                    project_id=project_id,
                    repository_id=repository_id,
                    error_code=error_code,
                    event=request.method.lower(),
                    job_id=request.path_params["job_id"],
                )
            )

    async def knowledge_attachment_download(request: Request):
        try:
            if not _host_allowed(request.headers.get("host", ""), settings):
                return JSONResponse({"error": "Host is not allowed"}, status_code=421)
            if container.knowledge_attachments is None:
                raise BridgeError(
                    ErrorCode.KNOWLEDGE_NOT_CONFIGURED,
                    "Knowledge attachment storage is not configured",
                )
            snapshot, path = container.knowledge_attachments.snapshot_file(
                request.path_params["source_id"],
                request.path_params["message_id"],
                request.path_params["attachment_id"],
            )
            return FileResponse(
                path,
                media_type=snapshot["media_type"],
                filename=snapshot["file_name"],
                headers={"ETag": f'"{snapshot["sha256"]}"'},
            )
        except (BridgeError, OSError):
            return JSONResponse(
                {"error": "Knowledge attachment is not available"}, status_code=404
            )

    async def knowledge_attachment_export_download(request: Request):
        try:
            if not _host_allowed(request.headers.get("host", ""), settings):
                return JSONResponse({"error": "Host is not allowed"}, status_code=421)
            if container.knowledge_attachment_exports is None:
                raise LookupError
            resolved = container.knowledge_attachment_exports.resolve(
                request.path_params["token"]
            )
            if resolved is None:
                raise LookupError
            snapshot, path = resolved
            return FileResponse(
                path,
                media_type=snapshot["media_type"],
                filename=snapshot["file_name"],
                headers={
                    "ETag": f'"{snapshot["sha256"]}"',
                    "Cache-Control": "private, no-store",
                },
            )
        except (LookupError, OSError):
            return JSONResponse(
                {"error": "Knowledge attachment export is not available"},
                status_code=404,
                headers={"Cache-Control": "private, no-store"},
            )

    async def job_artifact_export_download(request: Request):
        try:
            if not _host_allowed(request.headers.get("host", ""), settings):
                return JSONResponse({"error": "Host is not allowed"}, status_code=421)
            resolved = container.job_artifact_exports.resolve(
                request.path_params["token"]
            )
            if resolved is None:
                raise LookupError
            artifact, path = resolved
            assert artifact.sha256 is not None
            return FileResponse(
                path,
                media_type=artifact.media_type,
                filename=PurePosixPath(artifact.path).name,
                headers={
                    "ETag": f'"{artifact.sha256}"',
                    "Cache-Control": "private, no-store",
                },
            )
        except (LookupError, OSError):
            return JSONResponse(
                {"error": "Job artifact export is not available"},
                status_code=404,
                headers={"Cache-Control": "private, no-store"},
            )

    async def github_artifact_export_download(request: Request):
        try:
            if not _host_allowed(request.headers.get("host", ""), settings):
                return JSONResponse({"error": "Host is not allowed"}, status_code=421)
            snapshot = container.github_artifact_exports.resolve(request.path_params["token"])
            if snapshot is None:
                raise LookupError
            return FileResponse(
                snapshot.path,
                media_type=snapshot.media_type,
                filename=snapshot.file_name,
                headers={"ETag": f'"{snapshot.sha256}"', "Cache-Control": "private, no-store"},
            )
        except (LookupError, OSError):
            return JSONResponse(
                {"error": "GitHub Actions artifact export is not available"},
                status_code=404,
                headers={"Cache-Control": "private, no-store"},
            )

    artifact_path = settings.server.endpoint.rstrip("/") + (
        "/artifacts/{project_id}/{repository_id}/{job_id}/{artifact_id}"
    )
    knowledge_attachment_path = settings.server.endpoint.rstrip("/") + (
        "/knowledge/attachments/{source_id}/{message_id}/{attachment_id}"
    )
    knowledge_attachment_export_path = settings.server.endpoint.rstrip("/") + (
        "/knowledge/exports/{token}"
    )
    job_artifact_export_path = settings.server.endpoint.rstrip("/") + (
        "/job-artifacts/exports/{token}"
    )
    github_artifact_export_path = settings.server.endpoint.rstrip("/") + (
        "/github-actions-artifacts/exports/{token}"
    )
    artifact_endpoint = artifact_download
    auth_settings = None
    token_verifier = None
    auth_provider = None
    custom_routes = []
    if container.oauth is not None:
        assert settings.oauth.issuer_url is not None
        assert settings.oauth.resource_url is not None
        registration = ClientRegistrationOptions(
            enabled=True,
            valid_scopes=["bridge"],
            default_scopes=["bridge"],
        )
        revocation = RevocationOptions(enabled=True)
        auth_settings = AuthSettings(
            issuer_url=settings.oauth.issuer_url,
            resource_server_url=settings.oauth.resource_url,
            client_registration_options=registration,
            revocation_options=revocation,
            required_scopes=["bridge"],
        )
        token_verifier = ProviderTokenVerifier(container.oauth)
        auth_provider = container.oauth
        resource_metadata_url = build_resource_metadata_url(
            settings.oauth.resource_url
        )
        artifact_endpoint = RequireAuthMiddleware(
            request_response(artifact_download), ["bridge"], resource_metadata_url
        )
        knowledge_attachment_endpoint = RequireAuthMiddleware(
            request_response(knowledge_attachment_download),
            ["bridge"],
            resource_metadata_url,
        )
        custom_routes.append(
            Route(
                "/oauth/approve",
                approval_route(container.oauth),
                methods=["GET", "POST"],
                name="oauth_approve",
            )
        )
    if container.oauth is None:
        knowledge_attachment_endpoint = knowledge_attachment_download
    custom_routes.append(
        Route(
            artifact_path,
            artifact_endpoint,
            methods=["GET", "HEAD"],
            name="job_artifact_download",
        )
    )
    custom_routes.append(
        Route(
            knowledge_attachment_path,
            knowledge_attachment_endpoint,
            methods=["GET", "HEAD"],
            name="knowledge_attachment_download",
        )
    )
    custom_routes.append(
        Route(
            github_artifact_export_path,
            github_artifact_export_download,
            methods=["GET", "HEAD"],
            name="github_actions_artifact_export_download",
        )
    )
    custom_routes.append(
        Route(
            job_artifact_export_path,
            job_artifact_export_download,
            methods=["GET", "HEAD"],
            name="job_artifact_export_download",
        )
    )
    custom_routes.append(
        Route(
            knowledge_attachment_export_path,
            knowledge_attachment_export_download,
            methods=["GET", "HEAD"],
            name="knowledge_attachment_export_download",
        )
    )
    app = server.streamable_http_app(
        streamable_http_path=settings.server.endpoint,
        transport_security=TransportSecuritySettings(
            allowed_hosts=list(settings.server.allowed_hosts)
        ),
        auth=auth_settings,
        token_verifier=token_verifier,
        auth_server_provider=auth_provider,
        custom_starlette_routes=custom_routes,
    )
    if container.oauth is not None:
        _advertise_public_clients(app, settings)
        _enforce_token_resource(app, settings, container)
        _support_public_client_revocation(app, container)
    return app


def _advertise_public_clients(app: Starlette, settings: BridgeSettings) -> None:
    assert settings.oauth.issuer_url is not None
    registration = ClientRegistrationOptions(
        enabled=True,
        valid_scopes=["bridge"],
        default_scopes=["bridge"],
    )
    metadata = build_metadata(
        settings.oauth.issuer_url,
        None,
        registration,
        RevocationOptions(enabled=True),
    )
    metadata.token_endpoint_auth_methods_supported = [
        "none",
        "client_secret_basic",
        "client_secret_post",
    ]
    replacement = Route(
        "/.well-known/oauth-authorization-server",
        endpoint=cors_middleware(MetadataHandler(metadata).handle, ["GET", "OPTIONS"]),
        methods=["GET", "OPTIONS"],
    )
    for index, route in enumerate(app.routes):
        if getattr(route, "path", None) == replacement.path:
            app.routes[index] = replacement
            return
    raise RuntimeError("OAuth authorization server metadata route is missing")


def _enforce_token_resource(
    app: Starlette, settings: BridgeSettings, container: ApplicationContainer
) -> None:
    assert settings.oauth.resource_url is not None
    assert container.oauth is not None
    handler = ResourceBoundTokenHandler(
        container.oauth,
        ClientAuthenticator(container.oauth),
        resource_url=str(settings.oauth.resource_url),
    )
    replacement = Route(
        "/token",
        endpoint=cors_middleware(handler.handle, ["POST", "OPTIONS"]),
        methods=["POST", "OPTIONS"],
    )
    for index, route in enumerate(app.routes):
        if getattr(route, "path", None) == replacement.path:
            app.routes[index] = replacement
            return
    raise RuntimeError("OAuth token route is missing")


def _support_public_client_revocation(
    app: Starlette, container: ApplicationContainer
) -> None:
    assert container.oauth is not None
    handler = PublicClientRevocationHandler(container.oauth)
    replacement = Route(
        "/revoke",
        endpoint=cors_middleware(handler.handle, ["POST", "OPTIONS"]),
        methods=["POST", "OPTIONS"],
    )
    for index, route in enumerate(app.routes):
        if getattr(route, "path", None) == replacement.path:
            app.routes[index] = replacement
            return
    raise RuntimeError("OAuth revocation route is missing")


def _host_allowed(host: str, settings: BridgeSettings) -> bool:
    host = host.casefold()
    for configured in settings.server.allowed_hosts:
        pattern = configured.casefold()
        if pattern == "*" or host == pattern:
            return True
        if pattern.endswith(":*") and host.split(":", 1)[0] == pattern[:-2]:
            return True
    return False
