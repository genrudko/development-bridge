from __future__ import annotations

import json
import subprocess

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import Capability
from app.container import build_container
from app.projects.managed import SubprocessManagedCloneRunner
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
    assert repository.capabilities.allows(Capability.GITHUB_CONTRIBUTE)
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
async def test_managed_clone_ref_is_persisted_and_part_of_idempotency(tmp_path):
    runner = FakeManagedCloneRunner()
    configured = settings(tmp_path)
    container = build_container(configured, managed_clone_runner=runner)

    cloned = await container.managed_repositories.clone(
        "project", "tagged", URL, depth=20, requested_ref="1.7"
    )
    repeated = await container.managed_repositories.clone(
        "project", "tagged", URL, depth=99, requested_ref="1.7"
    )
    assert cloned["requested_ref"] == repeated["requested_ref"] == "1.7"
    assert cloned["branch"] == "1.7"
    assert repeated["status"] == "already_present"
    assert runner.clone_calls[0][3] == "1.7"
    with pytest.raises(BridgeError) as changed:
        await container.managed_repositories.clone(
            "project", "tagged", URL, requested_ref="main"
        )
    assert changed.value.code is ErrorCode.REPOSITORY_CONFLICT

    rebuilt = build_container(configured, managed_clone_runner=runner)
    restored = await rebuilt.managed_repositories.clone(
        "project", "tagged", URL, requested_ref="1.7"
    )
    assert restored["status"] == "already_present"
    assert restored["requested_ref"] == "1.7"
    assert len(runner.clone_calls) == 1


@pytest.mark.asyncio
async def test_writable_fork_profile_and_remotes_persist_exactly(tmp_path):
    runner = FakeManagedCloneRunner()
    configured = settings(tmp_path)
    container = build_container(configured, managed_clone_runner=runner)
    cloned = await container.managed_repositories.clone(
        "project", "my-fork", "https://github.com/alice/reference.git",
        kind="fork", push_url="git@github.com:alice/reference.git",
        upstream_url=URL,
    )
    assert cloned["kind"] == "fork"
    assert cloned["capabilities"] == {
        "read": True, "write": True, "git_read": True, "git_write": True,
        "github_contribute": False, "execute": True,
    }
    root = tmp_path / "managed" / "project" / "my-fork"
    push = subprocess.run(
        ["git", "remote", "get-url", "--push", "origin"], cwd=root,
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    upstream = subprocess.run(
        ["git", "remote", "get-url", "upstream"], cwd=root,
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert push == "git@github.com:alice/reference.git"
    assert upstream == URL
    rebuilt = build_container(configured, managed_clone_runner=runner)
    assert rebuilt.projects.repositories.get(
        "project", "my-fork"
    ).capabilities.as_dict() == cloned["capabilities"]


@pytest.mark.asyncio
async def test_old_manifest_schema_loads_with_null_requested_ref(tmp_path):
    runner = FakeManagedCloneRunner()
    configured = settings(tmp_path)
    first = build_container(configured, managed_clone_runner=runner)
    await first.managed_repositories.clone("project", "legacy", URL)
    manifest_path = tmp_path / "managed" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["repositories"][0].pop("requested_ref")
    manifest["repositories"][0].pop("kind")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    rebuilt = build_container(configured, managed_clone_runner=runner)
    restored = await rebuilt.managed_repositories.clone("project", "legacy", URL)
    assert restored["status"] == "already_present"
    assert restored["requested_ref"] is None
    assert len(runner.clone_calls) == 1

    with pytest.raises(BridgeError) as changed:
        await rebuilt.managed_repositories.clone(
            "project", "legacy", URL, requested_ref="1.7"
        )
    assert changed.value.code is ErrorCode.REPOSITORY_CONFLICT


@pytest.mark.asyncio
async def test_clone_runner_uses_fixed_branch_argv(monkeypatch, tmp_path):
    runner = SubprocessManagedCloneRunner()
    calls = []

    async def capture(*arguments):
        calls.append(arguments)
        return ""

    monkeypatch.setattr(runner, "_run", capture)
    await runner.clone(URL, tmp_path / "destination", 20, "1.7")
    assert calls == [(
        "git", "clone", "--depth", "20", "--single-branch",
        "--branch", "1.7", "--", URL, str(tmp_path / "destination"),
    )]


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


@pytest.mark.asyncio
@pytest.mark.parametrize("requested_ref", [
    "", "-branch", "feature:target", "refs/*", "bad..ref", "bad ref",
    "bad\x00ref", "bad\nref", "@{previous}", ".hidden/main",
])
async def test_managed_clone_rejects_unsafe_refs(tmp_path, requested_ref):
    runner = FakeManagedCloneRunner()
    container = build_container(settings(tmp_path), managed_clone_runner=runner)
    with pytest.raises(BridgeError) as raised:
        await container.managed_repositories.clone(
            "project", "upstream", URL, requested_ref=requested_ref
        )
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
    assert set(schema["properties"]) == {
        "project_id", "repository_id", "url", "depth", "ref", "retention"
    }


@pytest.mark.asyncio
async def test_identical_reference_clone_reuses_existing_storage(tmp_path):
    runner = FakeManagedCloneRunner()
    configured = settings(tmp_path)
    container = build_container(configured, managed_clone_runner=runner)
    first = await container.managed_repositories.clone("project", "ref-a", URL, depth=20)
    second = await container.managed_repositories.clone("project", "ref-b", URL, depth=10)
    assert first["status"] == "cloned"
    assert second["status"] == "aliased"
    assert second["storage_repository_id"] == "ref-a"
    assert second["storage_shared"] is True
    a = container.projects.repositories.get("project", "ref-a")
    b = container.projects.repositories.get("project", "ref-b")
    assert a.root == b.root
    assert not (tmp_path / "managed" / "project" / "ref-b").exists()

    rebuilt = build_container(configured, managed_clone_runner=runner)
    restored = rebuilt.projects.repositories.get("project", "ref-b")
    assert restored.root == tmp_path / "managed" / "project" / "ref-a"


def test_manifest_alias_must_reference_canonical_same_origin(tmp_path):
    runner = FakeManagedCloneRunner()
    configured = settings(tmp_path)
    first = build_container(configured, managed_clone_runner=runner)
    import asyncio
    asyncio.run(first.managed_repositories.clone("project", "ref-a", URL))
    manifest_path = tmp_path / "managed" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    bad = dict(manifest["repositories"][0])
    bad["repository_id"] = "ref-b"
    bad["storage_repository_id"] = "missing"
    manifest["repositories"].append(bad)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(BridgeError) as raised:
        build_container(configured, managed_clone_runner=runner)
    assert raised.value.code is ErrorCode.MANAGED_REPOSITORY_STATE_CORRUPT

@pytest.mark.asyncio
async def test_managed_retention_tracks_access_and_plans_gc(tmp_path, monkeypatch):
    runner = FakeManagedCloneRunner()
    container = build_container(settings(tmp_path), managed_clone_runner=runner)
    cloned = await container.managed_repositories.clone(
        "project", "cache-one", URL, depth=12, retention="ephemeral"
    )
    assert cloned["retention"] == "ephemeral"
    assert cloned["last_used_at"] is not None

    # Simulate a stale last-use timestamp, then verify ordinary repository access refreshes it.
    record = container.managed_repositories._records[("project", "cache-one")]
    stale = "2020-01-01T00:00:00+00:00"
    updated = __import__("dataclasses").replace(record, last_used_at=stale)
    container.managed_repositories._records[("project", "cache-one")] = updated
    container.managed_repositories._write_manifest(container.managed_repositories._records)
    container.managed_repositories._last_access_touch.clear()
    container.projects.repositories.get("project", "cache-one")
    touched = container.managed_repositories._records[("project", "cache-one")]
    assert touched.last_used_at != stale

    await container.managed_repositories.set_retention("project", "cache-one", "pinned")
    pinned_plan = await container.managed_repositories.gc_plan(
        "project", cache_days=1, ephemeral_days=1
    )
    assert pinned_plan["candidate_count"] == 0
    assert any(
        "cache-one:pinned" in row.get("blocked_by", [])
        for row in pinned_plan["blocked_storage_groups"]
    )

    await container.managed_repositories.set_retention("project", "cache-one", "ephemeral")
    record = container.managed_repositories._records[("project", "cache-one")]
    container.managed_repositories._records[("project", "cache-one")] = __import__("dataclasses").replace(
        record, last_used_at=stale
    )
    container.managed_repositories._write_manifest(container.managed_repositories._records)
    plan = await container.managed_repositories.gc_plan(
        "project", cache_days=30, ephemeral_days=14
    )
    assert plan["candidate_count"] == 1
    assert plan["candidate_storage_groups"][0]["storage_repository_id"] == "cache-one"


@pytest.mark.asyncio
async def test_managed_forks_are_always_pinned(tmp_path):
    runner = FakeManagedCloneRunner()
    container = build_container(settings(tmp_path), managed_clone_runner=runner)
    cloned = await container.managed_repositories.clone(
        "project", "my-fork-retention", "https://github.com/alice/reference.git",
        kind="fork", push_url="git@github.com:alice/reference.git", upstream_url=URL,
    )
    assert cloned["retention"] == "pinned"
    with pytest.raises(BridgeError) as changed:
        await container.managed_repositories.set_retention(
            "project", "my-fork-retention", "ephemeral"
        )
    assert changed.value.code is ErrorCode.POLICY_VIOLATION

@pytest.mark.asyncio
async def test_identical_references_never_alias_across_projects(tmp_path):
    runner = FakeManagedCloneRunner()
    configured = BridgeSettings.model_validate({
        "managed_repositories": {"root": tmp_path / "managed"},
        "projects": [
            {"id": "first", "name": "First", "repositories": []},
            {"id": "second", "name": "Second", "repositories": []},
        ],
    })
    container = build_container(configured, managed_clone_runner=runner)
    first = await container.managed_repositories.clone("first", "same", URL, depth=20)
    second = await container.managed_repositories.clone("second", "same", URL, depth=20)
    assert first["storage_shared"] is False
    assert second["storage_shared"] is False
    assert (tmp_path / "managed" / "first" / "same" / ".git").is_dir()
    assert (tmp_path / "managed" / "second" / "same" / ".git").is_dir()


@pytest.mark.asyncio
async def test_gc_apply_removes_stale_clean_storage_group_and_all_aliases(tmp_path):
    from dataclasses import replace

    runner = FakeManagedCloneRunner()
    container = build_container(settings(tmp_path), managed_clone_runner=runner)
    await container.managed_repositories.clone(
        "project", "old-a", URL, depth=20, retention="ephemeral"
    )
    aliased = await container.managed_repositories.clone(
        "project", "old-b", URL, depth=10, retention="ephemeral"
    )
    assert aliased["storage_shared"] is True
    stale = "2020-01-01T00:00:00+00:00"
    for key, record in list(container.managed_repositories._records.items()):
        container.managed_repositories._records[key] = replace(record, last_used_at=stale)
    container.managed_repositories._write_manifest(container.managed_repositories._records)
    target = tmp_path / "managed" / "project" / "old-a"
    assert target.is_dir()

    applied = await container.managed_repositories.gc_apply(
        "project", ephemeral_days=14, cache_days=30, max_groups=4, confirm=True
    )
    assert applied["deleted_storage_groups"] == 1
    assert applied["deleted_logical_repositories"] == 2
    assert not target.exists()
    with pytest.raises(BridgeError) as missing:
        container.projects.repositories.get("project", "old-a")
    assert missing.value.code is ErrorCode.REPOSITORY_NOT_FOUND
    with pytest.raises(BridgeError):
        container.projects.repositories.get("project", "old-b")
    manifest = json.loads((tmp_path / "managed" / "manifest.json").read_text())
    assert manifest["repositories"] == []


@pytest.mark.asyncio
async def test_gc_apply_requires_explicit_confirmation(tmp_path):
    container = build_container(settings(tmp_path), managed_clone_runner=FakeManagedCloneRunner())
    with pytest.raises(BridgeError) as refused:
        await container.managed_repositories.gc_apply("project")
    assert refused.value.code is ErrorCode.POLICY_VIOLATION
