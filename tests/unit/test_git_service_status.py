import subprocess

import pytest

from app.capabilities import CapabilityPolicy
from app.git import GitRunner, GitService
from app.projects import ProjectRegistry
from app.settings import BridgeSettings
from tests.fixtures.repositories import create_git_repository


def registry_for(repositories):
    settings = BridgeSettings.model_validate(
        {
            "projects": [
                {
                    "id": "project",
                    "name": "Project",
                    "repositories": [
                        {
                            "id": identifier,
                            "path": path,
                            "capabilities": {"git_read": True},
                        }
                        for identifier, path in repositories.items()
                    ],
                }
            ]
        }
    )
    return ProjectRegistry.from_settings(settings)


@pytest.mark.asyncio
async def test_reports_independent_repository_status(tmp_path):
    first = create_git_repository(tmp_path, "first")
    second = create_git_repository(tmp_path, "second", branch="develop")
    (first / "untracked.txt").write_text("new\n", encoding="utf-8")
    (second / "README.md").write_text("changed\n", encoding="utf-8")
    registry = registry_for({"first": first, "second": second})
    service = GitService(GitRunner(), CapabilityPolicy())

    first_status = await service.repository_status(
        registry.repositories.get("project", "first")
    )
    second_status = await service.repository_status(
        registry.repositories.get("project", "second")
    )

    assert first_status.branch == "main"
    assert first_status.untracked == 1
    assert first_status.unstaged == 0
    assert second_status.branch == "develop"
    assert second_status.untracked == 0
    assert second_status.unstaged == 1
    assert first_status.revision != second_status.revision


@pytest.mark.asyncio
async def test_reports_staged_changes(tmp_path):
    repository_path = create_git_repository(tmp_path, "repository")
    (repository_path / "staged.txt").write_text("staged\n", encoding="utf-8")
    subprocess.run(["git", "add", "staged.txt"], cwd=repository_path, check=True)
    registry = registry_for({"repository": repository_path})
    status = await GitService(GitRunner(), CapabilityPolicy()).repository_status(
        registry.repositories.get("project", "repository")
    )
    assert status.staged == 1
    assert status.dirty is True

