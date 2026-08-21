from __future__ import annotations

import asyncio

from app.api.errors import BridgeError, ErrorCode
from app.projects import Repository

from .models import GitCommandResult


class GitRunner:
    def __init__(self, *, timeout_seconds: float = 10, output_limit: int = 1_048_576):
        self._timeout_seconds = timeout_seconds
        self._output_limit = output_limit

    async def run(
        self,
        repository: Repository,
        arguments: list[str] | tuple[str, ...],
        *,
        check: bool = True,
    ) -> GitCommandResult:
        process = await asyncio.create_subprocess_exec(
            "git",
            *arguments,
            cwd=repository.root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout_seconds
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise BridgeError(
                ErrorCode.GIT_COMMAND_FAILED,
                "Git command timed out",
                retryable=True,
                details={"repository_id": repository.id},
            ) from exc

        if len(stdout_bytes) + len(stderr_bytes) > self._output_limit:
            raise BridgeError(
                ErrorCode.GIT_COMMAND_FAILED,
                "Git command output exceeded the configured limit",
                details={"repository_id": repository.id},
            )

        result = GitCommandResult(
            arguments=tuple(arguments),
            returncode=process.returncode or 0,
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
        )
        if check and result.returncode != 0:
            raise BridgeError(
                ErrorCode.GIT_COMMAND_FAILED,
                "Git command failed",
                details={
                    "repository_id": repository.id,
                    "returncode": result.returncode,
                },
            )
        return result

