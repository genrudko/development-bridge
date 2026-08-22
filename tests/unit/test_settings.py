import pytest
from pydantic import ValidationError

from app.auth import create_owner_verifier
from app.settings import BridgeSettings, load_settings


def test_defaults_allow_startup_without_registered_projects():
    settings = load_settings(environ={})
    assert settings.version == 1
    assert settings.server.host == "127.0.0.1"
    assert settings.projects == ()


def test_loads_yaml_and_environment_server_overrides(tmp_path):
    config = tmp_path / "bridge.yaml"
    config.write_text(
        "version: 1\nserver:\n  name: test-bridge\nprojects: []\n",
        encoding="utf-8",
    )
    settings = load_settings(
        config,
        environ={
            "DEVELOPMENT_BRIDGE_HOST": "0.0.0.0",
            "DEVELOPMENT_BRIDGE_PORT": "9000",
        },
    )
    assert settings.server.name == "test-bridge"
    assert settings.server.host == "0.0.0.0"
    assert settings.server.port == 9000


@pytest.mark.parametrize("version", [0, 2])
def test_rejects_unknown_configuration_version(version):
    with pytest.raises(ValidationError):
        BridgeSettings.model_validate({"version": version})


def test_rejects_duplicate_project_ids():
    project = {"id": "duplicate", "name": "Duplicate"}
    with pytest.raises(ValidationError, match="duplicate project id"):
        BridgeSettings.model_validate({"version": 1, "projects": [project, project]})


def test_rejects_duplicate_repository_ids():
    repository = {"id": "repo", "path": "/tmp/repo"}
    with pytest.raises(ValidationError, match="duplicate repository id"):
        BridgeSettings.model_validate(
            {"version": 1, "projects": [{"id": "project", "name": "Project", "repositories": [repository, repository]}]}
        )


def test_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        BridgeSettings.model_validate({"version": 1, "unknown": True})


def test_task_profiles_require_a_durable_job_database(tmp_path):
    repository = {
        "id": "repo",
        "path": tmp_path,
        "tasks": [
            {"id": "test", "name": "Test", "executable": "pytest"}
        ],
    }
    with pytest.raises(ValidationError, match="jobs.database_path"):
        BridgeSettings.model_validate(
            {
                "projects": [
                    {"id": "project", "name": "Project", "repositories": [repository]}
                ]
            }
        )


def test_task_artifacts_require_external_storage_and_safe_unique_paths(tmp_path):
    task = {
        "id": "test",
        "name": "Test",
        "executable": "pytest",
        "artifacts": [
            {"id": "report", "path": "report.txt", "media_type": "text/plain"}
        ],
    }
    base = {
        "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
        "projects": [
            {
                "id": "project",
                "name": "Project",
                "repositories": [{"id": "repo", "path": tmp_path, "tasks": [task]}],
            }
        ],
    }

    with pytest.raises(ValidationError, match="jobs.artifact_directory"):
        BridgeSettings.model_validate(base)

    base["jobs"]["artifact_directory"] = tmp_path / "artifacts"
    task["artifacts"].append(
        {"id": "report", "path": "../escape", "media_type": "text/plain"}
    )
    with pytest.raises(ValidationError):
        BridgeSettings.model_validate(base)


def test_rejects_duplicate_task_ids(tmp_path):
    task = {"id": "test", "name": "Test", "executable": "pytest"}
    with pytest.raises(ValidationError, match="duplicate task id"):
        BridgeSettings.model_validate(
            {
                "jobs": {"database_path": tmp_path / "jobs.sqlite3"},
                "projects": [
                    {
                        "id": "project",
                        "name": "Project",
                        "repositories": [
                            {"id": "repo", "path": tmp_path, "tasks": [task, task]}
                        ],
                    }
                ],
            }
        )


def test_loads_owner_verifier_only_from_environment(tmp_path):
    config = tmp_path / "bridge.yaml"
    config.write_text(
        "version: 1\n"
        "oauth:\n"
        "  enabled: true\n"
        "  issuer_url: https://bridge.example\n"
        "  resource_url: https://bridge.example/mcp\n"
        f"  database_path: {tmp_path / 'oauth.sqlite3'}\n",
        encoding="utf-8",
    )
    verifier = create_owner_verifier("password")

    settings = load_settings(
        config, environ={"DEVELOPMENT_BRIDGE_OWNER_VERIFIER": verifier}
    )

    assert settings.oauth.owner_verifier is not None
    assert settings.oauth.owner_verifier.get_secret_value() == verifier
    assert "owner_verifier" not in settings.model_dump()["oauth"]


def test_rejects_owner_verifier_in_yaml(tmp_path):
    config = tmp_path / "bridge.yaml"
    config.write_text(
        "oauth:\n"
        "  enabled: true\n"
        "  issuer_url: https://bridge.example\n"
        "  resource_url: https://bridge.example/mcp\n"
        f"  database_path: {tmp_path / 'oauth.sqlite3'}\n"
        "  owner_verifier: secret\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="deployment environment"):
        load_settings(config, environ={})


@pytest.mark.parametrize(
    ("issuer", "resource"),
    [
        ("http://bridge.example", "http://bridge.example/mcp"),
        ("https://auth.example", "https://bridge.example/mcp"),
        ("https://bridge.example", "https://bridge.example/other"),
    ],
)
def test_rejects_inconsistent_remote_oauth_urls(tmp_path, issuer, resource):
    with pytest.raises(ValidationError):
        BridgeSettings.model_validate(
            {
                "oauth": {
                    "enabled": True,
                    "issuer_url": issuer,
                    "resource_url": resource,
                    "database_path": tmp_path / "oauth.sqlite3",
                }
            }
        )
