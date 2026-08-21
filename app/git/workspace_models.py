from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GitRefUpdate:
    ref: str
    previous: str | None
    target: str | None

    def as_dict(self) -> dict[str, str | None]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GitFetchResult:
    remote: str
    updated_refs: tuple[GitRefUpdate, ...]
    truncated: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "remote": self.remote,
            "updated_refs": [update.as_dict() for update in self.updated_refs],
            "truncated": self.truncated,
        }


@dataclass(frozen=True, slots=True)
class GitBranchCreateResult:
    status: str
    branch: str
    head: str
    current_branch: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GitBranchSwitchResult:
    status: str
    previous_branch: str
    branch: str
    head: str
    revision: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GitFastForwardResult:
    status: str
    branch: str
    upstream: str
    previous_head: str
    head: str
    commits_applied: int

    def as_dict(self) -> dict[str, str | int]:
        return asdict(self)
