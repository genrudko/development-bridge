from __future__ import annotations

import subprocess

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import CapabilityPolicy, CapabilitySet
from app.git import GitRunner, GitService
from app.projects import Repository
from tests.fixtures.repositories import create_git_repository


def configured_repository(root, *, readable=True):
    return Repository(
        project_id="engineering",
        id="service",
        root=root,
        capabilities=CapabilitySet.from_mapping({"git_read": readable}),
    )


def commit(repository, path, content, message):
    (repository / path).write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", path], cwd=repository, check=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.asyncio
async def test_log_is_structured_and_reports_truncation(tmp_path):
    root = create_git_repository(tmp_path, "service")
    commit(root, "second.txt", "second\n", "Second commit")
    service = GitService(GitRunner(), CapabilityPolicy())

    result = await service.log(configured_repository(root), max_count=1)

    assert result.truncated is True
    assert len(result.commits) == 1
    assert result.commits[0].subject == "Second commit"
    assert len(result.commits[0].sha) == 40


@pytest.mark.asyncio
async def test_show_returns_commit_and_bounded_patch(tmp_path):
    root = create_git_repository(tmp_path, "service")
    commit(root, "shown.txt", "shown\n", "Shown commit")

    result = await GitService(GitRunner(), CapabilityPolicy()).show(
        configured_repository(root), "HEAD"
    )

    assert result.commit.subject == "Shown commit"
    assert "shown.txt" in result.patch.text
    assert result.patch.truncated is False


@pytest.mark.asyncio
async def test_show_truncates_large_patches_explicitly(tmp_path):
    root = create_git_repository(tmp_path, "service")
    commit(root, "large.txt", "x" * 300_000 + "\n", "Large commit")

    result = await GitService(GitRunner(), CapabilityPolicy()).show(
        configured_repository(root), "HEAD"
    )

    assert result.patch.truncated is True
    assert len(result.patch.text.encode("utf-8")) <= GitService.MAX_PATCH_BYTES


@pytest.mark.asyncio
async def test_diff_supports_working_staged_and_range_modes(tmp_path):
    root = create_git_repository(tmp_path, "service")
    initial = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    commit(root, "range.txt", "range\n", "Range commit")
    (root / "README.md").write_text("working\n", encoding="utf-8")
    (root / "staged.txt").write_text("staged\n", encoding="utf-8")
    subprocess.run(["git", "add", "staged.txt"], cwd=root, check=True)
    service = GitService(GitRunner(), CapabilityPolicy())
    repository = configured_repository(root)

    working = await service.diff(repository)
    staged = await service.diff(repository, mode="staged")
    ranged = await service.diff(repository, mode="range", base=initial, target="HEAD")

    assert [file.path for file in working.files] == ["README.md"]
    assert [file.path for file in staged.files] == ["staged.txt"]
    assert [file.path for file in ranged.files] == ["range.txt"]
    assert working.mode == "working"


@pytest.mark.asyncio
async def test_refs_are_structured_and_filterable(tmp_path):
    root = create_git_repository(tmp_path, "service")
    subprocess.run(["git", "tag", "v1"], cwd=root, check=True)
    service = GitService(GitRunner(), CapabilityPolicy())
    repository = configured_repository(root)

    heads = await service.refs(repository, kind="heads")
    tags = await service.refs(repository, kind="tags")

    assert [(ref.name, ref.short_name) for ref in heads.refs] == [
        ("refs/heads/main", "main")
    ]
    assert [(ref.name, ref.short_name) for ref in tags.refs] == [
        ("refs/tags/v1", "v1")
    ]


@pytest.mark.asyncio
async def test_missing_revision_has_a_stable_error(tmp_path):
    root = create_git_repository(tmp_path, "service")

    with pytest.raises(BridgeError) as raised:
        await GitService(GitRunner(), CapabilityPolicy()).show(
            configured_repository(root), "missing"
        )

    assert raised.value.code is ErrorCode.GIT_REVISION_NOT_FOUND
    assert raised.value.details["revision"] == "missing"


@pytest.mark.asyncio
async def test_revision_cannot_be_interpreted_as_a_git_option(tmp_path):
    root = create_git_repository(tmp_path, "service")

    with pytest.raises(BridgeError) as raised:
        await GitService(GitRunner(), CapabilityPolicy()).show(
            configured_repository(root), "--help"
        )

    assert raised.value.code is ErrorCode.GIT_REVISION_NOT_FOUND


@pytest.mark.asyncio
async def test_log_rejects_counts_outside_the_contract(tmp_path):
    root = create_git_repository(tmp_path, "service")
    service = GitService(GitRunner(), CapabilityPolicy())

    for max_count in (0, service.MAX_LOG_COUNT + 1):
        with pytest.raises(BridgeError) as raised:
            await service.log(configured_repository(root), max_count=max_count)
        assert raised.value.code is ErrorCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_git_read_capability_is_required(tmp_path):
    root = create_git_repository(tmp_path, "service")

    with pytest.raises(BridgeError) as raised:
        await GitService(GitRunner(), CapabilityPolicy()).refs(
            configured_repository(root, readable=False)
        )

    assert raised.value.code is ErrorCode.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_diff_rejects_unsafe_paths_and_invalid_ranges(tmp_path):
    root = create_git_repository(tmp_path, "service")
    service = GitService(GitRunner(), CapabilityPolicy())
    repository = configured_repository(root)

    with pytest.raises(BridgeError) as unsafe:
        await service.diff(repository, path="../outside")
    with pytest.raises(BridgeError) as incomplete:
        await service.diff(repository, mode="range", base="HEAD")

    assert unsafe.value.code is ErrorCode.POLICY_VIOLATION
    assert incomplete.value.code is ErrorCode.INVALID_ARGUMENT
