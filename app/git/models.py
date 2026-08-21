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

