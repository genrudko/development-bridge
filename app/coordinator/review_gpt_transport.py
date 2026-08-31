from __future__ import annotations

import asyncio
import json
import re
import tempfile
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.coordinator.wake_transport import (
    WakeDeliveryRequest,
    WakeDeliveryResult,
    WakeProbeResult,
    WakeTarget,
)

MAX_DETAIL_CHARS = 500


@dataclass(frozen=True, slots=True)
class ProcessResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""


AsyncProcessRunner = Callable[[Sequence[str], float], Awaitable[ProcessResult]]


async def default_process_runner(argv: Sequence[str], timeout: float) -> ProcessResult:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        raise TimeoutError(f"Process timed out after {timeout}s: {argv[0]}")
    return ProcessResult(
        exit_code=proc.returncode if proc.returncode is not None else -1,
        stdout=stdout_bytes.decode("utf-8", errors="replace"),
        stderr=stderr_bytes.decode("utf-8", errors="replace"),
    )


def canonical_chat_url(conversation_id: str) -> str:
    cleaned = conversation_id.strip()
    return f"https://chatgpt.com/c/{cleaned}"


def sanitize_delivery_key(delivery_key: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", delivery_key.strip())
    return cleaned or "delivery"


def deterministic_response_path(receipt_dir: Path | str, delivery_key: str) -> Path:
    safe_key = sanitize_delivery_key(delivery_key)
    return Path(receipt_dir) / f"{safe_key}.response.md"


def deterministic_receipt_path(receipt_dir: Path | str, delivery_key: str) -> Path:
    resp_path = deterministic_response_path(receipt_dir, delivery_key)
    return Path(f"{resp_path}.capture.json")


def validate_committed_receipt(
    receipt_path: Path,
    expected_endpoint: str,
    expected_chat_url: str,
) -> bool:
    try:
        if not receipt_path.is_file():
            return False
        data = json.loads(receipt_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False
        schema_version = data.get("schemaVersion")
        if schema_version != 2 or isinstance(schema_version, bool):
            return False
        if (
            str(data.get("browserEndpoint", "")).strip().rstrip("/")
            != expected_endpoint.strip().rstrip("/")
        ):
            return False
        if str(data.get("chatUrl", "")).strip() != expected_chat_url.strip():
            return False
        target_id = data.get("targetId")
        if not isinstance(target_id, str) or not target_id.strip():
            return False
        committed = data.get("committedUserTurn")
        if not isinstance(committed, dict):
            return False
        turn_id = committed.get("turnId")
        if not isinstance(turn_id, str) or not turn_id.strip():
            return False
        turn_index = committed.get("turnIndex")
        if type(turn_index) is not int or turn_index < 0:
            return False
        return True
    except Exception:
        return False


def _bound_detail(text: str, max_chars: int = MAX_DETAIL_CHARS) -> str:
    clean = text.strip()
    if len(clean) <= max_chars:
        return clean
    return clean[:max_chars] + "..."


class ReviewGptWakeTransport:
    """ Pluggable direct wake transport via external review-gpt CLI. """

    name: str = "review-gpt"

    def __init__(
        self,
        *,
        node_path: str | Path,
        cli_path: str | Path,
        config_path: str | Path,
        browser_endpoint: str,
        receipt_dir: str | Path,
        timeout_seconds: float = 60.0,
        process_runner: AsyncProcessRunner | None = None,
    ) -> None:
        self._node_path = Path(node_path).expanduser()
        self._cli_path = Path(cli_path).expanduser()
        self._config_path = Path(config_path).expanduser()
        self._browser_endpoint = str(browser_endpoint).strip()
        self._receipt_dir = Path(receipt_dir).expanduser()
        self._timeout_seconds = float(timeout_seconds)
        self._runner = process_runner or default_process_runner

    async def probe(self, target: WakeTarget) -> WakeProbeResult:
        canonical_url = canonical_chat_url(target.conversation_id)
        temp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        temp_path = Path(temp_file.name)
        temp_file.close()

        try:
            argv = [
                str(self._node_path),
                str(self._cli_path),
                "thread",
                "export",
                "--browser-endpoint",
                self._browser_endpoint,
                "--chat-url",
                canonical_url,
                "--output",
                str(temp_path),
            ]
            try:
                result = await self._runner(argv, self._timeout_seconds)
            except Exception as e:
                return WakeProbeResult(
                    ready=False,
                    owner_input_required=True,
                    detail=f"Probe process error: {_bound_detail(str(e))}",
                )

            if result.exit_code != 0:
                return WakeProbeResult(
                    ready=False,
                    owner_input_required=True,
                    detail=f"Probe failed with exit code {result.exit_code}: {_bound_detail(result.stderr or result.stdout)}",
                )

            if not temp_path.is_file():
                return WakeProbeResult(
                    ready=False,
                    owner_input_required=False,
                    detail="Probe export output missing",
                )

            try:
                export_data = json.loads(temp_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return WakeProbeResult(
                    ready=False,
                    owner_input_required=False,
                    detail="Probe export output is malformed JSON",
                )

            if not isinstance(export_data, dict):
                return WakeProbeResult(
                    ready=False,
                    owner_input_required=False,
                    detail="Probe export output format unexpected",
                )

            title = str(export_data.get("title", ""))
            body_text = str(export_data.get("bodyText", ""))
            combined = f"{title}\n{body_text}".lower()

            # Check Cloudflare challenge or login requirement
            if (
                "just a moment" in combined
                or "cloudflare" in combined
                or "log in" in combined
                or "login" in combined
                or "sign up" in combined
                or "welcome to chatgpt" in combined
            ):
                return WakeProbeResult(
                    ready=False,
                    owner_input_required=True,
                    detail="Target ChatGPT page requires login or Cloudflare verification",
                )

            chat_url = str(export_data.get("chatUrl", "")).strip()
            if chat_url != canonical_url:
                return WakeProbeResult(
                    ready=False,
                    owner_input_required=False,
                    detail=f"Target chat URL mismatch (expected: {canonical_url}, found: {chat_url})",
                )

            status_busy = bool(export_data.get("statusBusy", False))
            stop_visible = bool(export_data.get("stopVisible", False))
            if status_busy or stop_visible:
                return WakeProbeResult(
                    ready=False,
                    owner_input_required=False,
                    detail="ChatGPT target is actively generating (statusBusy or stopVisible)",
                )

            return WakeProbeResult(
                ready=True,
                owner_input_required=False,
                detail=None,
            )
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass

    async def deliver(self, request: WakeDeliveryRequest) -> WakeDeliveryResult:
        canonical_url = canonical_chat_url(request.target.conversation_id)
        resp_path = deterministic_response_path(self._receipt_dir, request.delivery_key)
        rec_path = deterministic_receipt_path(self._receipt_dir, request.delivery_key)

        # Before any send: check deterministic receipt
        if rec_path.is_file():
            if validate_committed_receipt(rec_path, self._browser_endpoint, canonical_url):
                return WakeDeliveryResult(
                    disposition="delivered",
                    detail="Existing valid committed turn receipt found",
                    receipt_path=rec_path,
                )
            # Malformed or belongs to another target => fail-closed uncertain without sending
            return WakeDeliveryResult(
                disposition="uncertain",
                detail="Existing receipt exists but is malformed or belongs to another target",
                receipt_path=rec_path,
            )

        self._receipt_dir.mkdir(parents=True, exist_ok=True)
        argv = [
            str(self._node_path),
            str(self._cli_path),
            "--config",
            str(self._config_path),
            "--chat-url",
            canonical_url,
            "--prompt",
            request.prompt,
            "--no-artifacts",
            "--no-zip",
            "--send",
            "--response-file",
            str(resp_path),
            "--format",
            "json",
            "--full-output",
        ]

        try:
            result = await self._runner(argv, self._timeout_seconds)
        except (FileNotFoundError, PermissionError, OSError) as e:
            return WakeDeliveryResult(
                disposition="not_submitted",
                detail=f"Process spawn failure before CLI start: {_bound_detail(str(e))}",
            )
        except Exception as e:
            if rec_path.is_file() and validate_committed_receipt(
                rec_path, self._browser_endpoint, canonical_url
            ):
                return WakeDeliveryResult(
                    disposition="delivered",
                    detail="Committed turn verified from receipt despite process exception",
                    receipt_path=rec_path,
                )
            return WakeDeliveryResult(
                disposition="uncertain",
                detail=f"Process execution error: {_bound_detail(str(e))}",
            )

        # Post-execution: valid receipt always wins
        if rec_path.is_file() and validate_committed_receipt(
            rec_path, self._browser_endpoint, canonical_url
        ):
            return WakeDeliveryResult(
                disposition="delivered",
                detail="Committed turn verified from receipt",
                receipt_path=rec_path,
            )

        output_text = f"{result.stdout}\n{result.stderr}"
        bounded_text = _bound_detail(
            result.stderr or result.stdout or f"exit code {result.exit_code}"
        )

        if result.exit_code == 0:
            return WakeDeliveryResult(
                disposition="uncertain",
                detail="CLI exited 0 without writing a valid committed turn receipt",
            )

        lower_out = output_text.lower()
        if "before auto-send" in lower_out:
            return WakeDeliveryResult(
                disposition="not_submitted",
                detail=f"Failure proven before auto-send: {bounded_text}",
            )

        if (
            "just a moment" in lower_out
            or "cloudflare" in lower_out
            or "log in" in lower_out
            or "login" in lower_out
            or "econnrefused" in lower_out
            or "unreachable" in lower_out
        ):
            return WakeDeliveryResult(
                disposition="owner_input_required",
                detail=f"Browser or login intervention required: {bounded_text}",
            )

        return WakeDeliveryResult(
            disposition="uncertain",
            detail=f"Process failed without proving delivery: {bounded_text}",
        )
