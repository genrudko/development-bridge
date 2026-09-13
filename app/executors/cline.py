from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from app.api.errors import BridgeError, ErrorCode
from app.executors.antigravity import ProcessRunner
from app.executors.cline_auth import local_auth_configured
from app.executors.models import (
    ExecutorLaunch,
    ExecutorName,
    ExecutorRequest,
    ExecutorStatus,
    QuotaState,
)
from app.executors.prompts import build_task_prompt
from app.projects.models import Repository
from app.settings import OPENROUTER_MODEL_PATTERN, ClineExecutorSettings

_PROBE_OUTPUT_LIMIT = 16_384


def _environment() -> dict[str, str]:
    return {
        key: os.environ[key]
        for key in ("HOME", "PATH", "LANG", "LC_ALL", "SSH_CONNECTION")
        if key in os.environ
    }


class ClineExecutor:
    """Explicit-only Cline CLI executor.

    Cline keeps its own provider authentication and streaming session state, so
    Development Bridge only probes the local binary/version and local provider
    evidence, then delegates each bounded task to ``cline_worker`` which
    normalizes Cline JSON output into one Bridge executor result.
    """

    def __init__(
        self,
        settings: ClineExecutorSettings,
        runner: ProcessRunner,
        worker_path: str | Path | None = None,
        python_executable: str | Path | None = None,
    ) -> None:
        self._settings = settings
        self._runner = runner
        self._worker_path = (
            Path(worker_path).resolve()
            if worker_path is not None
            else (Path(__file__).parent / "cline_worker.py").resolve()
        )
        self._python_executable = (
            str(python_executable) if python_executable is not None else sys.executable
        )

    async def probe(self, *, busy: bool) -> ExecutorStatus:
        base = dict(
            executor=ExecutorName.CLINE,
            busy=busy,
            model=self._settings.model,
            quota_state=QuotaState.UNKNOWN,
            remaining_fraction=None,
            reset_time=None,
            last_success_at=None,
            version=None,
        )
        executable = Path(self._settings.executable).expanduser()
        if not self._settings.enabled:
            return ExecutorStatus(
                available=False, authenticated=False, last_error="disabled", **base
            )
        if not executable.is_file():
            return ExecutorStatus(
                available=False, authenticated=False, last_error="binary_missing", **base
            )
        version = await self._runner.run(
            (str(executable), "--version"),
            cwd=executable.parent,
            timeout_seconds=self._settings.probe_timeout_seconds,
            output_limit_bytes=_PROBE_OUTPUT_LIMIT,
            env=_environment(),
        )
        if version.timed_out or version.returncode != 0:
            return ExecutorStatus(
                available=False, authenticated=False, last_error="probe_failed", **base
            )
        version_text = version.stdout[:_PROBE_OUTPUT_LIMIT].decode("utf-8", "replace").strip()
        base["version"] = version_text or None
        if not local_auth_configured(
            self._settings.config_directory, self._settings.provider
        ):
            return ExecutorStatus(
                available=True, authenticated=False, last_error="auth_required", **base
            )
        return ExecutorStatus(available=True, authenticated=True, last_error=None, **base)

    def launch(
        self,
        repository: Repository,
        request: ExecutorRequest,
        status: ExecutorStatus,
    ) -> ExecutorLaunch:
        if not status.available:
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                "Cline executor is unavailable",
                details={"reason": status.last_error or "unavailable"},
            )
        if not status.authenticated:
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                "Cline authentication is required",
                details={"reason": status.last_error or "auth_required"},
            )
        if not 1 <= len(request.task.encode("utf-8")) <= 65_536:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "Task must contain between 1 and 65536 UTF-8 bytes",
            )
        selected_model = request.model or self._settings.model
        if not re.fullmatch(OPENROUTER_MODEL_PATTERN, selected_model):
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                f"Invalid Cline model slug: {selected_model!r}",
                details={"reason": "invalid_model_slug"},
            )
        prompt = build_task_prompt(request.task, request.task_kind)
        arguments = (
            str(self._worker_path),
            "--executable",
            str(Path(self._settings.executable).expanduser()),
            "--provider",
            self._settings.provider,
            "--model",
            selected_model,
            "--config-dir",
            str(Path(self._settings.config_directory).expanduser()),
        )
        return ExecutorLaunch(
            executable=self._python_executable,
            arguments=arguments,
            stdin=prompt,
            environment_keys=("HOME", "SSH_CONNECTION"),
            executor=ExecutorName.CLINE,
            model=selected_model,
            quota_state=QuotaState.UNKNOWN,
        )
