from __future__ import annotations

import subprocess

import pytest

from app.capabilities import CapabilityPolicy, CapabilitySet
from app.changes import ChangeRevisionCalculator, ChangeService
from app.git import GitRunner
from app.projects import Repository
from tests.fixtures.repositories import create_git_repository


def repository(root) -> Repository:
    return Repository(
        project_id="engineering",
        id="service",
        root=root,
        capabilities=CapabilitySet.from_mapping({"write": True}),
    )


def calculator() -> ChangeRevisionCalculator:
    return ChangeRevisionCalculator(GitRunner())


@pytest.mark.asyncio
async def test_large_ignored_content_does_not_affect_revision_or_plan(tmp_path):
    root = create_git_repository(tmp_path, "service")
    (root / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore"], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Ignore virtual environment"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    ignored = root / ".venv" / "large.bin"
    ignored.parent.mkdir()
    with ignored.open("wb") as target:
        target.truncate(65 * 1024 * 1024)
    revisions = calculator()
    before = await revisions.calculate(repository(root))

    with ignored.open("r+b") as target:
        target.write(b"changed")
    after = await revisions.calculate(repository(root))
    plan = await ChangeService(CapabilityPolicy(), revisions).plan(
        repository(root),
        [{"type": "create", "path": "new.txt", "content": "new\n"}],
    )

    assert before == after == plan.base_revision
    assert revisions.MAX_BYTES == 256 * 1024 * 1024


@pytest.mark.asyncio
async def test_tracked_worktree_change_changes_revision(tmp_path):
    root = create_git_repository(tmp_path, "service")
    revisions = calculator()
    before = await revisions.calculate(repository(root))

    (root / "README.md").write_text("changed\n", encoding="utf-8")

    assert await revisions.calculate(repository(root)) != before


@pytest.mark.asyncio
async def test_untracked_file_and_its_content_change_revision(tmp_path):
    root = create_git_repository(tmp_path, "service")
    revisions = calculator()
    initial = await revisions.calculate(repository(root))

    untracked = root / "untracked.txt"
    untracked.write_text("one\n", encoding="utf-8")
    created = await revisions.calculate(repository(root))
    untracked.write_text("two\n", encoding="utf-8")
    changed = await revisions.calculate(repository(root))
    untracked.unlink()

    assert len({initial, created, changed}) == 3
    assert await revisions.calculate(repository(root)) == initial


@pytest.mark.asyncio
async def test_staged_index_change_changes_revision(tmp_path):
    root = create_git_repository(tmp_path, "service")
    revisions = calculator()
    before = await revisions.calculate(repository(root))

    (root / "staged.txt").write_text("staged\n", encoding="utf-8")
    subprocess.run(["git", "add", "staged.txt"], cwd=root, check=True)

    assert await revisions.calculate(repository(root)) != before
