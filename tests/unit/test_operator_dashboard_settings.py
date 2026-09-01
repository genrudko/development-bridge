import pytest
from pydantic import ValidationError

from app.settings import BridgeSettings, OperatorDashboardSettings, load_settings


def test_operator_dashboard_settings_defaults():
    settings = BridgeSettings()
    ops = settings.operator_dashboard
    assert ops.enabled is False
    assert ops.path == "/ops"
    assert ops.password_hash is None
    assert ops.session_secret is None
    assert ops.session_ttl_seconds == 43200
    assert ops.event_interval_seconds == 1.0
    assert ops.recent_jobs_limit == 25
    assert ops.terminal_tail_bytes == 32768


def test_operator_dashboard_fails_closed_when_enabled_without_secrets():
    with pytest.raises(ValueError, match="enabled operator_dashboard requires"):
        BridgeSettings.model_validate({"operator_dashboard": {"enabled": True}})

    with pytest.raises(ValueError, match="enabled operator_dashboard requires"):
        BridgeSettings.model_validate({
            "operator_dashboard": {
                "enabled": True,
                "password_hash": "scrypt$16384$8$1$salt$digest",
            }
        })

    with pytest.raises(ValueError, match="enabled operator_dashboard requires"):
        BridgeSettings.model_validate({
            "operator_dashboard": {
                "enabled": True,
                "session_secret": "my-secret",
            }
        })


def test_operator_dashboard_succeeds_when_enabled_with_both_secrets():
    settings = BridgeSettings.model_validate({
        "operator_dashboard": {
            "enabled": True,
            "password_hash": "scrypt$16384$8$1$salt$digest",
            "session_secret": "my-session-secret",
        }
    })
    ops = settings.operator_dashboard
    assert ops.enabled is True
    assert ops.password_hash is not None
    assert ops.password_hash.get_secret_value() == "scrypt$16384$8$1$salt$digest"
    assert ops.session_secret is not None
    assert ops.session_secret.get_secret_value() == "my-session-secret"
    assert "scrypt$16384$8$1$salt$digest" not in repr(settings)
    assert "my-session-secret" not in repr(settings)


@pytest.mark.parametrize("field,value", [
    ("session_ttl_seconds", 59),
    ("session_ttl_seconds", 604801),
    ("event_interval_seconds", 0.05),
    ("event_interval_seconds", 61.0),
    ("recent_jobs_limit", 0),
    ("recent_jobs_limit", 201),
    ("terminal_tail_bytes", 1023),
    ("terminal_tail_bytes", 1048577),
])
def test_operator_dashboard_settings_bounds(field, value):
    with pytest.raises(ValidationError):
        OperatorDashboardSettings.model_validate({field: value})


def test_rejects_operator_dashboard_secrets_in_yaml(tmp_path):
    config = tmp_path / "bridge.yaml"
    config.write_text("operator_dashboard:\n  password_hash: forbidden\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Operator dashboard secrets"):
        load_settings(config, environ={})

    config.write_text("operator_dashboard:\n  session_secret: forbidden\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Operator dashboard secrets"):
        load_settings(config, environ={})


def test_operator_dashboard_environment_overrides(tmp_path):
    config = tmp_path / "bridge.yaml"
    config.write_text(
        """version: 1
operator_dashboard:
  path: /ops
  session_ttl_seconds: 7200
  event_interval_seconds: 2.0
  recent_jobs_limit: 50
  terminal_tail_bytes: 65536
""",
        encoding="utf-8",
    )
    settings = load_settings(
        config,
        environ={
            "DEVELOPMENT_BRIDGE_OPERATOR_DASHBOARD_ENABLED": "true",
            "DEVELOPMENT_BRIDGE_OPERATOR_DASHBOARD_PASSWORD_HASH": "scrypt$16384$8$1$salt$digest",
            "DEVELOPMENT_BRIDGE_OPERATOR_DASHBOARD_SESSION_SECRET": "test-session-secret",
            "DEVELOPMENT_BRIDGE_OPERATOR_DASHBOARD_RECENT_JOBS_LIMIT": "30",
        },
    )
    ops = settings.operator_dashboard
    assert ops.enabled is True
    assert ops.path == "/ops"
    assert ops.session_ttl_seconds == 7200
    assert ops.event_interval_seconds == 2.0
    assert ops.recent_jobs_limit == 30
    assert ops.terminal_tail_bytes == 65536
    assert ops.password_hash.get_secret_value() == "scrypt$16384$8$1$salt$digest"
    assert ops.session_secret.get_secret_value() == "test-session-secret"
