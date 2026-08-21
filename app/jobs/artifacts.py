from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from pathlib import Path, PurePosixPath

from app.projects import Repository
from app.tasks import ArtifactDeclaration, TaskProfile

from .models import JobArtifact, JobRecord


class ArtifactStorage:
    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    def capture(
        self, job: JobRecord, profile: TaskProfile, repository: Repository
    ) -> tuple[JobArtifact, ...]:
        return tuple(
            self._capture_one(job, declaration, repository)
            for declaration in profile.artifacts
        )

    def path_for(self, artifact: JobArtifact) -> Path:
        if not artifact.available or artifact.storage_path is None:
            raise FileNotFoundError(artifact.artifact_id)
        path = Path(artifact.storage_path)
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            raise FileNotFoundError(artifact.artifact_id) from exc
        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError(artifact.artifact_id)
        return path

    def _capture_one(
        self,
        job: JobRecord,
        declaration: ArtifactDeclaration,
        repository: Repository,
    ) -> JobArtifact:
        unavailable = lambda error: JobArtifact(
            job.job_id,
            declaration.id,
            declaration.path,
            declaration.media_type,
            declaration.required,
            False,
            error=error,
        )
        relative = PurePosixPath(declaration.path)
        source = repository.root.joinpath(*relative.parts)
        current = repository.root
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                return unavailable("symlink")
        try:
            source_stat = source.stat()
        except FileNotFoundError:
            return unavailable("missing")
        except OSError:
            return unavailable("unreadable")
        if not stat.S_ISREG(source_stat.st_mode):
            return unavailable("not_regular_file")
        if source_stat.st_size > declaration.max_bytes:
            return unavailable("too_large")

        directory = (
            self._root
            / job.project_id
            / job.repository_id
            / job.job_id
        )
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / declaration.id
        if destination.exists():
            return unavailable("snapshot_exists")
        descriptor, temporary_name = tempfile.mkstemp(prefix=".artifact-", dir=directory)
        temporary = Path(temporary_name)
        digest = hashlib.sha256()
        copied = 0
        try:
            with source.open("rb") as input_file, os.fdopen(descriptor, "wb") as output_file:
                while chunk := input_file.read(64 * 1024):
                    copied += len(chunk)
                    if copied > declaration.max_bytes:
                        return unavailable("too_large")
                    digest.update(chunk)
                    output_file.write(chunk)
                output_file.flush()
                os.fsync(output_file.fileno())
            final_stat = source.stat()
            if (
                final_stat.st_dev != source_stat.st_dev
                or final_stat.st_ino != source_stat.st_ino
                or final_stat.st_size != source_stat.st_size
                or final_stat.st_mtime_ns != source_stat.st_mtime_ns
            ):
                return unavailable("changed_during_capture")
            os.chmod(temporary, 0o444)
            os.replace(temporary, destination)
            return JobArtifact(
                job.job_id,
                declaration.id,
                declaration.path,
                declaration.media_type,
                declaration.required,
                True,
                copied,
                "sha256:" + digest.hexdigest(),
                str(destination),
            )
        except OSError:
            return unavailable("unreadable")
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
