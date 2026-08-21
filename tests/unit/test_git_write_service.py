from __future__ import annotations

import subprocess

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import CapabilityPolicy, CapabilitySet
from app.changes import ChangeRevisionCalculator
from app.git import GitRunner, GitWriteService
from app.projects import Repository, RepositoryMutationLock
from tests.fixtures.repositories import create_git_repository


def repository(root, *, writable=True):
    return Repository(
        project_id="engineering",
        id="service",
        root=root,
        capabilities=CapabilitySet.from_mapping({"git_write": writable}),
    )


def service():
    runner = GitRunner()
    return GitWriteService(
        runner,
        CapabilityPolicy(),
        ChangeRevisionCalculator(runner),
        RepositoryMutationLock(),
    )


def git(root, *arguments):
    return subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.mark.asyncio
async def test_stage_explicit_paths_and_optional_revision_guard(tmp_path):
    root = create_git_repository(tmp_path, "service")
    (root / "README.md").write_text("changed\n", encoding="utf-8")
    (root / "ignored.txt").write_text("ignored\n", encoding="utf-8")
    write = service()

    result = await write.stage(repository(root), ["README.md"])

    assert result.previous_revision != result.revision
    assert result.paths == ("README.md",)
    assert result.staged_files == 1
    assert git(root, "diff", "--cached", "--name-only") == "README.md"
    assert "ignored.txt" in git(root, "status", "--short")

    with pytest.raises(BridgeError) as raised:
        await write.stage(
            repository(root), ["ignored.txt"], base_revision="sha256:" + "0" * 64
        )
    assert raised.value.code is ErrorCode.REVISION_CONFLICT


@pytest.mark.asyncio
async def test_stage_supports_deletion_and_rejects_unsafe_paths(tmp_path):
    root = create_git_repository(tmp_path, "service")
    (root / "README.md").unlink()
    write = service()

    result = await write.stage(repository(root), ["README.md"])
    assert result.staged_files == 1
    assert git(root, "diff", "--cached", "--name-status") == "D\tREADME.md"

    with pytest.raises(BridgeError) as raised:
        await write.stage(repository(root), [".git/config"])
    assert raised.value.code is ErrorCode.POLICY_VIOLATION


@pytest.mark.asyncio
async def test_commit_uses_only_prepared_index_with_optional_guards(tmp_path):
    root = create_git_repository(tmp_path, "service")
    (root / "staged.txt").write_text("staged\n", encoding="utf-8")
    (root / "unstaged.txt").write_text("unstaged\n", encoding="utf-8")
    write = service()
    staged = await write.stage(repository(root), ["staged.txt"])

    result = await write.commit(
        repository(root),
        message="Add staged file",
        idempotency_key="commit-one",
        expected_head=staged.head,
        expected_index_revision=staged.index_revision,
    )

    assert result.status == "committed"
    assert git(root, "show", "--format=", "--name-only", "HEAD") == "staged.txt"
    assert (root / "unstaged.txt").exists()
    retry = await service().commit(
        repository(root),
        message="Add staged file",
        idempotency_key="commit-one",
        expected_head=staged.head,
        expected_index_revision=staged.index_revision,
    )
    # Guards are part of the idempotent payload, so an exact retry includes them.
    assert retry.status == "already_committed"


@pytest.mark.asyncio
async def test_commit_without_guards_and_empty_index_failure(tmp_path):
    root = create_git_repository(tmp_path, "service")
    (root / "new.txt").write_text("new\n", encoding="utf-8")
    write = service()
    await write.stage(repository(root), ["new.txt"])
    committed = await write.commit(
        repository(root), message="Add new", idempotency_key="unguarded"
    )
    assert committed.status == "committed"

    with pytest.raises(BridgeError) as raised:
        await write.commit(
            repository(root), message="Empty", idempotency_key="empty"
        )
    assert raised.value.code is ErrorCode.GIT_INDEX_EMPTY


@pytest.mark.asyncio
async def test_commit_idempotency_conflict(tmp_path):
    root = create_git_repository(tmp_path, "service")
    (root / "new.txt").write_text("new\n", encoding="utf-8")
    write = service()
    await write.stage(repository(root), ["new.txt"])
    await write.commit(repository(root), message="First", idempotency_key="same")

    with pytest.raises(BridgeError) as raised:
        await write.commit(repository(root), message="Different", idempotency_key="same")
    assert raised.value.code is ErrorCode.IDEMPOTENCY_CONFLICT


@pytest.mark.asyncio
async def test_push_plan_and_push_create_then_update_remote_branch(tmp_path):
    root = create_git_repository(tmp_path, "service")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", remote], check=True, capture_output=True)
    git(root, "remote", "add", "origin", str(remote))
    write = service()

    create = await write.push_plan(
        repository(root), remote="origin", remote_branch="main"
    )
    assert create.action == "create"
    assert create.remote_head is None
    assert create.commit_count == 1
    pushed = await write.push(
        repository(root),
        plan_id=create.plan_id,
        local_branch=create.local_branch,
        local_head=create.local_head,
        remote=create.remote,
        remote_branch=create.remote_branch,
        remote_head=create.remote_head,
        set_upstream=True,
        idempotency_key="push-create",
    )
    assert pushed.status == "pushed"
    assert pushed.upstream == "origin/main"

    (root / "next.txt").write_text("next\n", encoding="utf-8")
    staged = await write.stage(repository(root), ["next.txt"])
    await write.commit(
        repository(root),
        message="Next",
        idempotency_key="commit-next",
        expected_index_revision=staged.index_revision,
    )
    update = await write.push_plan(repository(root))
    assert update.action == "update"
    assert update.fast_forward is True
    assert update.commit_count == 1


@pytest.mark.asyncio
async def test_push_rejects_remote_drift_and_is_idempotent(tmp_path):
    root = create_git_repository(tmp_path, "service")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", remote], check=True, capture_output=True)
    git(root, "remote", "add", "origin", str(remote))
    write = service()
    plan = await write.push_plan(repository(root), remote="origin", remote_branch="main")
    arguments = dict(
        plan_id=plan.plan_id,
        local_branch=plan.local_branch,
        local_head=plan.local_head,
        remote=plan.remote,
        remote_branch=plan.remote_branch,
        remote_head=plan.remote_head,
        set_upstream=True,
        idempotency_key="push-once",
    )
    first = await write.push(repository(root), **arguments)
    second = await service().push(repository(root), **arguments)
    assert first.status == "pushed"
    assert second.status == "already_pushed"

    (root / "later.txt").write_text("later\n", encoding="utf-8")
    await write.stage(repository(root), ["later.txt"])
    await write.commit(repository(root), message="Later", idempotency_key="later")
    stale = await write.push_plan(repository(root))
    git(root, "push", "origin", "HEAD:main")
    with pytest.raises(BridgeError) as raised:
        await write.push(
            repository(root),
            plan_id=stale.plan_id,
            local_branch=stale.local_branch,
            local_head=stale.local_head,
            remote=stale.remote,
            remote_branch=stale.remote_branch,
            remote_head=stale.remote_head,
            set_upstream=False,
            idempotency_key="stale",
        )
    assert raised.value.code is ErrorCode.GIT_PUSH_PLAN_INVALID


@pytest.mark.asyncio
async def test_git_write_capability_is_required(tmp_path):
    root = create_git_repository(tmp_path, "service")
    with pytest.raises(BridgeError) as raised:
        await service().stage(repository(root, writable=False), ["README.md"])
    assert raised.value.code is ErrorCode.PERMISSION_DENIED
