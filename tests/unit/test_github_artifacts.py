from __future__ import annotations

import os
import subprocess

import pytest

from app.api.capability_exports import CapabilityExportRegistry
from app.capabilities import CapabilityPolicy, CapabilitySet
from app.git import GitRunner
from app.github import (
    GitHubActionsArtifactExportService,
    GitHubArtifactSnapshot,
    GitHubHostService,
)
from app.projects import Repository
from tests.fixtures.github_transport import FakeGitHubTransport
from tests.fixtures.repositories import create_git_repository


def artifact_service(tmp_path):
    root = create_git_repository(tmp_path, "repo")
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/acme/widgets.git"],
        cwd=root,
        check=True,
    )
    repository = Repository(
        "project",
        "repo",
        root,
        CapabilitySet.from_mapping({"git_read": True}),
    )
    transport = FakeGitHubTransport()
    service = GitHubActionsArtifactExportService(
        GitHubHostService(GitRunner(), CapabilityPolicy(), transport),
        CapabilityExportRegistry[GitHubArtifactSnapshot](600),
        tmp_path / "snapshots",
        "https://bridge.example",
        "/mcp",
        1024,
    )
    return repository, transport, service


def add_metadata(transport, content, name="build", count=1):
    for _ in range(count):
        transport.add(
            "GET",
            "/repos/acme/widgets/actions/artifacts/8",
            {
                "id": 8,
                "name": name,
                "size_in_bytes": len(content),
                "expired": False,
            },
        )
    transport.downloads["/repos/acme/widgets/actions/artifacts/8/zip"] = content


@pytest.mark.asyncio
async def test_correct_size_cached_artifact_is_reused(tmp_path):
    repository, transport, service = artifact_service(tmp_path)
    content = b"correct archive"
    add_metadata(transport, content, count=2)

    _, first = await service.export(repository, 8)
    _, second = await service.export(repository, 8)

    assert first.path == second.path
    assert second.path.read_bytes() == content
    assert transport.download_calls == [
        "/repos/acme/widgets/actions/artifacts/8/zip"
    ]


@pytest.mark.asyncio
async def test_wrong_size_cached_artifact_is_atomically_replaced(tmp_path):
    repository, transport, service = artifact_service(tmp_path)
    content = b"replacement archive"
    add_metadata(transport, content, count=2)
    _, snapshot = await service.export(repository, 8)
    os.chmod(snapshot.path, 0o644)
    snapshot.path.write_bytes(b"broken")

    _, repaired = await service.export(repository, 8)

    assert repaired.path.read_bytes() == content
    assert len(transport.download_calls) == 2


@pytest.mark.asyncio
async def test_cached_symlink_is_never_served(tmp_path):
    repository, transport, service = artifact_service(tmp_path)
    content = b"safe archive"
    add_metadata(transport, content)
    permanent = tmp_path / "snapshots" / "project" / "repo" / "8.zip"
    permanent.parent.mkdir(parents=True)
    outside = tmp_path / "outside.zip"
    outside.write_bytes(b"unsafe bytes")
    permanent.symlink_to(outside)

    _, snapshot = await service.export(repository, 8)

    assert not snapshot.path.is_symlink()
    assert snapshot.path.read_bytes() == content
    assert outside.read_bytes() == b"unsafe bytes"


@pytest.mark.asyncio
async def test_artifact_download_name_is_safe_bounded_and_has_one_zip_suffix(tmp_path):
    repository, transport, service = artifact_service(tmp_path)
    content = b"archive"
    add_metadata(
        transport,
        content,
        name="folder\\subdir/bad\r\nname" + "x" * 300 + ".zip.zip",
    )

    data, snapshot = await service.export(repository, 8)

    assert "/" not in snapshot.file_name and "\\" not in snapshot.file_name
    assert "\r" not in snapshot.file_name and "\n" not in snapshot.file_name
    assert len(snapshot.file_name) <= 200
    assert snapshot.file_name.lower().endswith(".zip")
    assert not snapshot.file_name.lower().endswith(".zip.zip")
    assert data["file_name"] == snapshot.file_name
