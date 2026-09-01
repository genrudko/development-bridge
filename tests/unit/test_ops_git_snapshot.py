import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.git.runner import GitRunner
from app.ops.git_snapshot import GitSnapshotProvider
from app.projects.models import Repository


@pytest.fixture
def repo(tmp_path):
    return Repository(
        project_id="test-proj",
        id="test-repo",
        root=tmp_path / "repo",
        capabilities={"git_read": True},
    )


@pytest.mark.asyncio
async def test_git_snapshot_parses_status_and_head(repo):
    runner = MagicMock(spec=GitRunner)
    status_mock = MagicMock(
        returncode=0,
        stdout="## main...origin/main [ahead 2, behind 1]\n M file1.py\n?? file2.py\nA  file3.py\n",
        stderr="",
    )
    head_mock = MagicMock(
        returncode=0,
        stdout="a1b2c3d4e5f678901234567890abcdef12345678\n",
        stderr="",
    )
    runner.run = AsyncMock(side_effect=[status_mock, head_mock])

    provider = GitSnapshotProvider(runner=runner, cache_ttl_seconds=5.0)
    snap = await provider.snapshot(repo)

    assert snap["project_id"] == "test-proj"
    assert snap["repository_id"] == "test-repo"
    assert snap["branch"] == "main"
    assert snap["upstream"] == "origin/main"
    assert snap["ahead"] == 2
    assert snap["behind"] == 1
    assert snap["head"] == "a1b2c3d4e5f678901234567890abcdef12345678"
    assert snap["head_short"] == "a1b2c3d"
    assert snap["clean"] is False
    assert snap["dirty"] is True
    assert snap["changed_files_count"] == 3


@pytest.mark.asyncio
async def test_git_snapshot_caches_for_ttl(repo):
    runner = MagicMock(spec=GitRunner)
    status_mock = MagicMock(returncode=0, stdout="## main\n", stderr="")
    head_mock = MagicMock(returncode=0, stdout="abc1234\n", stderr="")
    runner.run = AsyncMock(side_effect=[status_mock, head_mock])

    provider = GitSnapshotProvider(runner=runner, cache_ttl_seconds=10.0)
    snap1 = await provider.snapshot(repo)
    snap2 = await provider.snapshot(repo)

    assert snap1 == snap2
    assert runner.run.call_count == 2  # Only called for first snapshot


@pytest.mark.asyncio
async def test_git_snapshot_no_branch_clean(repo):
    runner = MagicMock(spec=GitRunner)
    status_mock = MagicMock(returncode=0, stdout="## HEAD (no branch)\n", stderr="")
    head_mock = MagicMock(returncode=0, stdout="deadbeef123456\n", stderr="")
    runner.run = AsyncMock(side_effect=[status_mock, head_mock])

    provider = GitSnapshotProvider(runner=runner, cache_ttl_seconds=5.0)
    snap = await provider.snapshot(repo)

    assert snap["branch"] is None
    assert snap["upstream"] is None
    assert snap["ahead"] == 0
    assert snap["behind"] == 0
    assert snap["clean"] is True
    assert snap["dirty"] is False
    assert snap["changed_files_count"] == 0
