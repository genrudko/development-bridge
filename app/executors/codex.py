from __future__ import annotations

from pathlib import Path

from app.api.errors import BridgeError, ErrorCode
from app.executors.models import ExecutorLaunch, ExecutorName, ExecutorRequest, ExecutorStatus, QuotaState
from app.executors.prompts import build_task_prompt
from app.projects.models import Repository


class CodexExecutor:
    def __init__(self, executable: str | Path = "codex") -> None:
        self._executable = str(executable)

    def launch(self, repository: Repository, request: ExecutorRequest, status: ExecutorStatus) -> ExecutorLaunch:
        if not 1 <= len(request.task.encode("utf-8")) <= 65_536:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Task must contain between 1 and 65536 UTF-8 bytes")
        prompt = build_task_prompt(request.task, request.task_kind)
        arguments = ("exec", "--sandbox", "workspace-write", "-")
        return ExecutorLaunch(
            executable=self._executable,
            arguments=arguments,
            stdin=prompt,
            environment_keys=("HOME", "SSH_CONNECTION"),
            executor=ExecutorName.CODEX,
            model=None,
            quota_state=QuotaState.UNKNOWN,
        )
