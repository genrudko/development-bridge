import pytest

from app.api.errors import BridgeError, ErrorCode
from app.auth import create_owner_verifier
from app.container import build_container
from app.settings import BridgeSettings, load_settings
from tests.fixtures.repositories import create_git_repository
from tests.fixtures.settings import write_bridge_config


def test_yaml_startup_registers_two_repositories(tmp_path):
    first = create_git_repository(tmp_path, "first")
    second = create_git_repository(tmp_path, "second")
    config = write_bridge_config(
        tmp_path / "bridge.yaml", {"first": first, "second": second}
    )
    container = build_container(load_settings(config, environ={}))
    project = container.projects.get("test-project")
    assert [repository.id for repository in project.repositories] == ["first", "second"]


def test_invalid_repository_stops_container_construction(tmp_path):
    invalid = tmp_path / "not-a-repository"
    invalid.mkdir()
    config = write_bridge_config(
        tmp_path / "bridge.yaml", {"invalid": invalid}
    )
    with pytest.raises(BridgeError) as raised:
        build_container(load_settings(config, environ={}))
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT


def test_job_database_inside_repository_is_rejected(tmp_path):
    repository = create_git_repository(tmp_path, "repository")
    settings = {
        "jobs": {"database_path": repository / ".bridge" / "jobs.sqlite3"},
        "projects": [
            {
                "id": "project",
                "name": "Project",
                "repositories": [
                    {
                        "id": "repository",
                        "path": repository,
                        "tasks": [
                            {"id": "test", "name": "Test", "executable": "pytest"}
                        ],
                    }
                ],
            }
        ],
    }

    with pytest.raises(BridgeError) as raised:
        build_container(BridgeSettings.model_validate(settings))

    assert raised.value.code is ErrorCode.INVALID_ARGUMENT


def test_oauth_database_inside_repository_is_rejected(tmp_path):
    repository = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate(
        {
            "oauth": {
                "enabled": True,
                "issuer_url": "https://bridge.example",
                "resource_url": "https://bridge.example/mcp",
                "database_path": repository / ".bridge" / "oauth.sqlite3",
                "owner_verifier": create_owner_verifier("password"),
            },
            "projects": [
                {
                    "id": "project",
                    "name": "Project",
                    "repositories": [{"id": "repository", "path": repository}],
                }
            ],
        }
    )

    with pytest.raises(BridgeError) as raised:
        build_container(settings)

    assert raised.value.code is ErrorCode.INVALID_ARGUMENT


def test_enabled_oauth_requires_owner_verifier_at_startup(tmp_path):
    settings = BridgeSettings.model_validate(
        {
            "oauth": {
                "enabled": True,
                "issuer_url": "https://bridge.example",
                "resource_url": "https://bridge.example/mcp",
                "database_path": tmp_path / "oauth.sqlite3",
            }
        }
    )

    with pytest.raises(BridgeError, match="DEVELOPMENT_BRIDGE_OWNER_VERIFIER"):
        build_container(settings)


def test_knowledge_database_inside_repository_is_rejected(tmp_path):
    repository = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate(
        {
            "knowledge": {"database_path": repository / ".bridge" / "knowledge.sqlite3"},
            "projects": [
                {
                    "id": "project",
                    "name": "Project",
                    "repositories": [{"id": "repository", "path": repository}],
                }
            ],
        }
    )
    with pytest.raises(BridgeError) as raised:
        build_container(settings)
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT


def test_telegram_session_inside_repository_is_rejected(tmp_path):
    repository = create_git_repository(tmp_path, "repository")
    settings = BridgeSettings.model_validate(
        {
            "knowledge": {
                "database_path": tmp_path / "knowledge.sqlite3",
                "telegram": {
                    "api_id": 12345,
                    "api_hash": "secret",
                    "session_path": repository / "telegram.session",
                },
            },
            "projects": [
                {
                    "id": "project", "name": "Project",
                    "repositories": [{"id": "repository", "path": repository}],
                }
            ],
        }
    )
    with pytest.raises(BridgeError) as raised:
        build_container(settings)
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT
