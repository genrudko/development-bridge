from __future__ import annotations

import asyncio
import json
import re
import tempfile
import urllib.request
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
BrowserEndpointProbe = Callable[[str], Awaitable[bool]]


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


async def default_browser_endpoint_probe(endpoint: str) -> bool:
    url = endpoint.rstrip("/") + "/json/version"

    def _probe() -> bool:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if response.status != 200:
                    return False
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
                return isinstance(payload, dict) and bool(payload.get("webSocketDebuggerUrl"))
        except Exception:
            return False

    return await asyncio.to_thread(_probe)


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


def is_owner_input_required_error(text: str) -> bool:
    """Classifies whether probe/delivery error output indicates owner intervention is required.

    Returns True ONLY when explicit evidence proves:
    - CDP/browser endpoint is unreachable/refused;
    - Cloudflare challenge page is active;
    - Login / authentication / sign-up is required.

    Transient errors (such as timeouts waiting for thread content, navigation timing,
    or generic non-zero CLI failures) return False so the coordinator can safely retry.
    """
    lower = text.lower()
    return any(
        marker in lower
        for marker in (
            "just a moment",
            "cloudflare",
            "log in",
            "login",
            "sign up",
            "welcome to chatgpt",
            "econnrefused",
            "unreachable",
            "connection refused",
            "failed to connect to browser endpoint",
            "browser endpoint unavailable",
        )
    )


class ReviewGptWakeTransport:
    """Pluggable direct wake transport via external review-gpt CLI."""

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
        browser_start_command: Sequence[str] | None = None,
        browser_stop_command: Sequence[str] | None = None,
        browser_lifecycle_timeout_seconds: float = 30.0,
        browser_endpoint_probe: BrowserEndpointProbe | None = None,
    ) -> None:
        self._node_path = Path(node_path).expanduser()
        self._cli_path = Path(cli_path).expanduser()
        self._config_path = Path(config_path).expanduser()
        self._browser_endpoint = str(browser_endpoint).strip()
        self._receipt_dir = Path(receipt_dir).expanduser()
        self._timeout_seconds = float(timeout_seconds)
        self._runner = process_runner or default_process_runner
        self._browser_start_command = tuple(str(part) for part in (browser_start_command or ()))
        self._browser_stop_command = tuple(str(part) for part in (browser_stop_command or ()))
        self._browser_lifecycle_timeout_seconds = float(browser_lifecycle_timeout_seconds)
        self._browser_endpoint_probe = browser_endpoint_probe or default_browser_endpoint_probe
        if bool(self._browser_start_command) != bool(self._browser_stop_command):
            raise ValueError("browser_start_command and browser_stop_command must be configured together")

    @property
    def on_demand_browser(self) -> bool:
        return bool(self._browser_start_command)

    async def _wait_for_browser_endpoint(self, *, ready: bool) -> bool:
        deadline = asyncio.get_running_loop().time() + self._browser_lifecycle_timeout_seconds
        while True:
            current = await self._browser_endpoint_probe(self._browser_endpoint)
            if current is ready:
                return True
            if asyncio.get_running_loop().time() >= deadline:
                return False
            await asyncio.sleep(0.2)

    async def _start_browser(self) -> str | None:
        if not self.on_demand_browser:
            return None
        try:
            result = await self._runner(
                self._browser_start_command, self._browser_lifecycle_timeout_seconds
            )
        except Exception as exc:
            return f"Browser start process error: {_bound_detail(str(exc))}"
        if result.exit_code != 0:
            return (
                f"Browser start failed with exit code {result.exit_code}: "
                f"{_bound_detail(result.stderr or result.stdout)}"
            )
        try:
            if not await self._wait_for_browser_endpoint(ready=True):
                return "Browser start command completed but CDP endpoint did not become ready"
        except Exception as exc:
            return f"Browser endpoint readiness probe failed after start: {_bound_detail(str(exc))}"
        return None

    async def _stop_browser(self) -> str | None:
        if not self.on_demand_browser:
            return None
        try:
            result = await self._runner(
                self._browser_stop_command, self._browser_lifecycle_timeout_seconds
            )
        except Exception as exc:
            return f"Browser stop process error: {_bound_detail(str(exc))}"
        if result.exit_code != 0:
            return (
                f"Browser stop failed with exit code {result.exit_code}: "
                f"{_bound_detail(result.stderr or result.stdout)}"
            )
        try:
            if not await self._wait_for_browser_endpoint(ready=False):
                return "Browser stop command completed but CDP endpoint remained ready"
        except Exception as exc:
            return f"Browser endpoint readiness probe failed after stop: {_bound_detail(str(exc))}"
        return None

    async def _probe_connected(self, target: WakeTarget) -> WakeProbeResult:
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
                err_text = str(e)
                return WakeProbeResult(
                    ready=False,
                    owner_input_required=is_owner_input_required_error(err_text),
                    detail=f"Probe process error: {_bound_detail(err_text)}",
                )

            if result.exit_code != 0:
                error_output = f"{result.stderr}\n{result.stdout}".strip()
                return WakeProbeResult(
                    ready=False,
                    owner_input_required=is_owner_input_required_error(error_output),
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
            if is_owner_input_required_error(title):
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

            return WakeProbeResult(ready=True, owner_input_required=False, detail=None)
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass

    async def probe(self, target: WakeTarget) -> WakeProbeResult:
        if not self.on_demand_browser:
            return await self._probe_connected(target)

        start_error = await self._start_browser()
        if start_error is not None:
            cleanup_error = await self._stop_browser()
            detail = start_error
            if cleanup_error:
                detail += f"; cleanup also failed: {cleanup_error}"
            return WakeProbeResult(ready=False, owner_input_required=False, detail=detail)

        try:
            result = await self._probe_connected(target)
        finally:
            cleanup_error = await self._stop_browser()
        if cleanup_error:
            return WakeProbeResult(
                ready=False,
                owner_input_required=False,
                detail=f"Browser cleanup failed after probe: {cleanup_error}",
            )
        return result

    async def _deliver_connected(
        self,
        request: WakeDeliveryRequest,
        *,
        canonical_url: str,
        navigation_url: str,
        resp_path: Path,
        rec_path: Path,
    ) -> WakeDeliveryResult:
        argv = [
            str(self._node_path),
            str(self._cli_path),
            "--config",
            str(self._config_path),
            "--chat-url",
            navigation_url,
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

        if is_owner_input_required_error(lower_out):
            return WakeDeliveryResult(
                disposition="owner_input_required",
                detail=f"Browser or login intervention required: {bounded_text}",
            )

        return WakeDeliveryResult(
            disposition="uncertain",
            detail=f"Process failed without proving delivery: {bounded_text}",
        )

    @staticmethod
    def _with_cleanup_detail(
        result: WakeDeliveryResult, cleanup_error: str | None
    ) -> WakeDeliveryResult:
        if not cleanup_error:
            return result
        detail = f"{result.detail or result.disposition}; browser cleanup failed: {cleanup_error}"
        return WakeDeliveryResult(
            disposition=result.disposition,
            detail=detail,
            receipt_path=result.receipt_path,
        )

    async def deliver(self, request: WakeDeliveryRequest) -> WakeDeliveryResult:
        canonical_url = canonical_chat_url(request.target.conversation_id)
        navigation_url = request.target.route_url.strip() or canonical_url
        resp_path = deterministic_response_path(self._receipt_dir, request.delivery_key)
        rec_path = deterministic_receipt_path(self._receipt_dir, request.delivery_key)

        if rec_path.is_file():
            if validate_committed_receipt(rec_path, self._browser_endpoint, canonical_url):
                return WakeDeliveryResult(
                    disposition="delivered",
                    detail="Existing valid committed turn receipt found",
                    receipt_path=rec_path,
                )
            return WakeDeliveryResult(
                disposition="uncertain",
                detail="Existing receipt exists but is malformed or belongs to another target",
                receipt_path=rec_path,
            )

        self._receipt_dir.mkdir(parents=True, exist_ok=True)

        if not self.on_demand_browser:
            return await self._deliver_connected(
                request,
                canonical_url=canonical_url,
                navigation_url=navigation_url,
                resp_path=resp_path,
                rec_path=rec_path,
            )

        start_error = await self._start_browser()
        if start_error is not None:
            cleanup_error = await self._stop_browser()
            detail = start_error
            if cleanup_error:
                detail += f"; cleanup also failed: {cleanup_error}"
            return WakeDeliveryResult(disposition="not_submitted", detail=detail)

        result: WakeDeliveryResult
        try:
            preflight = await self._probe_connected(request.target)
            if not preflight.ready:
                result = WakeDeliveryResult(
                    disposition=(
                        "owner_input_required"
                        if preflight.owner_input_required
                        else "not_submitted"
                    ),
                    detail=f"Cold browser preflight blocked send: {preflight.detail or 'not ready'}",
                )
            else:
                result = await self._deliver_connected(
                    request,
                    canonical_url=canonical_url,
                    navigation_url=navigation_url,
                    resp_path=resp_path,
                    rec_path=rec_path,
                )
        finally:
            cleanup_error = await self._stop_browser()

        return self._with_cleanup_detail(result, cleanup_error)
