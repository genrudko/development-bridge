from __future__ import annotations

import asyncio
import os

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import Capability, CapabilityPolicy
from app.jobs import JobService
from app.projects import Repository


class RepositoryCommandService:
    MAX_TIMEOUT_SECONDS = 30.0
    MAX_OUTPUT_BYTES = 65_536

    def __init__(self, jobs: JobService, policy: CapabilityPolicy) -> None:
        self._jobs = jobs
        self._policy = policy

    async def run(
        self,
        repository: Repository,
        executable: str,
        arguments: list[str] | tuple[str, ...],
        *,
        timeout_seconds: float = 10,
        output_limit_bytes: int = MAX_OUTPUT_BYTES,
    ) -> dict:
        self._policy.require(
            repository.capabilities,
            Capability.EXECUTE,
            project_id=repository.project_id,
            repository_id=repository.id,
        )
        if not isinstance(executable, str) or not 1 <= len(executable) <= 4096 or "\0" in executable:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "executable is invalid")
        if not isinstance(arguments, (list, tuple)) or len(arguments) > 256 or any(
            not isinstance(value, str) or len(value) > 4096 or "\0" in value
            for value in arguments
        ):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "arguments are invalid")
        if (
            not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or not 0 < timeout_seconds <= self.MAX_TIMEOUT_SECONDS
        ):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "timeout_seconds is invalid")
        if (
            not isinstance(output_limit_bytes, int)
            or isinstance(output_limit_bytes, bool)
            or not 1024 <= output_limit_bytes <= self.MAX_OUTPUT_BYTES
        ):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "output_limit_bytes is invalid")

        async def execute():
            return await self._execute(
                repository, executable, arguments, timeout_seconds, output_limit_bytes
            )

        return await self._jobs.run_when_repository_idle(repository, execute)

    @staticmethod
    async def _read_bounded(stream, limit: int) -> tuple[bytes, bool]:
        output = bytearray()
        truncated = False
        while chunk := await stream.read(8192):
            remaining = max(0, limit - len(output))
            output.extend(chunk[:remaining])
            truncated = truncated or len(chunk) > remaining
        return bytes(output), truncated

    async def _execute(self, repository, executable, arguments, timeout, limit):
        environment = {
            key: value
            for key in ("PATH", "LANG", "LC_ALL")
            if (value := os.environ.get(key)) is not None
        }
        try:
            process = await asyncio.create_subprocess_exec(
                executable,
                *arguments,
                cwd=repository.root,
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "Command executable could not be started",
                details={"executable": executable},
            ) from exc
        stdout_task = asyncio.create_task(self._read_bounded(process.stdout, limit))
        stderr_task = asyncio.create_task(self._read_bounded(process.stderr, limit))
        timed_out = False
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
        except TimeoutError:
            timed_out = True
            process.kill()
            await process.wait()
        stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
        return {
            "executable": executable,
            "arguments": list(arguments),
            "exit_code": process.returncode,
            "stdout": stdout[0].decode("utf-8", errors="replace"),
            "stderr": stderr[0].decode("utf-8", errors="replace"),
            "stdout_truncated": stdout[1],
            "stderr_truncated": stderr[1],
            "timed_out": timed_out,
        }
