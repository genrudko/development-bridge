from pathlib import Path

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import CapabilitySet
from app.projects.models import Repository
import app.worktrees as worktrees


@pytest.mark.asyncio
async def test_worktree_branch_ambiguous_fails_closed(monkeypatch, tmp_path):
    branch="feature/dup"
    ref=f"refs/heads/{branch}"
    listing=(
        f"worktree {tmp_path / 'one'}\0branch {ref}\0\0"
        f"worktree {tmp_path / 'two'}\0branch {ref}\0\0"
    )
    async def fake_git(cwd, *arguments, check=True):
        if arguments[0] == "check-ref-format": return 0, "", ""
        if arguments[:2] == ("worktree", "list"): return 0, listing, ""
        raise AssertionError(arguments)
    monkeypatch.setattr(worktrees, "_git", fake_git)
    repo=Repository("p","r",tmp_path,CapabilitySet.from_mapping({"execute":True}))
    with pytest.raises(BridgeError) as exc:
        await worktrees.resolve_repository_worktree(repo, branch)
    assert exc.value.code is ErrorCode.REPOSITORY_CONFLICT
    assert exc.value.details.get("reason") == "ambiguous_worktree"


@pytest.mark.asyncio
async def test_worktree_identity_change_during_validation_fails_closed(monkeypatch, tmp_path):
    branch = "feature/racy"
    ref = f"refs/heads/{branch}"
    linked = tmp_path / "linked"
    linked.mkdir()
    common = tmp_path / ".git"
    common.mkdir()
    listing = f"worktree {linked}\0branch {ref}\0\0"
    state = {"branch": ref}

    async def fake_git(cwd, *arguments, check=True):
        if arguments[0] == "check-ref-format":
            return 0, "", ""
        if arguments[:2] == ("worktree", "list"):
            return 0, listing, ""
        if arguments == ("rev-parse", "--show-toplevel"):
            return 0, f"{linked}\n", ""
        if arguments == ("symbolic-ref", "-q", "HEAD"):
            observed = state["branch"]
            state["branch"] = "refs/heads/other"
            return 0, f"{observed}\n", ""
        if arguments == ("rev-parse", "--git-common-dir"):
            return 0, f"{common}\n", ""
        if arguments == ("rev-parse", "--show-toplevel", "--git-common-dir", "--symbolic-full-name", "HEAD"):
            return 0, f"{linked}\n{common}\nrefs/heads/other\n", ""
        raise AssertionError(arguments)

    monkeypatch.setattr(worktrees, "_git", fake_git)
    repo = Repository("p", "r", tmp_path, CapabilitySet.from_mapping({"execute": True}))
    with pytest.raises(BridgeError) as exc:
        await worktrees.resolve_repository_worktree(repo, branch)
    assert exc.value.code is ErrorCode.POLICY_VIOLATION
    assert exc.value.details.get("reason") == "worktree_branch_mismatch"


@pytest.mark.asyncio
async def test_worktree_replacement_during_final_canonical_inspection_fails_closed(monkeypatch, tmp_path):
    branch = "feature/replaced"
    ref = f"refs/heads/{branch}"
    linked = tmp_path / "linked"
    linked.mkdir()
    canonical_common = tmp_path / ".git"
    canonical_common.mkdir()
    foreign_common = tmp_path / "foreign.git"
    foreign_common.mkdir()
    listing = f"worktree {linked}\0branch {ref}\0\0"
    state = {"replaced": False}

    async def fake_git(cwd, *arguments, check=True):
        if arguments[0] == "check-ref-format":
            return 0, "", ""
        if arguments[:2] == ("worktree", "list"):
            return 0, listing, ""
        if cwd == linked and arguments == (
            "rev-parse", "--show-toplevel", "--git-common-dir", "--symbolic-full-name", "HEAD"
        ):
            common = foreign_common if state["replaced"] else canonical_common
            branch_out = "refs/heads/foreign" if state["replaced"] else ref
            return 0, f"{linked}\n{common}\n{branch_out}\n", ""
        if cwd == tmp_path and arguments == ("rev-parse", "--git-common-dir"):
            state["replaced"] = True
            return 0, f"{canonical_common}\n", ""
        raise AssertionError((cwd, arguments))

    monkeypatch.setattr(worktrees, "_git", fake_git)
    repo = Repository("p", "r", tmp_path, CapabilitySet.from_mapping({"execute": True}))
    with pytest.raises(BridgeError) as exc:
        await worktrees.resolve_repository_worktree(repo, branch)
    assert exc.value.code is ErrorCode.POLICY_VIOLATION
    assert exc.value.details.get("reason") in {"worktree_branch_mismatch", "foreign_worktree", "worktree_identity_changed"}
