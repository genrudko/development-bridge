from types import MappingProxyType

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import Capability
from app.projects import ProjectRegistry
from app.settings import BridgeSettings
from tests.fixtures.repositories import create_git_repository


def settings_for(repositories):
    return BridgeSettings.model_validate(
        {
            "version": 1,
            "projects": [
                {
                    "id": "project",
                    "name": "Project",
                    "repositories": [
                        {
                            "id": identifier,
                            "path": path,
                            "capabilities": {"read": True, "git_read": True},
                        }
                        for identifier, path in repositories.items()
                    ],
                }
            ],
        }
    )


def test_registers_two_repositories_without_current_workspace(tmp_path):
    first = create_git_repository(tmp_path, "first")
    second = create_git_repository(tmp_path, "second", branch="develop")
    registry = ProjectRegistry.from_settings(
        settings_for({"first": first, "second": second})
    )
    project = registry.get("project")
    assert [repository.id for repository in project.repositories] == ["first", "second"]
    assert registry.repositories.get("project", "second").root == second.resolve()
    assert registry.repositories.get("project", "first").capabilities.allows(
        Capability.GIT_READ
    )
    assert not hasattr(registry, "current_repository")


def test_unknown_project_has_stable_error_code(tmp_path):
    registry = ProjectRegistry.from_settings(BridgeSettings())
    with pytest.raises(BridgeError) as raised:
        registry.get("missing")
    assert raised.value.code is ErrorCode.PROJECT_NOT_FOUND


def test_unknown_repository_has_stable_error_code():
    registry = ProjectRegistry.from_settings(BridgeSettings())
    with pytest.raises(BridgeError) as raised:
        registry.repositories.get("project", "missing")
    assert raised.value.code is ErrorCode.REPOSITORY_NOT_FOUND


def test_rejects_non_git_directory(tmp_path):
    directory = tmp_path / "not-git"
    directory.mkdir()
    with pytest.raises(BridgeError) as raised:
        ProjectRegistry.from_settings(settings_for({"not-git": directory}))
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT
    assert str(directory) not in raised.value.message


def test_internal_project_mapping_is_read_only(tmp_path):
    repository = create_git_repository(tmp_path, "repository")
    registry = ProjectRegistry.from_settings(settings_for({"repository": repository}))
    assert isinstance(registry._projects, MappingProxyType)
    with pytest.raises(TypeError):
        registry._projects["other"] = registry.get("project")

