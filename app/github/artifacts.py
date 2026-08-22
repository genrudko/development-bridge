from __future__ import annotations

import os
import hashlib
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.api.capability_exports import CapabilityExportRegistry
from app.api.errors import BridgeError, ErrorCode
from app.capabilities import Capability
from app.projects import Repository

from .service import GitHubHostService


@dataclass(frozen=True, slots=True)
class GitHubArtifactSnapshot:
    path: Path
    file_name: str
    media_type: str
    size_bytes: int
    sha256: str


class GitHubActionsArtifactExportService:
    def __init__(self, github: GitHubHostService, registry: CapabilityExportRegistry[GitHubArtifactSnapshot], root: Path, public_base_url: str | None, endpoint: str, max_bytes: int) -> None:
        self.github, self.registry = github, registry
        self.root = root.expanduser().resolve()
        self.public_base_url = public_base_url.rstrip("/") if public_base_url else None
        self.export_path = endpoint.rstrip("/") + "/github-actions-artifacts/exports"
        self.max_bytes = max_bytes

    async def export(self, repository: Repository, artifact_id: int) -> tuple[dict, GitHubArtifactSnapshot]:
        if self.public_base_url is None:
            raise BridgeError(ErrorCode.ARTIFACT_EXPORT_NOT_CONFIGURED, "server.public_base_url is required for GitHub artifact export")
        identity = await self.github.identity(repository)
        self.github._require(repository, Capability.GIT_READ)
        if self.github.transport is None:
            raise BridgeError(ErrorCode.GITHUB_NOT_CONFIGURED, "GitHub token is not configured")
        metadata, _ = await self.github._request(repository, "GET", f"/repos/{identity.slug}/actions/artifacts/{artifact_id}", write=False)
        if metadata.get("expired"):
            raise BridgeError(ErrorCode.GITHUB_REPOSITORY_UNAVAILABLE, "GitHub Actions artifact expired")
        declared_size = metadata.get("size_in_bytes")
        if isinstance(declared_size, int) and declared_size > self.max_bytes:
            raise BridgeError(
                ErrorCode.GITHUB_API_ERROR,
                "GitHub artifact exceeded the size limit",
            )
        safe_name = _artifact_file_name(metadata.get("name"), artifact_id)
        directory = self.root / repository.project_id / repository.id
        directory.mkdir(parents=True, exist_ok=True)
        final = directory / f"{artifact_id}.zip"
        reusable = False
        if final.is_symlink():
            final.unlink()
        elif final.is_file():
            actual_size = final.stat().st_size
            reusable = actual_size <= self.max_bytes and (
                not isinstance(declared_size, int) or actual_size == declared_size
            )
            if not reusable:
                final.unlink()
        elif final.exists():
            raise BridgeError(
                ErrorCode.GITHUB_API_ERROR,
                "GitHub artifact snapshot path is invalid",
            )
        if not reusable:
            descriptor, temporary_name = tempfile.mkstemp(prefix=".github-artifact-", dir=directory)
            os.close(descriptor)
            temporary = Path(temporary_name)
            temporary.unlink()
            try:
                size, sha256 = await self.github.transport.download_to(f"/repos/{identity.slug}/actions/artifacts/{artifact_id}/zip", temporary, self.max_bytes)
                os.chmod(temporary, 0o444)
                os.replace(temporary, final)
            finally:
                temporary.unlink(missing_ok=True)
        else:
            digest = hashlib.sha256()
            size = 0
            with final.open("rb") as artifact_file:
                while chunk := artifact_file.read(64 * 1024):
                    size += len(chunk)
                    digest.update(chunk)
            sha256 = "sha256:" + digest.hexdigest()
        snapshot = GitHubArtifactSnapshot(final, safe_name, "application/zip", size, sha256)
        token, grant = self.registry.issue(snapshot)
        return {"artifact_id": artifact_id, "file_name": safe_name, "media_type": snapshot.media_type, "size_bytes": size, "sha256": sha256, "export_url": f"{self.public_base_url}{self.export_path}/{token}", "expires_at": grant.expires_at.isoformat()}, snapshot

    def resolve(self, token: str) -> GitHubArtifactSnapshot | None:
        grant = self.registry.lookup(token)
        if grant is None:
            return None
        snapshot = grant.subject
        try:
            snapshot.path.relative_to(self.root)
            if snapshot.path.is_symlink() or not snapshot.path.is_file() or snapshot.path.stat().st_size != snapshot.size_bytes:
                return None
        except OSError:
            return None
        return snapshot


def _artifact_file_name(value: object, artifact_id: int) -> str:
    name = str(value or f"artifact-{artifact_id}")
    name = name.replace("/", "_").replace("\\", "_")
    name = re.sub(r"[\x00-\x1f\x7f]", "_", name).strip(" .")
    name = re.sub(r"(?:\.zip)+$", "", name, flags=re.IGNORECASE)
    name = name[:196].rstrip(" .") or f"artifact-{artifact_id}"
    return name + ".zip"
