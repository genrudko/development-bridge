from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GitCommandResult:
    arguments: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class RepositoryStatus:
    branch: str | None
    head: str
    upstream: str | None
    ahead: int
    behind: int
    staged: int
    unstaged: int
    untracked: int
    operation: str | None
    dirty: bool
    revision: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GitCommit:
    sha: str
    parents: tuple[str, ...]
    author_name: str
    author_email: str
    authored_at: str
    subject: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GitLog:
    commits: tuple[GitCommit, ...]
    truncated: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "commits": [commit.as_dict() for commit in self.commits],
            "truncated": self.truncated,
        }


@dataclass(frozen=True, slots=True)
class GitPatch:
    text: str
    truncated: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GitShow:
    commit: GitCommit
    patch: GitPatch

    def as_dict(self) -> dict[str, Any]:
        return {"commit": self.commit.as_dict(), "patch": self.patch.as_dict()}


@dataclass(frozen=True, slots=True)
class GitDiffFile:
    path: str
    additions: int | None
    deletions: int | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GitDiff:
    mode: str
    files: tuple[GitDiffFile, ...]
    patch: GitPatch

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "files": [file.as_dict() for file in self.files],
            "patch": self.patch.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class GitRef:
    name: str
    short_name: str
    target: str
    object_type: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GitRefs:
    refs: tuple[GitRef, ...]
    truncated: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "refs": [reference.as_dict() for reference in self.refs],
            "truncated": self.truncated,
        }
