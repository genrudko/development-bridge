from __future__ import annotations

import re
import time
from typing import Any

from app.git.runner import GitRunner
from app.projects.models import Repository


class GitSnapshotProvider:
    """Read-only cached Git snapshot provider for operator dashboard."""

    def __init__(self, runner: GitRunner | None = None, *, cache_ttl_seconds: float = 5.0) -> None:
        self._runner = runner or GitRunner()
        self._cache_ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    async def snapshot(self, repository: Repository) -> dict[str, Any]:
        key = f"{repository.project_id}:{repository.id}"
        now = time.time()
        cached = self._cache.get(key)
        if cached is not None and now - cached[0] < self._cache_ttl:
            return dict(cached[1])

        status_res = await self._runner.run(
            repository, ["status", "--porcelain=v1", "--branch"], check=False
        )
        head_res = await self._runner.run(
            repository, ["rev-parse", "HEAD"], check=False
        )

        lines = status_res.stdout.splitlines() if status_res.returncode == 0 else []
        branch, upstream, ahead, behind = self._parse_branch(lines[0] if lines else "")

        staged = unstaged = untracked = 0
        for line in lines[1:]:
            if line.startswith("??"):
                untracked += 1
                continue
            if len(line) >= 2 and line[0] not in (" ", "?"):
                staged += 1
            if len(line) >= 2 and line[1] not in (" ", "?"):
                unstaged += 1

        changed_files_count = staged + unstaged + untracked
        clean = changed_files_count == 0
        head = head_res.stdout.strip() if head_res.returncode == 0 and head_res.stdout.strip() else None
        head_short = head[:7] if head else None

        result: dict[str, Any] = {
            "project_id": repository.project_id,
            "repository_id": repository.id,
            "branch": branch,
            "head": head,
            "head_short": head_short,
            "clean": clean,
            "dirty": not clean,
            "changed_files_count": changed_files_count,
            "upstream": upstream,
            "ahead": ahead,
            "behind": behind,
        }
        self._cache[key] = (now, result)
        return dict(result)

    @staticmethod
    def _parse_branch(header: str) -> tuple[str | None, str | None, int, int]:
        value = header.removeprefix("## ")
        if value.startswith("HEAD (no branch)") or not value.strip():
            return None, None, 0, 0
        branch_part, _, tracking = value.partition("...")
        branch = branch_part.strip() or None
        upstream = None
        ahead = behind = 0
        if tracking:
            upstream = tracking.split(" ", 1)[0]
            ahead_match = re.search(r"ahead (\d+)", tracking)
            behind_match = re.search(r"behind (\d+)", tracking)
            ahead = int(ahead_match.group(1)) if ahead_match else 0
            behind = int(behind_match.group(1)) if behind_match else 0
        return branch, upstream, ahead, behind
