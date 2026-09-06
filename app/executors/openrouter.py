from __future__ import annotations

import sys
from pathlib import Path

from app.api.errors import BridgeError, ErrorCode
from app.executors.models import (
    ExecutorLaunch,
    ExecutorName,
    ExecutorRequest,
    ExecutorStatus,
    QuotaState,
)
from app.executors.prompts import build_task_prompt
from app.projects.models import Repository
from app.settings import OpenRouterExecutorSettings


class OpenRouterExecutor:
    def __init__(
        self,
        settings: OpenRouterExecutorSettings,
        worker_path: str | Path | None = None,
        python_executable: str | Path | None = None,
    ) -> None:
        self._settings = settings
        self._worker_path = (
            Path(worker_path).resolve()
            if worker_path is not None
            else (Path(__file__).parent / "openrouter_worker.py").resolve()
        )
        self._python_executable = (
            str(python_executable)
            if python_executable is not None
            else sys.executable
        )

    def probe(self, *, busy: bool) -> ExecutorStatus:
        base = dict(
            executor=ExecutorName.OPENROUTER,
            busy=busy,
            model=self._settings.model,
            quota_state=QuotaState.UNKNOWN,
            remaining_fraction=None,
            reset_time=None,
            last_success_at=None,
            version=None,
        )
        if not self._settings.enabled:
            return ExecutorStatus(
                available=False,
                authenticated=False,
                last_error="disabled",
                **base,
            )
        if (
            self._settings.api_key is None
            or not self._settings.api_key.get_secret_value()
        ):
            return ExecutorStatus(
                available=False,
                authenticated=False,
                last_error="missing_key",
                **base,
            )
        return ExecutorStatus(
            available=True, authenticated=True, last_error=None, **base
        )

    def launch(
        self,
        repository: Repository,
        request: ExecutorRequest,
        status: ExecutorStatus,
    ) -> ExecutorLaunch:
        if not status.available:
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                "OpenRouter executor is disabled",
                details={"reason": status.last_error or "disabled"},
            )
        if not status.authenticated:
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                "OpenRouter authentication is required",
                details={"reason": status.last_error or "missing_key"},
            )
        if not 1 <= len(request.task.encode("utf-8")) <= 65_536:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "Task must contain between 1 and 65536 UTF-8 bytes",
            )
        selected_model = request.model or self._settings.model
        if selected_model not in self._settings.allowed_models:
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                f"Model '{selected_model}' is not allowlisted for openrouter",
                details={"reason": "model_not_allowlisted"},
            )
        prompt = build_task_prompt(request.task, request.task_kind)
        arguments = (
            str(self._worker_path),
            "--model",
            selected_model,
            "--base-url",
            self._settings.api_base_url,
            "--task-kind",
            request.task_kind.value,
        )
        return ExecutorLaunch(
            executable=self._python_executable,
            arguments=arguments,
            stdin=prompt,
            environment_keys=(
                "HOME",
                "SSH_CONNECTION",
                "OPENROUTER_API_KEY",
                "DEVELOPMENT_BRIDGE_OPENROUTER_API_KEY",
                "OPENROUTER_BASE_URL",
                "DEVELOPMENT_BRIDGE_OPENROUTER_BASE_URL",
            ),
            executor=ExecutorName.OPENROUTER,
            model=selected_model,
            quota_state=QuotaState.UNKNOWN,
        )
