from __future__ import annotations

import hashlib
import os
from pathlib import Path

from app.api.errors import BridgeError, ErrorCode
from app.git import GitRunner
from app.projects import Repository


class ChangeRevisionCalculator:
    MAX_FILES = 20_000
    MAX_BYTES = 64 * 1024 * 1024

    def __init__(self, runner: GitRunner) -> None:
        self._runner = runner

    async def calculate(self, repository: Repository) -> str:
        head = await self._runner.run(
            repository, ["rev-parse", "--verify", "HEAD"], check=False
        )
        index = await self._runner.run(repository, ["ls-files", "--stage", "-z"])
        digest = hashlib.sha256()
        digest.update(b"head\0")
        digest.update(head.stdout.strip().encode("utf-8") if head.returncode == 0 else b"unborn")
        digest.update(b"\0index\0")
        digest.update(index.stdout.encode("utf-8"))

        files = total_bytes = 0
        for candidate in sorted(repository.root.rglob("*")):
            relative = candidate.relative_to(repository.root)
            if relative.parts[0] == ".git":
                continue
            files += 1
            if files > self.MAX_FILES:
                raise self._limit_error("revision file limit", self.MAX_FILES)
            path = relative.as_posix().encode("utf-8")
            digest.update(b"\0path\0" + path + b"\0")
            if candidate.is_symlink():
                digest.update(b"symlink\0" + os.readlink(candidate).encode("utf-8"))
            elif candidate.is_dir():
                digest.update(b"directory")
            elif candidate.is_file():
                digest.update(b"file\0")
                try:
                    with candidate.open("rb") as source:
                        while chunk := source.read(64 * 1024):
                            total_bytes += len(chunk)
                            if total_bytes > self.MAX_BYTES:
                                raise self._limit_error(
                                    "revision content limit", self.MAX_BYTES
                                )
                            digest.update(chunk)
                except OSError as exc:
                    raise BridgeError(
                        ErrorCode.CHANGE_PRECONDITION_FAILED,
                        "Repository changed while calculating revision",
                        details={"path": relative.as_posix()},
                    ) from exc
            else:
                digest.update(b"other")
        return "sha256:" + digest.hexdigest()

    async def tracked_paths(self, repository: Repository) -> frozenset[str]:
        result = await self._runner.run(repository, ["ls-files", "-z", "--cached"])
        return frozenset(path for path in result.stdout.split("\0") if path)

    @staticmethod
    def _limit_error(boundary: str, limit: int) -> BridgeError:
        return BridgeError(
            ErrorCode.CHANGE_PLAN_INVALID,
            "Repository is too large for a Changes revision",
            details={"boundary": boundary, "limit": limit},
        )
