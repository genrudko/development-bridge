from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .models import GitCommit


@dataclass(frozen=True, slots=True)
class GitStageResult:
    status: str
    previous_revision: str
    revision: str
    head: str
    index_revision: str
    paths: tuple[str, ...]
    staged_files: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GitCommitResult:
    status: str
    commit: GitCommit
    previous_head: str
    head: str
    index_revision: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "commit": self.commit.as_dict(),
            "previous_head": self.previous_head,
            "head": self.head,
            "index_revision": self.index_revision,
        }


@dataclass(frozen=True, slots=True)
class GitPushPlan:
    plan_id: str
    local_branch: str
    local_head: str
    remote: str
    remote_branch: str
    remote_ref: str
    remote_head: str | None
    action: str
    fast_forward: bool
    set_upstream: bool
    commits: tuple[GitCommit, ...]
    commit_count: int
    commits_truncated: bool

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["commits"] = [commit.as_dict() for commit in self.commits]
        return payload


@dataclass(frozen=True, slots=True)
class GitPushResult:
    status: str
    plan_id: str
    remote: str
    remote_branch: str
    previous_remote_head: str | None
    remote_head: str
    local_head: str
    upstream: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
