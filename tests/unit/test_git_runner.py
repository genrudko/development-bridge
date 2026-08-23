import pytest

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import CapabilitySet
from app.git import GitRunner
from app.projects import Repository
from tests.fixtures.repositories import create_git_repository


@pytest.mark.asyncio
async def test_runner_uses_registered_repository_root(tmp_path):
    root = create_git_repository(tmp_path, "repository")
    repository = Repository("project", "repository", root, CapabilitySet.from_mapping({}))
    result = await GitRunner().run(repository, ["rev-parse", "--show-toplevel"])
    assert result.stdout.strip() == str(root)


@pytest.mark.asyncio
async def test_runner_returns_structured_failure(tmp_path):
    root = create_git_repository(tmp_path, "repository")
    repository = Repository("project", "repository", root, CapabilitySet.from_mapping({}))
    with pytest.raises(BridgeError) as raised:
        await GitRunner().run(repository, ["rev-parse", "missing-ref"])
    assert raised.value.code is ErrorCode.GIT_COMMAND_FAILED
    assert "missing-ref" not in raised.value.message



@pytest.mark.asyncio
async def test_runner_applies_scoped_environment(tmp_path):
    root = create_git_repository(tmp_path, "repository")
    repository = Repository("project", "repository", root, CapabilitySet.from_mapping({}))

    result = await GitRunner().run(
        repository,
        ["var", "GIT_AUTHOR_IDENT"],
        environment={
            "GIT_AUTHOR_NAME": "Scoped Author",
            "GIT_AUTHOR_EMAIL": "scoped@example.test",
        },
    )

    assert "Scoped Author <scoped@example.test>" in result.stdout
