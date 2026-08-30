import pytest
from pydantic import ValidationError
from pathlib import Path

from app.auth import create_owner_verifier
from app.settings import BridgeSettings, load_settings


def test_antigravity_executor_is_disabled_by_default():
    settings = BridgeSettings()
    assert settings.executors.antigravity.enabled is False
    assert settings.executors.antigravity.executable == Path("~/.local/bin/agy")


def test_antigravity_executor_settings_are_bounded():
    settings = BridgeSettings.model_validate({"executors": {"antigravity": {
        "enabled": True, "executable": "/opt/agy/bin/agy",
        "probe_timeout_seconds": 12, "task_timeout_seconds": 600,
        "output_limit_bytes": 131072, "model": "gemini-3.1-pro",
    }}})
    assert settings.executors.antigravity.executable == Path("/opt/agy/bin/agy")
    assert settings.executors.antigravity.model == "gemini-3.1-pro"


@pytest.mark.parametrize("field,value", [
    ("probe_timeout_seconds", 0), ("task_timeout_seconds", 3601),
    ("output_limit_bytes", 1023), ("output_limit_bytes", 1048577),
])
def test_antigravity_executor_rejects_out_of_bounds_values(field, value):
    with pytest.raises(ValidationError):
        BridgeSettings.model_validate({"executors": {"antigravity": {field: value}}})


def test_defaults_allow_startup_without_registered_projects():
    settings = load_settings(environ={})
    assert settings.version == 1
    assert settings.server.host == "127.0.0.1"
    assert settings.projects == ()


def test_managed_repository_root_has_default_and_optional_override(tmp_path):
    assert BridgeSettings().managed_repositories.root.name == "repositories"
    settings = BridgeSettings.model_validate({
        "managed_repositories": {"root": tmp_path / "managed"}
    })
    assert settings.managed_repositories.root == tmp_path / "managed"


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


def test_public_base_url_is_an_optional_canonical_https_origin():
    assert BridgeSettings().server.public_base_url is None
    configured = BridgeSettings.model_validate({
        "server": {"public_base_url": "https://bridge.example"},
    })
    assert str(configured.server.public_base_url) == "https://bridge.example/"
    for invalid in (
        "http://bridge.example", "https://bridge.example/mcp",
        "https://bridge.example/?query=yes",
        "https://user:password@bridge.example",
    ):
        with pytest.raises(ValidationError):
            BridgeSettings.model_validate({"server": {"public_base_url": invalid}})


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


def test_loads_optional_knowledge_database_path(tmp_path):
    settings = BridgeSettings.model_validate(
        {"knowledge": {"database_path": tmp_path / "knowledge.sqlite3"}}
    )
    assert settings.knowledge.database_path == tmp_path / "knowledge.sqlite3"


def test_antigravity_quota_cache_defaults_and_bounds():
    settings = BridgeSettings().executors.antigravity
    assert settings.quota_cache_path == Path("~/.local/state/development-bridge/antigravity-quota.json")
    assert settings.quota_cache_max_age_seconds == 120
    with pytest.raises(ValidationError):
        BridgeSettings.model_validate({"executors": {"antigravity": {"quota_cache_max_age_seconds": 0}}})
