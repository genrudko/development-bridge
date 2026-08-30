from __future__ import annotations

import asyncio
import json
import os
import signal
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from typing import Protocol

from app.api.errors import BridgeError, ErrorCode
from app.executors.models import ExecutorLaunch, ExecutorName, ExecutorRequest, ExecutorStatus, QuotaState
from app.projects.models import Repository
from app.settings import AntigravityExecutorSettings


@dataclass(frozen=True, slots=True)
class ProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool
    stdout_truncated: bool
    stderr_truncated: bool


class ProcessRunner(Protocol):
    async def run(self, argv: tuple[str, ...], *, cwd: Path, timeout_seconds: float,
                  output_limit_bytes: int, env: dict[str, str]) -> ProcessResult: ...


class AsyncioProcessRunner:
    async def run(self, argv: tuple[str, ...], *, cwd: Path, timeout_seconds: float,
                  output_limit_bytes: int, env: dict[str, str]) -> ProcessResult:
        process = await asyncio.create_subprocess_exec(
            *argv, cwd=cwd, env=env, start_new_session=True,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )

        async def drain(stream: asyncio.StreamReader) -> tuple[bytes, bool]:
            kept = bytearray()
            truncated = False
            while chunk := await stream.read(8192):
                room = max(0, output_limit_bytes - len(kept))
                kept.extend(chunk[:room])
                truncated = truncated or len(chunk) > room
            return bytes(kept), truncated

        stdout_task = asyncio.create_task(drain(process.stdout))
        stderr_task = asyncio.create_task(drain(process.stderr))
        timed_out = False
        async def terminate() -> None:
            if process.returncode is not None:
                return
            os.killpg(process.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(process.wait(), 2)
            except TimeoutError:
                os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
        try:
            await asyncio.wait_for(process.wait(), timeout_seconds)
        except TimeoutError:
            timed_out = True
            await terminate()
        except asyncio.CancelledError:
            await asyncio.shield(terminate())
            await asyncio.shield(asyncio.gather(stdout_task, stderr_task))
            raise
        stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
        return ProcessResult(process.returncode, stdout[0], stderr[0], timed_out, stdout[1], stderr[1])


_PROMPT = """You are executing one bounded Development Bridge repository task.
Read and obey AGENTS.md before changing files.
Task:
{task}
Invariants:
- Work only inside the current repository.
- Do not change Git remotes, SSH configuration, credentials, or repository registration.
- Do not expose secrets or Bridge-native GitHub credentials.
- Do not push or deploy.
- Do not start background schedulers or delegate the task.
Verification:
- Run the repository's targeted tests for the changed behavior.
- Stop after running: pytest -q
Stop conditions:
- Stop on an authentication, quota, permission, or environment blocker.
- Return concise evidence: files changed, tests run, and remaining blocker.
"""


def _environment(extra: tuple[str, ...] = ("HOME", "SSH_CONNECTION")) -> dict[str, str]:
    return {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", *extra) if key in os.environ}


def _failure(text: str, timed_out: bool = False) -> str:
    if timed_out:
        return "probe_timeout"
    lowered = text[:16_384].lower()
    if any(item in lowered for item in ("authentication required", "sign in", "login required")):
        return "auth_required"
    if any(item in lowered for item in ("quota exhausted", "resource exhausted", "rate limit")):
        return "quota_exhausted"
    return "runtime_probe_failed"


class AntigravityExecutor:
    def __init__(self, settings: AntigravityExecutorSettings, runner: ProcessRunner) -> None:
        self._settings = settings
        self._runner = runner

    async def probe(self, *, busy: bool) -> ExecutorStatus:
        base = dict(executor=ExecutorName.ANTIGRAVITY, busy=busy, model=self._settings.model,
                    quota_state=QuotaState.UNKNOWN, remaining_fraction=None, reset_time=None,
                    last_success_at=None, version=None)
        executable = Path(self._settings.executable).expanduser()
        if not self._settings.enabled:
            return ExecutorStatus(available=False, authenticated=False, last_error="disabled", **base)
        if not executable.is_file():
            return ExecutorStatus(available=False, authenticated=False, last_error="binary_missing", **base)
        version = await self._runner.run((str(executable), "--version"), cwd=executable.parent,
            timeout_seconds=self._settings.probe_timeout_seconds, output_limit_bytes=16_384, env=_environment())
        if version.timed_out or version.returncode != 0:
            return ExecutorStatus(available=False, authenticated=False,
                last_error=_failure(version.stderr.decode("utf-8", "replace"), version.timed_out), **base)
        version_text = version.stdout[:16_384].decode("utf-8", "replace").strip()
        probe = await self._runner.run((str(executable), "-p", "Reply with exactly BRIDGE_PROBE_OK",
            "--output-format", "json", "--sandbox", "--print-timeout", "15s"), cwd=executable.parent,
            timeout_seconds=self._settings.probe_timeout_seconds, output_limit_bytes=16_384, env=_environment())
        diagnostic = probe.stderr.decode("utf-8", "replace")
        try:
            payload = json.loads(probe.stdout.decode("utf-8")) if not probe.timed_out else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        callable_runtime = (probe.returncode == 0 and isinstance(payload, dict)
            and payload.get("status") == "SUCCESS"
            and isinstance(payload.get("response"), str)
            and payload["response"].strip() == "BRIDGE_PROBE_OK")
        if callable_runtime:
            return ExecutorStatus(available=True, authenticated=True, last_error=None,
                last_success_at=datetime.now(UTC), version=version_text, **{k: v for k, v in base.items() if k not in {"last_success_at", "version"}})
        if isinstance(payload, dict):
            diagnostic += " " + str(payload.get("status", "")) + " " + str(payload.get("response", ""))
        reason = _failure(diagnostic, probe.timed_out)
        if reason == "quota_exhausted":
            base["quota_state"] = QuotaState.EXHAUSTED
        return ExecutorStatus(available=True, authenticated=reason != "auth_required",
            last_error=reason, version=version_text, **{k: v for k, v in base.items() if k != "version"})

    def launch(self, repository: Repository, request: ExecutorRequest, status: ExecutorStatus) -> ExecutorLaunch:
        gates = ((not status.available, "unavailable", "Antigravity executor is unavailable"),
                 (not status.authenticated, "auth_required", "Antigravity authentication is required"),
                 (status.busy, "busy", "Antigravity executor is busy"),
                 (status.quota_state is QuotaState.EXHAUSTED, "quota_exhausted", "Antigravity quota is exhausted"))
        for blocked, reason, message in gates:
            if blocked:
                raise BridgeError(ErrorCode.POLICY_VIOLATION, message, details={"reason": reason})
        if not 1 <= len(request.task.encode("utf-8")) <= 65_536:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Task must contain between 1 and 65536 UTF-8 bytes")
        timeout = min(ceil(request.timeout_seconds), ceil(self._settings.task_timeout_seconds))
        arguments = ["-p", _PROMPT.format(task=request.task), "--output-format", "json", "--sandbox",
                     "--print-timeout", f"{timeout}s"]
        if self._settings.model is not None:
            arguments.extend(("--model", self._settings.model))
        return ExecutorLaunch(str(Path(self._settings.executable).expanduser()), tuple(arguments), None,
            ("HOME", "SSH_CONNECTION"), ExecutorName.ANTIGRAVITY, self._settings.model, status.quota_state)
