from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from app.api.capability_exports import CapabilityExportRegistry
from app.api.errors import BridgeError, ErrorCode
from app.projects import ProjectRegistry, Repository

from .models import JobArtifact
from .service import JobService


@dataclass(frozen=True, slots=True)
class JobArtifactExportSubject:
    project_id: str
    repository_id: str
    job_id: str
    artifact_id: str


class JobArtifactExportService:
    def __init__(
        self,
        jobs: JobService,
        projects: ProjectRegistry,
        registry: CapabilityExportRegistry[JobArtifactExportSubject],
        public_base_url: str | None,
        endpoint: str,
    ) -> None:
        self.jobs = jobs
        self.projects = projects
        self.registry = registry
        self.public_base_url = public_base_url.rstrip("/") if public_base_url else None
        self.export_path = endpoint.rstrip("/") + "/job-artifacts/exports"

    def export(
        self, repository: Repository, job_id: str, artifact_id: str
    ) -> tuple[dict, JobArtifact, Path]:
        if self.public_base_url is None:
            raise BridgeError(
                ErrorCode.ARTIFACT_EXPORT_NOT_CONFIGURED,
                "server.public_base_url is required for job artifact export",
            )
        artifact, path = self.jobs.artifact_file(repository, job_id, artifact_id)
        assert artifact.size_bytes is not None
        assert artifact.sha256 is not None
        token, grant = self.registry.issue(JobArtifactExportSubject(
            repository.project_id,
            repository.id,
            job_id,
            artifact_id,
        ))
        file_name = PurePosixPath(artifact.path).name
        data = {
            "job_id": job_id,
            "artifact": artifact.public_dict(),
            "file_name": file_name,
            "media_type": artifact.media_type,
            "size_bytes": artifact.size_bytes,
            "sha256": artifact.sha256,
            "export_url": (
                f"{self.public_base_url}{self.export_path}/{quote(token, safe='')}"
            ),
            "expires_at": grant.expires_at.isoformat(),
        }
        return data, artifact, path

    def resolve(self, token: str) -> tuple[JobArtifact, Path] | None:
        grant = self.registry.lookup(token)
        if grant is None:
            return None
        subject = grant.subject
        try:
            repository = self.projects.repositories.get(
                subject.project_id, subject.repository_id
            )
            return self.jobs.artifact_file(
                repository, subject.job_id, subject.artifact_id
            )
        except (BridgeError, OSError):
            return None
