from __future__ import annotations

import hashlib
import re

from app.capabilities import Capability, CapabilityPolicy
from app.projects import Repository

from .models import RepositoryStatus
from .runner import GitRunner


class GitService:
    def __init__(self, runner: GitRunner, policy: CapabilityPolicy) -> None:
        self._runner = runner
        self._policy = policy

    async def repository_status(self, repository: Repository) -> RepositoryStatus:
        self._policy.require(
            repository.capabilities,
            Capability.GIT_READ,
            project_id=repository.project_id,
            repository_id=repository.id,
        )
        status_result = await self._runner.run(
            repository, ["status", "--porcelain=v1", "--branch"]
        )
        head_result = await self._runner.run(repository, ["rev-parse", "HEAD"])
        lines = status_result.stdout.splitlines()
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

        operation = self._operation(repository)
        revision = "sha256:" + hashlib.sha256(
            (head_result.stdout.strip() + "\0" + status_result.stdout).encode("utf-8")
        ).hexdigest()
        return RepositoryStatus(
            branch=branch,
            head=head_result.stdout.strip(),
            upstream=upstream,
            ahead=ahead,
            behind=behind,
            staged=staged,
            unstaged=unstaged,
            untracked=untracked,
            operation=operation,
            dirty=bool(staged or unstaged or untracked),
            revision=revision,
        )

    @staticmethod
    def _parse_branch(header: str) -> tuple[str | None, str | None, int, int]:
        value = header.removeprefix("## ")
        if value.startswith("HEAD (no branch)"):
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

    @staticmethod
    def _operation(repository: Repository) -> str | None:
        git_directory = repository.root / ".git"
        if (git_directory / "MERGE_HEAD").exists():
            return "merge"
        if (git_directory / "rebase-merge").exists() or (
            git_directory / "rebase-apply"
        ).exists():
            return "rebase"
        if (git_directory / "CHERRY_PICK_HEAD").exists():
            return "cherry-pick"
        return None

