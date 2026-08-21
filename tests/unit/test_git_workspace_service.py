from __future__ import annotations

import subprocess

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import CapabilityPolicy, CapabilitySet
from app.changes import ChangeRevisionCalculator
from app.git import GitRunner, GitWorkspaceService
from app.projects import Repository, RepositoryMutationLock
from tests.fixtures.repositories import create_git_repository


def configured(root, *, writable=True):
    return Repository(
        "engineering",
        "service",
        root,
        CapabilitySet.from_mapping({"git_write": writable}),
    )


def service():
    runner = GitRunner()
    return GitWorkspaceService(
        runner,
        CapabilityPolicy(),
        ChangeRevisionCalculator(runner),
        RepositoryMutationLock(),
    )


def git(root, *arguments):
    return subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def remote_fixture(tmp_path, root):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", remote], check=True, capture_output=True)
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "--set-upstream", "origin", "main")
    return remote


@pytest.mark.asyncio
async def test_create_and_switch_local_branch(tmp_path):
    root = create_git_repository(tmp_path, "service")
    workspace = service()
    repository = configured(root)
    head = git(root, "rev-parse", "HEAD")

    created = await workspace.branch_create(
        repository, branch="feature/artifacts", expected_head=head
    )
    assert created.branch == "feature/artifacts"
    assert created.current_branch == "main"

    switched = await workspace.branch_switch(repository, branch="feature/artifacts")
    assert switched.previous_branch == "main"
    assert switched.branch == "feature/artifacts"
    assert git(root, "branch", "--show-current") == "feature/artifacts"


@pytest.mark.asyncio
async def test_switch_rejects_dirty_repository_and_revision_drift(tmp_path):
    root = create_git_repository(tmp_path, "service")
    workspace = service()
    repository = configured(root)
    await workspace.branch_create(repository, branch="feature")
    (root / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(BridgeError) as dirty:
        await workspace.branch_switch(repository, branch="feature")
    assert dirty.value.code is ErrorCode.GIT_WORKTREE_DIRTY

    (root / "dirty.txt").unlink()
    with pytest.raises(BridgeError) as drift:
        await workspace.branch_switch(
            repository,
            branch="feature",
            expected_revision="sha256:" + "0" * 64,
        )
    assert drift.value.code is ErrorCode.REVISION_CONFLICT


@pytest.mark.asyncio
async def test_fetch_and_fast_forward_from_upstream(tmp_path):
    root = create_git_repository(tmp_path, "service")
    remote = remote_fixture(tmp_path, root)
    publisher = tmp_path / "publisher"
    subprocess.run(["git", "clone", remote, publisher], check=True, capture_output=True)
    git(publisher, "config", "user.name", "Publisher")
    git(publisher, "config", "user.email", "publisher@example.invalid")
    git(publisher, "switch", "main")
    (publisher / "upstream.txt").write_text("upstream\n", encoding="utf-8")
    git(publisher, "add", "upstream.txt")
    git(publisher, "commit", "-m", "Upstream change")
    target = git(publisher, "rev-parse", "HEAD")
    git(publisher, "push", "origin", "main")

    workspace = service()
    repository = configured(root)
    fetched = await workspace.fetch(repository)
    assert fetched.remote == "origin"
    assert any(update.ref == "refs/remotes/origin/main" for update in fetched.updated_refs)
    advanced = await workspace.fast_forward(repository)
    assert advanced.status == "fast_forwarded"
    assert advanced.commits_applied == 1
    assert advanced.head == target
    assert (root / "upstream.txt").read_text(encoding="utf-8") == "upstream\n"


@pytest.mark.asyncio
async def test_fast_forward_rejects_diverged_branch(tmp_path):
    root = create_git_repository(tmp_path, "service")
    remote_fixture(tmp_path, root)
    (root / "local.txt").write_text("local\n", encoding="utf-8")
    git(root, "add", "local.txt")
    git(root, "commit", "-m", "Local")

    with pytest.raises(BridgeError) as raised:
        await service().fast_forward(configured(root))
    assert raised.value.code is ErrorCode.GIT_FAST_FORWARD_REJECTED


@pytest.mark.asyncio
async def test_git_write_capability_is_required(tmp_path):
    root = create_git_repository(tmp_path, "service")
    with pytest.raises(BridgeError) as raised:
        await service().branch_create(configured(root, writable=False), branch="feature")
    assert raised.value.code is ErrorCode.PERMISSION_DENIED
