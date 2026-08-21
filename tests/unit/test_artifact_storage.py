from __future__ import annotations

from dataclasses import replace

from app.jobs import ArtifactStorage, JobRecord, JobStatus
from app.projects import ProjectRegistry
from app.settings import BridgeSettings
from app.tasks import TaskRegistry
from tests.fixtures.repositories import create_git_repository


def configured(tmp_path, artifacts):
    root = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate(
        {
            "jobs": {
                "database_path": tmp_path / "jobs.sqlite3",
                "artifact_directory": tmp_path / "artifacts",
            },
            "projects": [
                {
                    "id": "project",
                    "name": "Project",
                    "repositories": [
                        {
                            "id": "repository",
                            "path": root,
                            "tasks": [
                                {
                                    "id": "task",
                                    "name": "Task",
                                    "executable": "true",
                                    "artifacts": artifacts,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )
    repository = ProjectRegistry.from_settings(settings).repositories.get(
        "project", "repository"
    )
    profile = TaskRegistry.from_settings(settings).get("project", "repository", "task")
    job = JobRecord(
        "job_" + "1" * 32,
        "project",
        "repository",
        "task",
        "req_1",
        JobStatus.SUCCEEDED,
        "2026-08-22T00:00:00+00:00",
    )
    return ArtifactStorage(settings.jobs.artifact_directory), repository, profile, job


def test_capture_creates_immutable_snapshot_with_digest(tmp_path):
    storage, repository, profile, job = configured(
        tmp_path,
        [{"id": "report", "path": "report.txt", "media_type": "text/plain"}],
    )
    source = repository.root / "report.txt"
    source.write_text("first", encoding="utf-8")

    artifact = storage.capture(job, profile, repository)[0]
    source.write_text("second", encoding="utf-8")

    assert artifact.available is True
    assert artifact.size_bytes == 5
    assert artifact.sha256 == (
        "sha256:a7937b64b8caa58f03721bb6bacf5c78c"
        "b235febe0e70b1b84cd99541461a08e"
    )
    assert storage.path_for(artifact).read_text(encoding="utf-8") == "first"


def test_capture_reports_missing_oversized_and_symlink_artifacts(tmp_path):
    storage, repository, profile, job = configured(
        tmp_path,
        [
            {"id": "missing", "path": "missing.txt", "media_type": "text/plain"},
            {
                "id": "large",
                "path": "large.txt",
                "media_type": "text/plain",
                "max_bytes": 3,
            },
            {"id": "link", "path": "link.txt", "media_type": "text/plain"},
        ],
    )
    (repository.root / "large.txt").write_text("large", encoding="utf-8")
    (repository.root / "target.txt").write_text("target", encoding="utf-8")
    (repository.root / "link.txt").symlink_to("target.txt")

    artifacts = storage.capture(job, profile, repository)

    assert [(artifact.artifact_id, artifact.error) for artifact in artifacts] == [
        ("missing", "missing"),
        ("large", "too_large"),
        ("link", "symlink"),
    ]
    assert all(not artifact.available for artifact in artifacts)


def test_path_for_rejects_storage_path_outside_root(tmp_path):
    storage, repository, profile, job = configured(
        tmp_path,
        [{"id": "report", "path": "report.txt", "media_type": "text/plain"}],
    )
    (repository.root / "report.txt").write_text("report", encoding="utf-8")
    artifact = storage.capture(job, profile, repository)[0]

    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    invalid = replace(artifact, storage_path=str(outside))

    try:
        storage.path_for(invalid)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("outside storage path was accepted")
