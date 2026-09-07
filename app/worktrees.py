from __future__ import annotations

import asyncio
from pathlib import Path

from app.api.errors import BridgeError, ErrorCode
from app.projects.models import Repository


async def _git(cwd: Path, *arguments: str, check: bool = True) -> tuple[int, str, str]:
    try:
        process = await asyncio.create_subprocess_exec(
            "git", *arguments, cwd=cwd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise BridgeError(ErrorCode.GIT_COMMAND_FAILED, "Git worktree inspection failed") from exc
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise BridgeError(
            ErrorCode.GIT_COMMAND_FAILED,
            "Git worktree inspection timed out",
            retryable=True,
        ) from exc
    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")
    if len(stdout) + len(stderr) > 1_048_576:
        raise BridgeError(ErrorCode.GIT_COMMAND_FAILED, "Git worktree inspection output exceeded limit")
    if check and process.returncode != 0:
        raise BridgeError(
            ErrorCode.GIT_COMMAND_FAILED,
            "Git worktree inspection failed",
            details={"returncode": process.returncode},
        )
    return process.returncode or 0, out, err


def _parse_worktree_porcelain_z(text: str) -> tuple[dict[str, object], ...]:
    records: list[dict[str, object]] = []
    current: dict[str, object] = {}
    for field in text.split("\0"):
        if not field:
            if current:
                records.append(current)
                current = {}
            continue
        key, separator, value = field.partition(" ")
        if key == "worktree":
            if current:
                records.append(current)
            current = {"worktree": value if separator else ""}
        elif key == "branch":
            current["branch"] = value if separator else ""
        elif key == "detached":
            current["detached"] = True
    if current:
        records.append(current)
    return tuple(records)


def _reported_path(cwd: Path, value: str) -> Path:
    path = Path(value.strip())
    if not path.is_absolute():
        path = cwd / path
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "Git worktree path is unavailable",
            details={"reason": "worktree_path_unavailable"},
        ) from exc


async def resolve_repository_worktree(repository: Repository, branch: str) -> Path:
    if not isinstance(branch, str) or not branch or "\0" in branch or len(branch) > 1024:
        raise BridgeError(
            ErrorCode.INVALID_ARGUMENT,
            "worktree_branch is invalid",
            details={"reason": "invalid_worktree_branch"},
        )
    expected_ref = f"refs/heads/{branch}"
    try:
        canonical = Path(repository.root).resolve(strict=True)
    except OSError as exc:
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "Registered repository root is unavailable",
            details={"reason": "repository_root_unavailable"},
        ) from exc
    if not canonical.is_dir():
        raise BridgeError(ErrorCode.POLICY_VIOLATION, "Registered repository root is not a directory")
    rc, _, _ = await _git(canonical, "check-ref-format", expected_ref, check=False)
    if rc != 0:
        raise BridgeError(
            ErrorCode.INVALID_ARGUMENT,
            "worktree_branch is invalid",
            details={"reason": "invalid_worktree_branch", "worktree_branch": branch},
        )

    _, listing, _ = await _git(canonical, "worktree", "list", "--porcelain", "-z")
    matches = [
        record for record in _parse_worktree_porcelain_z(listing)
        if record.get("branch") == expected_ref and not record.get("detached")
    ]
    if not matches:
        raise BridgeError(
            ErrorCode.GIT_BRANCH_NOT_FOUND,
            "No existing worktree is checked out on worktree_branch",
            details={"reason": "worktree_not_found", "worktree_branch": branch},
        )
    if len(matches) != 1:
        raise BridgeError(
            ErrorCode.REPOSITORY_CONFLICT,
            "worktree_branch resolves to multiple worktrees",
            details={"reason": "ambiguous_worktree", "worktree_branch": branch},
        )

    raw_value = str(matches[0].get("worktree") or "")
    raw_path = Path(raw_value)
    if not raw_path.is_absolute() or raw_path.is_symlink():
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "Selected worktree path is unsafe",
            details={"reason": "unsafe_worktree_path"},
        )
    candidate = _reported_path(canonical, raw_value)
    if raw_path != candidate:
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "Selected worktree path contains a symlink or path alias",
            details={"reason": "unsafe_worktree_path"},
        )
    if not candidate.is_dir():
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "Selected worktree is not a directory",
            details={"reason": "unsafe_worktree_path"},
        )

    try:
        initial_stat = candidate.stat()
        initial_identity = (initial_stat.st_dev, initial_stat.st_ino)
    except OSError as exc:
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "Selected worktree identity could not be verified",
            details={"reason": "worktree_identity_unverified"},
        ) from exc

    canon_common_rc, canon_common_out, _ = await _git(
        canonical, "rev-parse", "--git-common-dir", check=False
    )
    identity_rc, identity_out, _ = await _git(
        candidate,
        "rev-parse",
        "--show-toplevel",
        "--git-common-dir",
        "--symbolic-full-name",
        "HEAD",
        check=False,
    )
    identity_lines = identity_out.splitlines()
    if identity_rc != 0 or canon_common_rc != 0 or len(identity_lines) != 3:
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "Selected worktree identity could not be verified",
            details={"reason": "worktree_identity_unverified"},
        )
    top_out, common_out, branch_out = identity_lines
    if _reported_path(candidate, top_out) != candidate or branch_out.strip() != expected_ref:
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "Selected worktree no longer matches worktree_branch",
            details={"reason": "worktree_branch_mismatch"},
        )
    if _reported_path(candidate, common_out) != _reported_path(canonical, canon_common_out):
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "Selected worktree does not belong to the registered repository",
            details={"reason": "foreign_worktree"},
        )
    try:
        final_stat = candidate.stat()
        final_identity = (final_stat.st_dev, final_stat.st_ino)
        final_resolved = raw_path.resolve(strict=True)
    except OSError as exc:
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "Selected worktree identity changed during validation",
            details={"reason": "worktree_identity_changed"},
        ) from exc
    if raw_path.is_symlink() or final_resolved != candidate or final_identity != initial_identity:
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "Selected worktree identity changed during validation",
            details={"reason": "worktree_identity_changed"},
        )
    return candidate
