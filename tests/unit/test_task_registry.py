import pytest

from app.api.errors import BridgeError, ErrorCode
from app.settings import BridgeSettings
from app.tasks import TaskRegistry


def configured_settings(tmp_path):
    return BridgeSettings.model_validate(
        {
            "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
            "projects": [
                {
                    "id": "project",
                    "name": "Project",
                    "repositories": [
                        {
                            "id": "repository",
                            "path": tmp_path,
                            "tasks": [
                                {
                                    "id": "test",
                                    "name": "Run tests",
                                    "executable": "pytest",
                                    "arguments": ["-q"],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )


def test_registry_is_repository_scoped_and_hides_command_details(tmp_path):
    registry = TaskRegistry.from_settings(configured_settings(tmp_path))

    profile = registry.get("project", "repository", "test")

    assert profile.arguments == ("-q",)
    assert profile.public_dict() == {
        "task_id": "test",
        "name": "Run tests",
        "timeout_seconds": 300.0,
        "output_limit_bytes": 262144,
        "artifacts": [],
    }
    assert registry.list("project", "other") == ()


def test_unknown_task_has_stable_error(tmp_path):
    registry = TaskRegistry.from_settings(configured_settings(tmp_path))

    with pytest.raises(BridgeError) as raised:
        registry.get("project", "repository", "missing")

    assert raised.value.code is ErrorCode.TASK_NOT_FOUND
