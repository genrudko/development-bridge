import pytest

from app.api.errors import BridgeError, ErrorCode
from app.container import build_container
from app.settings import load_settings
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

