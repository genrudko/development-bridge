from __future__ import annotations

import time
from pathlib import PurePosixPath

from mcp.server import Server
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from app.api.context import new_request_context
from app.api.errors import BridgeError, ErrorCode
from app.audit import AuditEvent, AuditOutcome
from app.container import ApplicationContainer
from app.settings import BridgeSettings


def create_streamable_http_app(
    server: Server,
    settings: BridgeSettings,
    container: ApplicationContainer,
) -> Starlette:
    app = server.streamable_http_app(
        streamable_http_path=settings.server.endpoint,
        transport_security=TransportSecuritySettings(
            allowed_hosts=list(settings.server.allowed_hosts)
        ),
    )

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

    artifact_path = settings.server.endpoint.rstrip("/") + (
        "/artifacts/{project_id}/{repository_id}/{job_id}/{artifact_id}"
    )
    app.routes.append(
        Route(
            artifact_path,
            artifact_download,
            methods=["GET", "HEAD"],
            name="job_artifact_download",
        )
    )
    return app


def _host_allowed(host: str, settings: BridgeSettings) -> bool:
    host = host.casefold()
    for configured in settings.server.allowed_hosts:
        pattern = configured.casefold()
        if pattern == "*" or host == pattern:
            return True
        if pattern.endswith(":*") and host.split(":", 1)[0] == pattern[:-2]:
            return True
    return False
