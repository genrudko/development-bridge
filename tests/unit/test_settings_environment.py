import pytest
from pydantic import ValidationError

from app.settings import load_settings


def test_environment_port_override_is_validated():
    with pytest.raises(ValidationError):
        load_settings(environ={"DEVELOPMENT_BRIDGE_PORT": "70000"})

