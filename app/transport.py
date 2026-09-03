from __future__ import annotations

import hmac
import time
from pathlib import PurePosixPath

from mcp.server import Server
from mcp.server.auth.handlers.metadata import MetadataHandler
from mcp.server.auth.middleware.bearer_auth import RequireAuthMiddleware
from mcp.server.auth.middleware.client_auth import ClientAuthenticator
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
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route, request_response

from app.api.context import new_request_context
from app.api.errors import BridgeError, ErrorCode
from app.audit import AuditEvent, AuditOutcome
from app.auth import (
    PublicClientRevocationHandler,
    ResourceBoundTokenHandler,
    approval_route,
)
from app.container import ApplicationContainer
from app.ops.routes import create_operator_dashboard_routes
from app.settings import BridgeSettings


def create_streamable_http_app(
    server: Server,
    settings: BridgeSettings,
    container: ApplicationContainer,
) -> Starlette:
    desktop = container.desktop_nodes

    def desktop_authorized(request: Request) -> bool:
        configured = settings.desktop_nodes.token
        authorization = request.headers.get("authorization", "")
        supplied = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
        return configured is not None and hmac.compare_digest(supplied, configured.get_secret_value())

    def desktop_error(error: BridgeError) -> JSONResponse:
        status = 404 if error.code is ErrorCode.DESKTOP_NODE_NOT_FOUND else 400 if error.code is ErrorCode.INVALID_ARGUMENT else 409
        return JSONResponse({"error": error.message, "code": error.code.value}, status_code=status)

    async def desktop_route(request: Request):
        if settings.desktop_nodes.token is None:
            return JSONResponse({"error": "Not found"}, status_code=404)
        if not desktop_authorized(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        node_id, action = request.path_params["node_id"], request.path_params["action"]
        try:
            if action == "claim":
                command = await desktop.claim(node_id, float(request.query_params.get("wait", settings.desktop_nodes.claim_timeout_seconds)))
                return JSONResponse({"command": command})
            limit = settings.desktop_nodes.max_result_bytes if action == "result" else settings.desktop_nodes.max_request_bytes
            if int(request.headers.get("content-length", "0") or 0) > limit:
                raise OverflowError
            raw = await request.body()
            if len(raw) > limit:
                raise OverflowError
            import json
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError
            if action == "register":
                return JSONResponse(await desktop.register(node_id, body.get("tools", []), bool(body.get("fusion_available", False)), body.get("telemetry")))
            if action == "heartbeat":
                return JSONResponse(await desktop.heartbeat(node_id, body.get("tools"), body.get("fusion_available"), body.get("telemetry")))
            if action == "result-upload-start":
                return JSONResponse(desktop.begin_result_upload(node_id, body["command_id"], body["size_bytes"], body["sha256"]))
            if action == "result-upload-chunk":
                return JSONResponse(desktop.append_result_upload(node_id, body["upload_id"], body["offset"], body["data"]))
            if action == "result-upload-finalize":
                return JSONResponse(desktop.finalize_result_upload(node_id, body["upload_id"]))
            if action == "result":
                await desktop.submit_result(node_id, body["command_id"], body["result"])
                return JSONResponse({"accepted": True})
            return JSONResponse({"error": "Not found"}, status_code=404)
        except OverflowError:
            return JSONResponse({"error": "Request too large"}, status_code=413)
        except (KeyError, TypeError, ValueError):
            return JSONResponse({"error": "Invalid request"}, status_code=400)
        except BridgeError as error:
            return desktop_error(error)

    async def desktop_operator_route(request: Request):
        if settings.desktop_nodes.token is None:
            return JSONResponse({"error": "Not found"}, status_code=404)
        if request.client is None or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            return JSONResponse({"error": "Forbidden"}, status_code=403)
        if not desktop_authorized(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        node_id, action = request.path_params["node_id"], request.path_params["action"]
        try:
            if action == "status":
                return JSONResponse(desktop.status(node_id))
            if action == "tools":
                return JSONResponse(desktop.tools(node_id))
            if action != "call":
                return JSONResponse({"error": "Not found"}, status_code=404)
            limit = settings.desktop_nodes.max_request_bytes
            if int(request.headers.get("content-length", "0") or 0) > limit:
                raise OverflowError
            raw = await request.body()
            if len(raw) > limit:
                raise OverflowError
            import json
            body = json.loads(raw)
            if not isinstance(body, dict) or not isinstance(body.get("tool_name"), str) or not isinstance(body.get("arguments"), dict):
                raise ValueError
            return JSONResponse(await desktop.call(node_id, body["tool_name"], body["arguments"]))
        except OverflowError:
            return JSONResponse({"error": "Request too large"}, status_code=413)
        except (TypeError, ValueError):
            return JSONResponse({"error": "Invalid request"}, status_code=400)
        except BridgeError as error:
            return desktop_error(error)
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

    async def desktop_result_export(request: Request):
        resolved = desktop.resolve_external_export(request.path_params["token"])
        if resolved is None:
            return JSONResponse({"error": "Desktop result is not available"}, status_code=404)
        path, item = resolved
        return FileResponse(
            path,
            media_type=item.get("mime_type", "application/json"),
            filename=item.get("file_name", path.name),
            headers={
                "Cache-Control": "private, no-store",
                "ETag": f'"sha256:{item["sha256"]}"',
            },
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

    coordinator_ui_headers = {
        "Cache-Control": "no-store",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }

    async def coordinator_status(request: Request):
        try:
            return JSONResponse(
                await container.coordinator.status(
                    request.query_params.get("channel_id", "coordinator"),
                    delivery_lease=request.query_params.get("delivery_lease"),
                ),
                headers=coordinator_ui_headers,
            )
        except BridgeError as error:
            return JSONResponse({"error": error.message}, status_code=400, headers=coordinator_ui_headers)

    async def coordinator_claim(request: Request):
        try:
            return JSONResponse(
                await container.coordinator.claim(
                    request.query_params.get("channel_id", "coordinator"),
                    delivery_lease=request.query_params.get("delivery_lease"),
                ),
                headers=coordinator_ui_headers,
            )
        except BridgeError as error:
            return JSONResponse({"error": error.message}, status_code=400, headers=coordinator_ui_headers)

    async def coordinator_ack(request: Request):
        try:
            return JSONResponse(
                await container.coordinator.ack(
                    request.query_params.get("channel_id", "coordinator"),
                    request.query_params.get("claim_id", ""),
                    delivery_lease=request.query_params.get("delivery_lease"),
                ),
                headers=coordinator_ui_headers,
            )
        except BridgeError as error:
            return JSONResponse({"error": error.message}, status_code=400, headers=coordinator_ui_headers)

    async def coordinator_observed(request: Request):
        try:
            return JSONResponse(
                await container.coordinator.observe_model_turn(
                    request.query_params.get("channel_id", "coordinator"),
                    request.query_params.get("continuation_id", ""),
                ),
                headers=coordinator_ui_headers,
            )
        except BridgeError as error:
            return JSONResponse({"error": error.message}, status_code=400, headers=coordinator_ui_headers)

    async def coordinator_browser_preflight(request: Request):
        client_host = request.client.host if request.client is not None else ""
        if client_host not in {"127.0.0.1", "::1", "testclient"}:
            return JSONResponse(
                {"error": "Browser preflight authorization is localhost-only"},
                status_code=403,
                headers=coordinator_ui_headers,
            )
        try:
            return JSONResponse(
                await container.coordinator.authorize_browser_preflight(
                    request.query_params.get("channel_id", "coordinator"),
                    request.query_params.get("continuation_id", ""),
                ),
                headers=coordinator_ui_headers,
            )
        except BridgeError as error:
            return JSONResponse({"error": error.message}, status_code=400, headers=coordinator_ui_headers)

    async def coordinator_discover_current_chat(request: Request):
        if request.method == "OPTIONS":
            return Response(status_code=204, headers=coordinator_ui_headers)
        try:
            if int(request.headers.get("content-length", "0") or 0) > 8192:
                raise ValueError
            body = await request.json()
            if not isinstance(body, dict):
                raise TypeError
            route_id = body["route_id"]
            token = body["token"]
            service = container.coordinator_wake_delivery
            if service is None:
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    "Current-chat discovery requires configured wake delivery",
                )
            result = await service.discover_and_bind_current_route(route_id, token)
            return JSONResponse(result, headers=coordinator_ui_headers)
        except BridgeError as error:
            status = 409 if error.code is ErrorCode.POLICY_VIOLATION else 400
            return JSONResponse(
                {"error": error.message}, status_code=status, headers=coordinator_ui_headers
            )
        except (KeyError, TypeError, ValueError):
            return JSONResponse(
                {"error": "Invalid current-chat discovery request"},
                status_code=400,
                headers=coordinator_ui_headers,
            )

    async def coordinator_rollover_control(request: Request):
        try:
            if int(request.headers.get("content-length", "0") or 0) > 8192:
                raise ValueError
            body = await request.json()
            if not isinstance(body, dict):
                raise TypeError
            route_id = body["route_id"]
            token = body["token"]
            action = request.path_params.get("action", "")
            if action == "candidate":
                result = container.route_registry.record_rollover_candidate(
                    route_id, token, body["url"]
                )
            elif action == "commit":
                result = container.route_registry.commit_rollover(route_id, token)
            elif action == "complete":
                result = container.route_registry.complete_rollover(route_id, token)
            elif action == "abort":
                result = container.route_registry.abort_rollover(
                    route_id, token, body.get("reason")
                )
            else:
                return JSONResponse(
                    {"error": "Unknown rollover action"},
                    status_code=404,
                    headers=coordinator_ui_headers,
                )
            return JSONResponse(result, headers=coordinator_ui_headers)
        except BridgeError as error:
            status = 409 if error.code is ErrorCode.POLICY_VIOLATION else 400
            return JSONResponse(
                {"error": error.message}, status_code=status, headers=coordinator_ui_headers
            )
        except (KeyError, TypeError, ValueError):
            return JSONResponse(
                {"error": "Invalid rollover request"},
                status_code=400,
                headers=coordinator_ui_headers,
            )

    async def coordinator_trigger(request: Request):
        configured_token = settings.server.x_trigger_token
        if configured_token is None:
            return JSONResponse({"error": "Not found"}, status_code=404)
        authorization = request.headers.get("authorization", "")
        supplied = (
            authorization.removeprefix("Bearer ")
            if authorization.startswith("Bearer ")
            else request.headers.get("x-development-bridge-trigger-token", "")
        )
        if not hmac.compare_digest(supplied, configured_token.get_secret_value()):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        try:
            if int(request.headers.get("content-length", "0") or 0) > 8192:
                raise ValueError
            body = await request.json()
            if not isinstance(body, dict):
                raise TypeError
            if "message" not in body:
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "message is required")
            result = await container.coordinator.arm(
                body["message"],
                channel_id=body.get("channel_id", "coordinator"),
                delay_seconds=body.get("delay", 0),
                conflict=body.get("conflict", "coalesce"),
            )
            return JSONResponse(result, status_code=202)
        except BridgeError as error:
            status = 409 if error.code is ErrorCode.POLICY_VIOLATION else 400
            return JSONResponse({"error": error.message}, status_code=status)
        except (ValueError, TypeError):
            return JSONResponse({"error": "Invalid JSON request"}, status_code=400)

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
    coordinator_base_path = settings.server.endpoint.rstrip("/") + "/x/coordinator"
    artifact_endpoint = artifact_download
    auth_settings = None
    token_verifier = None
    auth_provider = None
    custom_routes = []
    custom_routes.append(Route(settings.server.endpoint.rstrip("/") + "/desktop-nodes/{node_id}/{action}", desktop_route, methods=["POST"], name="desktop_node_agent"))
    custom_routes.append(Route(settings.server.endpoint.rstrip("/") + "/desktop-nodes/{node_id}/operator/{action}", desktop_operator_route, methods=["POST"], name="desktop_node_operator"))
    custom_routes.append(Route(settings.server.endpoint.rstrip("/") + "/desktop-results/exports/{token}", desktop_result_export, methods=["GET", "HEAD"], name="desktop_result_export"))
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
            coordinator_base_path + "/status",
            coordinator_status,
            methods=["GET"],
            name="coordinator_x_status",
        )
    )
    custom_routes.append(
        Route(
            coordinator_base_path + "/claim",
            coordinator_claim,
            methods=["POST"],
            name="coordinator_x_claim",
        )
    )
    custom_routes.append(
        Route(
            coordinator_base_path + "/ack",
            coordinator_ack,
            methods=["POST"],
            name="coordinator_x_ack",
        )
    )
    custom_routes.append(
        Route(
            coordinator_base_path + "/observed",
            coordinator_observed,
            methods=["POST"],
            name="coordinator_x_observed",
        )
    )
    custom_routes.append(
        Route(
            coordinator_base_path + "/preflight/authorize",
            coordinator_browser_preflight,
            methods=["POST"],
            name="coordinator_x_browser_preflight",
        )
    )
    custom_routes.append(
        Route(
            coordinator_base_path + "/discover",
            coordinator_discover_current_chat,
            methods=["POST", "OPTIONS"],
            name="coordinator_x_discover_current_chat",
        )
    )
    custom_routes.append(
        Route(
            coordinator_base_path + "/rollover/{action}",
            coordinator_rollover_control,
            methods=["POST"],
            name="coordinator_x_rollover_control",
        )
    )
    custom_routes.append(
        Route(
            coordinator_base_path + "/trigger",
            coordinator_trigger,
            methods=["POST"],
            name="coordinator_x_trigger",
        )
    )
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
    custom_routes.extend(create_operator_dashboard_routes(container, settings))
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
