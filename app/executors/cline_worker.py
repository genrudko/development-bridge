"""Bridge-side adapter for the Cline CLI.

Cline streams newline-delimited JSON events on stdout. Development Bridge jobs
expect exactly one bounded executor result object on stdout, so this adapter runs
Cline, reduces its event stream to a single normalized ``SUCCESS``/``ERROR``
result, and never forwards raw JSONL or credential material.

The Cline CLI is intentionally left at its default (no) timeout: the durable
Bridge job owns the outer timeout and terminates the whole process group.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable

RESPONSE_LIMIT = 32_768
DIAGNOSTIC_LIMIT = 8_192
STDERR_LIMIT = 4_096
COMPLETED_FINISH_REASON = "completed"

_SECRET_KEY_PATTERN = re.compile(
    r'(?i)("?(?:api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|id[_-]?token'
    r'|token|secret|password|authorization|bearer)"?\s*[:=]\s*)("?)([^\s",}]+)'
)
_BARE_SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9._-]{6,}")


def scrub_secrets(text: str) -> str:
    scrubbed = _SECRET_KEY_PATTERN.sub(r"\1\2[redacted]", text)
    return _BARE_SECRET_PATTERN.sub("[redacted]", scrubbed)


@dataclass(slots=True)
class ClineRunEvidence:
    session_id: str | None = None
    response: str | None = None
    finish_reason: str | None = None
    model: str | None = None
    usage: dict[str, object] | None = None
    iterations: int | None = None
    duration_ms: float | None = None
    aborted_reason: str | None = None
    malformed_events: int = 0


def parse_jsonl_events(raw: str) -> ClineRunEvidence:
    evidence = ClineRunEvidence()
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except (ValueError, TypeError):
            evidence.malformed_events += 1
            continue
        if not isinstance(event, dict):
            evidence.malformed_events += 1
            continue
        kind = event.get("type")
        if kind == "run_start":
            session_id = event.get("sessionId")
            if isinstance(session_id, str) and session_id:
                evidence.session_id = session_id
        elif kind == "run_result":
            finish_reason = event.get("finishReason")
            if isinstance(finish_reason, str):
                evidence.finish_reason = finish_reason
            text = event.get("text")
            if isinstance(text, str):
                evidence.response = text
            model = event.get("model")
            if isinstance(model, str) and model:
                evidence.model = model
            usage = event.get("usage")
            if isinstance(usage, dict):
                evidence.usage = usage
            iterations = event.get("iterations")
            if isinstance(iterations, int):
                evidence.iterations = iterations
            duration_ms = event.get("durationMs")
            if isinstance(duration_ms, (int, float)) and not isinstance(duration_ms, bool):
                evidence.duration_ms = float(duration_ms)
        elif kind == "run_aborted":
            reason = event.get("reason")
            if isinstance(reason, str) and reason:
                evidence.aborted_reason = reason
    return evidence


def _normalized_reason(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.strip().lower())[:64] or "unknown"


class ClineWorker:
    def __init__(
        self,
        executable: str,
        provider: str,
        model: str,
        task: str,
        config_directory: str | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self._executable = executable
        self._provider = provider
        self._model = model
        self._task = task
        self._config_directory = config_directory
        self._runner = runner

    def command(self) -> list[str]:
        command = [
            self._executable,
            "--json",
            "--provider",
            self._provider,
            "--model",
            self._model,
        ]
        if self._config_directory:
            command.extend(("--config", self._config_directory))
        command.append(self._task)
        return command

    def run(self) -> dict[str, object]:
        try:
            completed = self._runner(
                self.command(),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            return {
                "status": "ERROR",
                "reason": "executable_unavailable",
                "error": scrub_secrets(f"Cline executable could not be started: {exc}"),
            }
        evidence = parse_jsonl_events(completed.stdout or "")
        diagnostic = self._diagnostic(completed, evidence)
        prefix: dict[str, object] = {}
        if evidence.session_id is not None:
            prefix["session_id"] = evidence.session_id
        if evidence.aborted_reason is not None:
            return {
                "status": "ERROR",
                "reason": "run_aborted",
                "error": f"Cline run aborted ({evidence.aborted_reason})",
                "diagnostic": diagnostic,
                **prefix,
            }
        if completed.returncode != 0:
            return {
                "status": "ERROR",
                "reason": "nonzero_exit",
                "error": f"Cline exited with status {completed.returncode}",
                "diagnostic": diagnostic,
                **prefix,
            }
        if evidence.finish_reason is None:
            return {
                "status": "ERROR",
                "reason": "run_result_missing",
                "error": "Cline returned no terminal run_result event",
                "diagnostic": diagnostic,
                **prefix,
            }
        if evidence.finish_reason != COMPLETED_FINISH_REASON:
            return {
                "status": "ERROR",
                "reason": f"finish_reason_{_normalized_reason(evidence.finish_reason)}",
                "error": f"Cline finished without completing ({evidence.finish_reason})",
                "diagnostic": diagnostic,
                **prefix,
            }
        if evidence.response is None:
            return {
                "status": "ERROR",
                "reason": "run_result_invalid",
                "error": "Cline run_result carried no terminal text",
                "diagnostic": diagnostic,
                **prefix,
            }
        result: dict[str, object] = {
            "status": "SUCCESS",
            "response": evidence.response[:RESPONSE_LIMIT],
            "finish_reason": COMPLETED_FINISH_REASON,
            **prefix,
        }
        if evidence.model is not None:
            result["model"] = evidence.model
        if evidence.usage is not None:
            result["usage"] = evidence.usage
        if evidence.iterations is not None:
            result["iterations"] = evidence.iterations
        if evidence.duration_ms is not None:
            result["duration_ms"] = evidence.duration_ms
        return result

    def _diagnostic(
        self, completed: subprocess.CompletedProcess[str], evidence: ClineRunEvidence
    ) -> str:
        parts = [f"exit_code={completed.returncode}"]
        if evidence.finish_reason is not None:
            parts.append(f"finish_reason={evidence.finish_reason}")
        if evidence.aborted_reason is not None:
            parts.append(f"aborted_reason={evidence.aborted_reason}")
        if evidence.malformed_events:
            parts.append(f"malformed_events={evidence.malformed_events}")
        stderr = (completed.stderr or "").strip()
        if stderr:
            parts.append("stderr=" + stderr[:STDERR_LIMIT])
        return scrub_secrets(" ".join(parts))[:DIAGNOSTIC_LIMIT]


def emit(result: dict[str, object]) -> int:
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0 if result.get("status") == "SUCCESS" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one bounded Cline task for Development Bridge"
    )
    parser.add_argument(
        "--executable",
        default=os.environ.get("DEVELOPMENT_BRIDGE_CLINE_EXECUTABLE", "cline"),
    )
    parser.add_argument("--provider", default="cline-pass")
    parser.add_argument("--model", required=True)
    parser.add_argument("--config-dir", dest="config_directory", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    task = sys.stdin.read()
    if not task.strip():
        return emit(
            {
                "status": "ERROR",
                "reason": "missing_task",
                "error": "Cline worker requires a task on stdin",
            }
        )
    worker = ClineWorker(
        executable=arguments.executable,
        provider=arguments.provider,
        model=arguments.model,
        task=task,
        config_directory=arguments.config_directory,
    )
    return emit(worker.run())


if __name__ == "__main__":
    raise SystemExit(main())
