import pytest
from pydantic import ValidationError

from app.settings import load_settings


def test_environment_port_override_is_validated():
    with pytest.raises(ValidationError):
        load_settings(environ={"DEVELOPMENT_BRIDGE_PORT": "70000"})


def test_telegram_credentials_and_session_path_can_come_from_environment(tmp_path):
    settings = load_settings(environ={
        "DEVELOPMENT_BRIDGE_TELEGRAM_API_ID": "12345",
        "DEVELOPMENT_BRIDGE_TELEGRAM_API_HASH": "secret-hash",
        "DEVELOPMENT_BRIDGE_TELEGRAM_SESSION_PATH": str(tmp_path / "telegram.session"),
    })
    telegram = settings.knowledge.telegram
    assert telegram.api_id == 12345
    assert telegram.api_hash.get_secret_value() == "secret-hash"
    assert telegram.session_path == tmp_path / "telegram.session"


def test_github_token_survives_other_environment_overrides():
    settings = load_settings(environ={
        "DEVELOPMENT_BRIDGE_GITHUB_TOKEN": "github-secret",
        "DEVELOPMENT_BRIDGE_TELEGRAM_API_ID": "12345",
        "DEVELOPMENT_BRIDGE_TELEGRAM_API_HASH": "telegram-secret",
    })

    assert settings.github.token is not None
    assert settings.github.token.get_secret_value() == "github-secret"
    assert "github-secret" not in repr(settings)


def test_github_primary_and_classic_tokens_are_environment_only_and_secret():
    settings = load_settings(environ={
        "DEVELOPMENT_BRIDGE_GITHUB_TOKEN": "primary-secret",
        "DEVELOPMENT_BRIDGE_GITHUB_CLASSIC_TOKEN": "classic-secret",
    })

    assert settings.github.token.get_secret_value() == "primary-secret"
    assert settings.github.classic_token.get_secret_value() == "classic-secret"
    dumped = settings.model_dump()
    assert "token" not in dumped["github"]
    assert "classic_token" not in dumped["github"]
    for secret in ("primary-secret", "classic-secret"):
        assert secret not in repr(settings)
        assert secret not in repr(dumped)


def test_owner_verifier_survives_github_environment_override():
    settings = load_settings(environ={
        "DEVELOPMENT_BRIDGE_OWNER_VERIFIER": "owner-secret",
        "DEVELOPMENT_BRIDGE_GITHUB_TOKEN": "github-secret",
        "DEVELOPMENT_BRIDGE_TELEGRAM_API_ID": "12345",
        "DEVELOPMENT_BRIDGE_TELEGRAM_API_HASH": "telegram-secret",
    })

    assert settings.oauth.owner_verifier is not None
    assert settings.oauth.owner_verifier.get_secret_value() == "owner-secret"
    assert settings.github.token is not None
    assert settings.github.token.get_secret_value() == "github-secret"
    assert "owner-secret" not in repr(settings)
    assert "github-secret" not in repr(settings)


def test_all_secret_environment_values_survive_combined_overrides(tmp_path):
    config = tmp_path / "bridge.yaml"
    config.write_text(
        """version: 1
server:
  public_base_url: https://bridge.example
oauth:
  enabled: true
  issuer_url: https://bridge.example
  resource_url: https://bridge.example/mcp
  database_path: oauth.sqlite3
""",
        encoding="utf-8",
    )
    settings = load_settings(config, environ={
        "DEVELOPMENT_BRIDGE_HOST": "0.0.0.0",
        "DEVELOPMENT_BRIDGE_PORT": "9443",
        "DEVELOPMENT_BRIDGE_X_TRIGGER_TOKEN": "x-secret",
        "DEVELOPMENT_BRIDGE_TELEGRAM_API_ID": "12345",
        "DEVELOPMENT_BRIDGE_TELEGRAM_API_HASH": "telegram-secret",
        "DEVELOPMENT_BRIDGE_TELEGRAM_SESSION_PATH": str(tmp_path / "telegram.session"),
        "DEVELOPMENT_BRIDGE_GITHUB_TOKEN": "github-secret",
        "DEVELOPMENT_BRIDGE_OWNER_VERIFIER": "owner-secret",
    })

    assert settings.server.host == "0.0.0.0"
    assert settings.server.port == 9443
    assert settings.server.x_trigger_token.get_secret_value() == "x-secret"
    assert settings.knowledge.telegram.api_hash.get_secret_value() == "telegram-secret"
    assert settings.github.token.get_secret_value() == "github-secret"
    assert settings.oauth.owner_verifier.get_secret_value() == "owner-secret"
    dumped = settings.model_dump()
    assert "x_trigger_token" not in dumped["server"]
    for secret in ("x-secret", "telegram-secret", "github-secret", "owner-secret"):
        assert secret not in repr(settings)
        assert secret not in repr(dumped)


def test_rejects_x_trigger_token_in_yaml(tmp_path):
    config = tmp_path / "bridge.yaml"
    config.write_text("server:\n  x_trigger_token: forbidden\n", encoding="utf-8")

    with pytest.raises(ValueError, match="X trigger token"):
        load_settings(config, environ={})


@pytest.mark.parametrize("field", ["token", "classic_token"])
def test_rejects_github_tokens_in_yaml(tmp_path, field):
    config = tmp_path / "bridge.yaml"
    config.write_text(f"github:\n  {field}: forbidden\n", encoding="utf-8")

    with pytest.raises(ValueError, match="GitHub tokens"):
        load_settings(config, environ={})
