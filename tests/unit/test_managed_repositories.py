from __future__ import annotations

import json

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import Capability
from app.container import build_container
from app.settings import BridgeSettings
from tests.fixtures.managed_clone import FakeManagedCloneRunner
from tests.fixtures.repositories import create_git_repository


URL = "https://github.com/example/reference.git"


def settings(tmp_path, repositories=()):
    return BridgeSettings.model_validate({
        "managed_repositories": {"root": tmp_path / "managed"},
        "projects": [{
            "id": "project",
            "name": "Project",
            "repositories": repositories,
        }],
    })


@pytest.mark.asyncio
async def test_managed_clone_is_idempotent_and_persists_across_container_rebuild(tmp_path):
    runner = FakeManagedCloneRunner()
    configured = settings(tmp_path)
    first = build_container(configured, managed_clone_runner=runner)

    cloned = await first.managed_repositories.clone(
        "project", "upstream", URL, depth=12
    )
    present = await first.managed_repositories.clone(
        "project", "upstream", URL, depth=99
    )

    assert cloned["status"] == "cloned"
    assert cloned["depth"] == 12
    assert present["status"] == "already_present"
    assert present["depth"] == 12
    assert len(runner.clone_calls) == 1
    repository = first.projects.repositories.get("project", "upstream")
    assert repository.capabilities.allows(Capability.READ)
    assert repository.capabilities.allows(Capability.GIT_READ)
    assert not repository.capabilities.allows(Capability.WRITE)
    assert not repository.capabilities.allows(Capability.GIT_WRITE)
    assert not repository.capabilities.allows(Capability.EXECUTE)
    assert [repo.id for repo in first.projects.get("project").repositories] == [
        "upstream"
    ]

    rebuilt = build_container(configured, managed_clone_runner=runner)
    restored = rebuilt.projects.repositories.get("project", "upstream")
    assert restored.root == tmp_path / "managed" / "project" / "upstream"
    assert len(runner.clone_calls) == 1


@pytest.mark.asyncio
async def test_managed_clone_conflicts_are_fail_closed(tmp_path):
    configured_root = create_git_repository(tmp_path, "configured")
    configured = settings(tmp_path, [{
        "id": "configured",
        "path": configured_root,
        "capabilities": {"read": True},
    }])
    container = build_container(
        configured, managed_clone_runner=FakeManagedCloneRunner()
    )
    with pytest.raises(BridgeError) as occupied:
        await container.managed_repositories.clone("project", "configured", URL)
    assert occupied.value.code is ErrorCode.REPOSITORY_CONFLICT

    await container.managed_repositories.clone("project", "managed", URL)
    with pytest.raises(BridgeError) as different:
        await container.managed_repositories.clone(
            "project", "managed", "https://github.com/other/repository.git"
        )
    assert different.value.code is ErrorCode.REPOSITORY_CONFLICT


@pytest.mark.asyncio
async def test_failed_clone_leaves_no_registry_manifest_target_or_temporary_data(tmp_path):
    container = build_container(
        settings(tmp_path), managed_clone_runner=FakeManagedCloneRunner(fail=True)
    )
    with pytest.raises(BridgeError) as raised:
        await container.managed_repositories.clone("project", "failed", URL)
    assert raised.value.code is ErrorCode.REPOSITORY_CLONE_FAILED
    with pytest.raises(BridgeError) as missing:
        container.projects.repositories.get("project", "failed")
    assert missing.value.code is ErrorCode.REPOSITORY_NOT_FOUND
    assert not (tmp_path / "managed" / "manifest.json").exists()
    assert not (tmp_path / "managed" / "project" / "failed").exists()
    assert not list((tmp_path / "managed" / "project").glob(".clone-*"))


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "file:///tmp/repository",
    "ssh://git@example.com/repository.git",
    "git@github.com:example/repository.git",
    "https://user:password@example.com/repository.git",
    "https://example.com/repository.git?token=secret",
    "https://example.com/repository.git#main",
])
async def test_managed_clone_rejects_unsafe_urls_without_calling_runner(tmp_path, url):
    runner = FakeManagedCloneRunner()
    container = build_container(settings(tmp_path), managed_clone_runner=runner)
    with pytest.raises(BridgeError) as raised:
        await container.managed_repositories.clone("project", "upstream", url)
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT
    assert runner.clone_calls == []


def test_manifest_path_is_not_authority_and_malformed_entry_fails_closed(tmp_path):
    managed = tmp_path / "managed"
    managed.mkdir()
    outside = create_git_repository(tmp_path, "outside")
    (managed / "manifest.json").write_text(json.dumps({"repositories": [{
        "project_id": "project",
        "repository_id": "upstream",
        "origin_url": URL,
        "depth": 50,
        "created_at": "2026-08-23T00:00:00+00:00",
        "path": str(outside),
    }]}), encoding="utf-8")

    with pytest.raises(BridgeError) as raised:
        build_container(settings(tmp_path), managed_clone_runner=FakeManagedCloneRunner())
    assert raised.value.code is ErrorCode.MANAGED_REPOSITORY_STATE_CORRUPT


def test_clone_tool_identity_schema_prevents_traversal(tmp_path):
    from app.tools.registry import build_tool_registry

    container = build_container(settings(tmp_path))
    schema = build_tool_registry(container).get("repository_clone").definition.input_schema
    assert schema["properties"]["project_id"]["pattern"] == "^[a-z][a-z0-9-]{0,62}$"
    assert schema["properties"]["repository_id"]["pattern"] == "^[a-z][a-z0-9-]{0,62}$"
    assert set(schema["properties"]) == {"project_id", "repository_id", "url", "depth"}
