from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import Capability, CapabilityPolicy
from app.projects import Repository

from .models import (
    GitCommit,
    GitDiff,
    GitDiffFile,
    GitLog,
    GitPatch,
    GitRef,
    GitRefs,
    GitShow,
    RepositoryStatus,
)
from .runner import GitRunner


class GitService:
    DEFAULT_LOG_COUNT = 50
    MAX_LOG_COUNT = 100
    MAX_REFS = 1000
    MAX_PATCH_BYTES = 256 * 1024

    def __init__(self, runner: GitRunner, policy: CapabilityPolicy) -> None:
        self._runner = runner
        self._policy = policy

    async def repository_status(self, repository: Repository) -> RepositoryStatus:
        self._require_read(repository)
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

    async def log(
        self,
        repository: Repository,
        *,
        revision: str = "HEAD",
        max_count: int = DEFAULT_LOG_COUNT,
    ) -> GitLog:
        self._require_read(repository)
        if not 1 <= max_count <= self.MAX_LOG_COUNT:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "max_count is outside the allowed range",
                details={"minimum": 1, "maximum": self.MAX_LOG_COUNT},
            )
        commit_sha = await self._resolve_commit(repository, revision)
        result = await self._runner.run(
            repository,
            [
                "log",
                f"--max-count={max_count + 1}",
                "--format=%H%x1f%P%x1f%an%x1f%ae%x1f%aI%x1f%s%x1e",
                commit_sha,
            ],
        )
        commits = self._parse_commits(result.stdout)
        return GitLog(commits[:max_count], len(commits) > max_count)

    async def show(self, repository: Repository, revision: str) -> GitShow:
        self._require_read(repository)
        commit_sha = await self._resolve_commit(repository, revision)
        metadata = await self._runner.run(
            repository,
            [
                "show",
                "-s",
                "--format=%H%x1f%P%x1f%an%x1f%ae%x1f%aI%x1f%s%x1e",
                commit_sha,
            ],
        )
        commits = self._parse_commits(metadata.stdout)
        patch = await self._runner.run(
            repository,
            [
                "show",
                "--format=",
                "--patch",
                "--no-color",
                "--no-ext-diff",
                "--no-renames",
                commit_sha,
            ],
        )
        return GitShow(commits[0], self._bounded_patch(patch.stdout))

    async def diff(
        self,
        repository: Repository,
        *,
        mode: str = "working",
        base: str | None = None,
        target: str | None = None,
        path: str | None = None,
    ) -> GitDiff:
        self._require_read(repository)
        if mode not in {"working", "staged", "range"}:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Unknown diff mode")
        if mode == "range":
            if not base or not target:
                raise BridgeError(
                    ErrorCode.INVALID_ARGUMENT,
                    "range diff requires base and target revisions",
                )
            revisions = [
                await self._resolve_commit(repository, base),
                await self._resolve_commit(repository, target),
            ]
        else:
            if base is not None or target is not None:
                raise BridgeError(
                    ErrorCode.INVALID_ARGUMENT,
                    "base and target are only valid for range diff",
                )
            revisions = ["--cached"] if mode == "staged" else []

        common = ["--no-renames", *revisions]
        if path is not None:
            self._validate_path(path)
            common.extend(["--", path])
        stats = await self._runner.run(
            repository, ["diff", "--numstat", "-z", *common]
        )
        patch = await self._runner.run(
            repository,
            ["diff", "--patch", "--no-color", "--no-ext-diff", *common],
        )
        return GitDiff(
            mode,
            self._parse_diff_files(stats.stdout),
            self._bounded_patch(patch.stdout),
        )

    async def refs(self, repository: Repository, *, kind: str = "all") -> GitRefs:
        self._require_read(repository)
        prefixes = {
            "all": (),
            "heads": ("refs/heads",),
            "tags": ("refs/tags",),
            "remotes": ("refs/remotes",),
        }
        if kind not in prefixes:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Unknown ref kind")
        result = await self._runner.run(
            repository,
            [
                "for-each-ref",
                f"--count={self.MAX_REFS + 1}",
                "--sort=refname",
                "--format=%(refname)%1f%(refname:short)%1f%(objectname)%1f%(objecttype)%1e",
                *prefixes[kind],
            ],
        )
        references = self._parse_refs(result.stdout)
        return GitRefs(references[: self.MAX_REFS], len(references) > self.MAX_REFS)

    def _require_read(self, repository: Repository) -> None:
        self._policy.require(
            repository.capabilities,
            Capability.GIT_READ,
            project_id=repository.project_id,
            repository_id=repository.id,
        )

    async def _resolve_commit(self, repository: Repository, revision: str) -> str:
        if not isinstance(revision, str) or not revision or "\0" in revision:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT, "Revision must be a non-empty string"
            )
        result = await self._runner.run(
            repository,
            ["rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}"],
            check=False,
        )
        if result.returncode != 0:
            raise BridgeError(
                ErrorCode.GIT_REVISION_NOT_FOUND,
                "Git revision was not found",
                details={"revision": revision, "repository_id": repository.id},
            )
        return result.stdout.strip()

    @staticmethod
    def _parse_commits(output: str) -> tuple[GitCommit, ...]:
        commits = []
        for record in output.split("\x1e"):
            record = record.strip("\n")
            if not record:
                continue
            sha, parents, name, email, authored_at, subject = record.split("\x1f", 5)
            commits.append(
                GitCommit(
                    sha,
                    tuple(parents.split()) if parents else (),
                    name,
                    email,
                    authored_at,
                    subject,
                )
            )
        return tuple(commits)

    @staticmethod
    def _parse_diff_files(output: str) -> tuple[GitDiffFile, ...]:
        files = []
        for record in output.split("\0"):
            if not record:
                continue
            additions, deletions, path = record.split("\t", 2)
            files.append(
                GitDiffFile(
                    path,
                    int(additions) if additions.isdigit() else None,
                    int(deletions) if deletions.isdigit() else None,
                )
            )
        return tuple(files)

    @staticmethod
    def _parse_refs(output: str) -> tuple[GitRef, ...]:
        references = []
        for record in output.split("\x1e"):
            record = record.strip("\n")
            if not record:
                continue
            references.append(GitRef(*record.split("\x1f", 3)))
        return tuple(references)

    @classmethod
    def _bounded_patch(cls, patch: str) -> GitPatch:
        encoded = patch.encode("utf-8")
        if len(encoded) <= cls.MAX_PATCH_BYTES:
            return GitPatch(patch, False)
        bounded = encoded[: cls.MAX_PATCH_BYTES].decode("utf-8", errors="ignore")
        return GitPatch(bounded, True)

    @staticmethod
    def _validate_path(path: str) -> None:
        if not isinstance(path, str) or not path:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT, "Path must be a non-empty string"
            )
        normalized = PurePosixPath(path)
        if (
            normalized.is_absolute()
            or ".." in normalized.parts
            or normalized.parts[0] == ".git"
        ):
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                "Path is outside the repository boundary",
                details={"path": path},
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
