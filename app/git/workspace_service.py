from __future__ import annotations

from typing import TYPE_CHECKING

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import Capability, CapabilityPolicy
from app.projects import Repository, RepositoryMutationLock

from .runner import GitRunner
from .workspace_models import (
    GitBranchCreateResult,
    GitBranchSwitchResult,
    GitFastForwardResult,
    GitFetchResult,
    GitRefUpdate,
)

if TYPE_CHECKING:
    from app.changes.revision import ChangeRevisionCalculator


class GitWorkspaceService:
    MAX_UPDATED_REFS = 1000

    def __init__(
        self,
        runner: GitRunner,
        policy: CapabilityPolicy,
        revisions: ChangeRevisionCalculator,
        mutations: RepositoryMutationLock,
    ) -> None:
        self._runner = runner
        self._policy = policy
        self._revisions = revisions
        self._mutations = mutations

    async def fetch(
        self, repository: Repository, *, remote: str | None = None
    ) -> GitFetchResult:
        self._require_fetch(repository)
        async with self._mutations.acquire(repository):
            await self._ensure_no_operation(repository)
            if remote is None:
                remote, _ = await self._upstream(repository)
            if remote is None:
                raise BridgeError(
                    ErrorCode.INVALID_ARGUMENT,
                    "remote is required when no upstream is configured",
                )
            self._validate_remote(remote)
            await self._require_remote(repository, remote)
            before = await self._remote_refs(repository, remote)
            await self._runner.run(repository, ["fetch", remote])
            after = await self._remote_refs(repository, remote)
            names = sorted(set(before) | set(after))
            updates = tuple(
                GitRefUpdate(name, before.get(name), after.get(name))
                for name in names
                if before.get(name) != after.get(name)
            )
            return GitFetchResult(
                remote,
                updates[: self.MAX_UPDATED_REFS],
                len(updates) > self.MAX_UPDATED_REFS,
            )

    async def branch_create(
        self,
        repository: Repository,
        *,
        branch: str,
        start_point: str = "HEAD",
        expected_head: str | None = None,
    ) -> GitBranchCreateResult:
        self._require_write(repository)
        async with self._mutations.acquire(repository):
            await self._ensure_no_operation(repository)
            await self._require_branch_name(repository, branch)
            current_head = await self._head(repository)
            if expected_head is not None and expected_head != current_head:
                raise self._revision_conflict(expected_head, current_head)
            exists = await self._runner.run(
                repository,
                ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
                check=False,
            )
            if exists.returncode == 0:
                raise BridgeError(
                    ErrorCode.GIT_BRANCH_EXISTS,
                    "Local branch already exists",
                    details={"branch": branch},
                )
            target = await self._resolve_commit(repository, start_point)
            await self._runner.run(repository, ["branch", branch, target])
            return GitBranchCreateResult(
                "created", branch, target, await self._current_branch(repository)
            )

    async def branch_switch(
        self,
        repository: Repository,
        *,
        branch: str,
        expected_revision: str | None = None,
    ) -> GitBranchSwitchResult:
        self._require_write(repository)
        async with self._mutations.acquire(repository):
            await self._ensure_no_operation(repository)
            await self._require_branch_name(repository, branch)
            previous_revision = await self._revisions.calculate(repository)
            if expected_revision is not None and expected_revision != previous_revision:
                raise self._revision_conflict(expected_revision, previous_revision)
            await self._require_clean(repository)
            exists = await self._runner.run(
                repository,
                ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
                check=False,
            )
            if exists.returncode != 0:
                raise BridgeError(
                    ErrorCode.GIT_BRANCH_NOT_FOUND,
                    "Local branch was not found",
                    details={"branch": branch},
                )
            previous = await self._current_branch(repository)
            await self._runner.run(repository, ["switch", branch])
            return GitBranchSwitchResult(
                "switched",
                previous,
                branch,
                await self._head(repository),
                await self._revisions.calculate(repository),
            )

    async def fast_forward(
        self,
        repository: Repository,
        *,
        expected_head: str | None = None,
    ) -> GitFastForwardResult:
        self._require_write(repository)
        async with self._mutations.acquire(repository):
            await self._ensure_no_operation(repository)
            await self._require_clean(repository)
            branch = await self._current_branch(repository)
            remote, remote_branch = await self._upstream(repository)
            if remote is None or remote_branch is None:
                raise BridgeError(
                    ErrorCode.GIT_UPSTREAM_NOT_CONFIGURED,
                    "Current branch has no upstream",
                )
            previous = await self._head(repository)
            if expected_head is not None and expected_head != previous:
                raise self._revision_conflict(expected_head, previous)
            upstream = f"{remote}/{remote_branch}"
            target = await self._resolve_commit(repository, upstream)
            if target == previous:
                return GitFastForwardResult(
                    "already_up_to_date", branch, upstream, previous, previous, 0
                )
            ancestor = await self._runner.run(
                repository,
                ["merge-base", "--is-ancestor", previous, target],
                check=False,
            )
            if ancestor.returncode != 0:
                raise BridgeError(
                    ErrorCode.GIT_FAST_FORWARD_REJECTED,
                    "Upstream cannot fast-forward the current branch",
                    details={"branch": branch, "upstream": upstream},
                )
            count = int(
                (
                    await self._runner.run(
                        repository, ["rev-list", "--count", f"{previous}..{target}"]
                    )
                ).stdout.strip()
            )
            await self._runner.run(repository, ["merge", "--ff-only", upstream])
            return GitFastForwardResult(
                "fast_forwarded",
                branch,
                upstream,
                previous,
                await self._head(repository),
                count,
            )

    def _require_write(self, repository: Repository) -> None:
        self._policy.require(
            repository.capabilities,
            Capability.GIT_WRITE,
            project_id=repository.project_id,
            repository_id=repository.id,
        )

    def _require_fetch(self, repository: Repository) -> None:
        if repository.capabilities.allows(Capability.GIT_WRITE):
            return
        self._policy.require(
            repository.capabilities,
            Capability.GIT_READ,
            project_id=repository.project_id,
            repository_id=repository.id,
        )

    async def _require_clean(self, repository: Repository) -> None:
        status = await self._runner.run(
            repository, ["status", "--porcelain=v1", "--untracked-files=normal"]
        )
        if status.stdout:
            raise BridgeError(
                ErrorCode.GIT_WORKTREE_DIRTY,
                "Git workspace operation requires a clean repository",
            )

    async def _ensure_no_operation(self, repository: Repository) -> None:
        git_dir = repository.root / ".git"
        if any(
            (git_dir / marker).exists()
            for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "rebase-merge", "rebase-apply")
        ):
            raise BridgeError(
                ErrorCode.GIT_OPERATION_IN_PROGRESS, "A Git operation is in progress"
            )

    async def _head(self, repository: Repository) -> str:
        return (
            await self._runner.run(repository, ["rev-parse", "--verify", "HEAD"])
        ).stdout.strip()

    async def _current_branch(self, repository: Repository) -> str:
        result = await self._runner.run(
            repository, ["symbolic-ref", "--short", "HEAD"], check=False
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise BridgeError(
                ErrorCode.GIT_BRANCH_NOT_FOUND,
                "Operation requires a named current branch",
            )
        return result.stdout.strip()

    async def _upstream(
        self, repository: Repository
    ) -> tuple[str | None, str | None]:
        result = await self._runner.run(
            repository,
            ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
            check=False,
        )
        if result.returncode != 0:
            return None, None
        remote, separator, branch = result.stdout.strip().partition("/")
        return (remote, branch) if separator else (None, None)

    async def _resolve_commit(self, repository: Repository, revision: str) -> str:
        if not isinstance(revision, str) or not revision or "\0" in revision:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Revision is invalid")
        result = await self._runner.run(
            repository,
            ["rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}"],
            check=False,
        )
        if result.returncode != 0:
            raise BridgeError(
                ErrorCode.GIT_REVISION_NOT_FOUND,
                "Git revision was not found",
                details={"revision": revision},
            )
        return result.stdout.strip()

    async def _require_branch_name(self, repository: Repository, branch: str) -> None:
        if not isinstance(branch, str) or not branch or "\0" in branch or len(branch) > 1024:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Branch name is invalid")
        result = await self._runner.run(
            repository, ["check-ref-format", f"refs/heads/{branch}"], check=False
        )
        if result.returncode != 0:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Branch name is invalid")

    @staticmethod
    def _validate_remote(remote: str) -> None:
        import re

        if not isinstance(remote, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}", remote
        ):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Remote name is invalid")

    async def _require_remote(self, repository: Repository, remote: str) -> None:
        result = await self._runner.run(
            repository, ["remote", "get-url", remote], check=False
        )
        if result.returncode != 0:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "Git remote is not configured",
                details={"remote": remote},
            )

    async def _remote_refs(
        self, repository: Repository, remote: str
    ) -> dict[str, str]:
        result = await self._runner.run(
            repository,
            [
                "for-each-ref",
                "--format=%(refname)%00%(objectname)",
                f"refs/remotes/{remote}",
            ],
        )
        refs = {}
        for line in result.stdout.splitlines():
            name, separator, target = line.partition("\0")
            if separator:
                refs[name] = target
        return refs

    @staticmethod
    def _revision_conflict(expected: str, actual: str) -> BridgeError:
        return BridgeError(
            ErrorCode.REVISION_CONFLICT,
            "Git state does not match the guarded revision",
            details={"expected_revision": expected, "actual_revision": actual},
        )
