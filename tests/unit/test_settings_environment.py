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
