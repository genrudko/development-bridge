from __future__ import annotations

import subprocess
from pathlib import Path

from app.api.errors import BridgeError, ErrorCode
from tests.fixtures.repositories import create_git_repository


class FakeManagedCloneRunner:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.clone_calls: list[tuple[str, Path, int]] = []

    async def clone(self, url: str, destination: Path, depth: int) -> None:
        self.clone_calls.append((url, destination, depth))
        if self.fail:
            destination.mkdir()
            (destination / "partial").write_text("partial", encoding="utf-8")
            raise BridgeError(
                ErrorCode.REPOSITORY_CLONE_FAILED, "Controlled clone failure"
            )
        create_git_repository(destination.parent, destination.name)
        remote = destination.parent.parent / f".fake-origin-{destination.parent.name}.git"
        subprocess.run(
            ["git", "init", "--bare", remote], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "remote", "add", "origin", str(remote)],
            cwd=destination,
            check=True,
        )
        subprocess.run(
            ["git", "push", "--set-upstream", "origin", "main"],
            cwd=destination,
            check=True,
            capture_output=True,
        )

    async def inspect(self, repository: Path) -> tuple[str, str]:
        def git(*arguments: str) -> str:
            return subprocess.run(
                ["git", *arguments],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

        return git("branch", "--show-current"), git("rev-parse", "HEAD")
