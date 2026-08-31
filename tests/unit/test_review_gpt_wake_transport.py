from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Sequence

import pytest

from app.coordinator.review_gpt_transport import (
    ProcessResult,
    ReviewGptWakeTransport,
    canonical_chat_url,
    deterministic_receipt_path,
    deterministic_response_path,
    sanitize_delivery_key,
    validate_committed_receipt,
)
from app.coordinator.wake_transport import (
    WakeDeliveryRequest,
    WakeDeliveryResult,
    WakeProbeResult,
    WakeTarget,
    WakeTransport,
)


class FakeProcessRunner:
    """Offline fake async process runner for testing ReviewGptWakeTransport."""

    def __init__(
        self,
        *,
        exit_code: int = 0,
        stdout: str = "",
        stderr: str = "",
        on_run: callable | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.on_run = on_run
        self.exc = exc
        self.calls: list[tuple[Sequence[str], float]] = []

    async def __call__(self, argv: Sequence[str], timeout: float) -> ProcessResult:
        self.calls.append((argv, timeout))
        if self.exc is not None:
            raise self.exc
        if self.on_run is not None:
            self.on_run(argv, timeout)
        return ProcessResult(
            exit_code=self.exit_code,
            stdout=self.stdout,
            stderr=self.stderr,
        )


def _make_valid_receipt_dict(
    *,
    browser_endpoint: str = "http://127.0.0.1:9222",
    chat_url: str = "https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3",
    target_id: str = "TARGET-123",
    turn_id: str = "turn-456",
    turn_index: int = 0,
) -> dict:
    return {
        "schemaVersion": 2,
        "browserEndpoint": browser_endpoint,
        "chatUrl": chat_url,
        "targetId": target_id,
        "committedUserTurn": {
            "turnId": turn_id,
            "turnIndex": turn_index,
        },
    }


def test_contract_shapes_and_protocol(tmp_path: Path):
    target = WakeTarget(
        route_id="r1",
        channel_id="c1",
        conversation_id="67c1e309-548c-8005-b0ff-90a6ea5e01b3",
        route_url="https://chatgpt.com/g/g-p-123/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3",
    )
    assert target.route_id == "r1"
    assert target.channel_id == "c1"
    assert target.conversation_id == "67c1e309-548c-8005-b0ff-90a6ea5e01b3"
    assert target.route_url == "https://chatgpt.com/g/g-p-123/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3"

    with pytest.raises(AttributeError):
        target.route_id = "r2"  # frozen

    probe_res = WakeProbeResult(ready=True, owner_input_required=False, detail="ok")
    assert probe_res.ready is True
    assert probe_res.owner_input_required is False
    assert probe_res.detail == "ok"

    req = WakeDeliveryRequest(
        target=target,
        continuation_id="wake_cont_123",
        prompt="DBRIDGE_CONTINUE wake_cont_123",
        delivery_key="wake_cont_123",
    )
    assert req.continuation_id == "wake_cont_123"

    deliv_res = WakeDeliveryResult(
        disposition="delivered",
        detail="success",
        receipt_path=tmp_path / "rec.json",
    )
    assert deliv_res.disposition == "delivered"
    assert deliv_res.receipt_path == tmp_path / "rec.json"

    runner = FakeProcessRunner()
    transport = ReviewGptWakeTransport(
        node_path="/usr/bin/node",
        cli_path="/opt/review-gpt/cli.js",
        config_path=tmp_path / "config.json",
        browser_endpoint="http://127.0.0.1:9222",
        receipt_dir=tmp_path / "receipts",
        timeout_seconds=30.0,
        process_runner=runner,
    )
    assert transport.name == "review-gpt"
    assert isinstance(transport, WakeTransport)


def test_canonical_chat_url():
    conv_id = "67c1e309-548c-8005-b0ff-90a6ea5e01b3"
    assert (
        canonical_chat_url(conv_id)
        == "https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3"
    )
    assert (
        canonical_chat_url(f"  {conv_id}  ")
        == "https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3"
    )


@pytest.mark.asyncio
async def test_probe_exact_conversation_success(tmp_path: Path):
    target = WakeTarget(
        route_id="r1",
        channel_id="c1",
        conversation_id="67c1e309-548c-8005-b0ff-90a6ea5e01b3",
        route_url="https://chatgpt.com/g/g-p-123/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3",
    )
    canonical = "https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3"

    def write_export_file(argv: Sequence[str], timeout: float):
        output_idx = argv.index("--output") + 1
        out_path = Path(argv[output_idx])
        payload = {
            "chatUrl": canonical,
            "statusBusy": False,
            "stopVisible": False,
            "title": "Development Bridge Conversation",
            "bodyText": "Ready for instruction",
        }
        out_path.write_text(json.dumps(payload), encoding="utf-8")

    runner = FakeProcessRunner(on_run=write_export_file)
    transport = ReviewGptWakeTransport(
        node_path="/usr/bin/node",
        cli_path="/opt/review-gpt/cli.js",
        config_path=tmp_path / "config.json",
        browser_endpoint="http://127.0.0.1:9222",
        receipt_dir=tmp_path / "receipts",
        process_runner=runner,
    )

    result = await transport.probe(target)
    assert result.ready is True
    assert result.owner_input_required is False
    assert len(runner.calls) == 1

    argv, timeout = runner.calls[0]
    assert argv[0] == "/usr/bin/node"
    assert argv[1] == "/opt/review-gpt/cli.js"
    assert list(argv[2:4]) == ["thread", "export"]
    assert "--browser-endpoint" in argv
    assert argv[argv.index("--browser-endpoint") + 1] == "http://127.0.0.1:9222"
    assert "--chat-url" in argv
    assert argv[argv.index("--chat-url") + 1] == canonical
    assert "--send" not in argv


@pytest.mark.asyncio
async def test_probe_rejects_mismatched_chat_url(tmp_path: Path):
    target = WakeTarget(
        route_id="r1",
        channel_id="c1",
        conversation_id="67c1e309-548c-8005-b0ff-90a6ea5e01b3",
        route_url="https://chatgpt.com/g/g-p-123/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3",
    )

    def write_mismatched_export(argv: Sequence[str], timeout: float):
        output_idx = argv.index("--output") + 1
        out_path = Path(argv[output_idx])
        payload = {
            "chatUrl": "https://chatgpt.com/c/00000000-0000-0000-0000-000000000000",
            "statusBusy": False,
            "stopVisible": False,
            "title": "Other conversation",
            "bodyText": "Hello",
        }
        out_path.write_text(json.dumps(payload), encoding="utf-8")

    runner = FakeProcessRunner(on_run=write_mismatched_export)
    transport = ReviewGptWakeTransport(
        node_path="/usr/bin/node",
        cli_path="/opt/review-gpt/cli.js",
        config_path=tmp_path / "config.json",
        browser_endpoint="http://127.0.0.1:9222",
        receipt_dir=tmp_path / "receipts",
        process_runner=runner,
    )

    result = await transport.probe(target)
    assert result.ready is False
    assert result.owner_input_required is False


@pytest.mark.asyncio
async def test_probe_rejects_busy_and_stop_visible_as_transient_not_ready(tmp_path: Path):
    target = WakeTarget(
        route_id="r1",
        channel_id="c1",
        conversation_id="67c1e309-548c-8005-b0ff-90a6ea5e01b3",
        route_url="https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3",
    )
    canonical = "https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3"

    for busy, stop in [(True, False), (False, True), (True, True)]:
        def write_busy_export(argv: Sequence[str], timeout: float, b=busy, s=stop):
            output_idx = argv.index("--output") + 1
            out_path = Path(argv[output_idx])
            payload = {
                "chatUrl": canonical,
                "statusBusy": b,
                "stopVisible": s,
                "title": "Working...",
                "bodyText": "Thinking...",
            }
            out_path.write_text(json.dumps(payload), encoding="utf-8")

        runner = FakeProcessRunner(on_run=write_busy_export)
        transport = ReviewGptWakeTransport(
            node_path="/usr/bin/node",
            cli_path="/opt/review-gpt/cli.js",
            config_path=tmp_path / "config.json",
            browser_endpoint="http://127.0.0.1:9222",
            receipt_dir=tmp_path / "receipts",
            process_runner=runner,
        )

        result = await transport.probe(target)
        assert result.ready is False
        assert result.owner_input_required is False


@pytest.mark.asyncio
async def test_probe_classifies_cloudflare_and_login_as_owner_input_required(tmp_path: Path):
    target = WakeTarget(
        route_id="r1",
        channel_id="c1",
        conversation_id="67c1e309-548c-8005-b0ff-90a6ea5e01b3",
        route_url="https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3",
    )
    canonical = "https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3"

    cases = [
        {"title": "Just a moment...", "bodyText": "Checking your browser before accessing chatgpt.com."},
        {"title": "ChatGPT - Log in or Sign up", "bodyText": "Log in with your OpenAI account to continue"},
        {"title": "ChatGPT", "bodyText": "Welcome to ChatGPT. Log in to get started."},
    ]

    for case in cases:
        def write_cf_export(argv: Sequence[str], timeout: float, c=case):
            output_idx = argv.index("--output") + 1
            out_path = Path(argv[output_idx])
            payload = {
                "chatUrl": canonical,
                "statusBusy": False,
                "stopVisible": False,
                "title": c["title"],
                "bodyText": c["bodyText"],
            }
            out_path.write_text(json.dumps(payload), encoding="utf-8")

        runner = FakeProcessRunner(on_run=write_cf_export)
        transport = ReviewGptWakeTransport(
            node_path="/usr/bin/node",
            cli_path="/opt/review-gpt/cli.js",
            config_path=tmp_path / "config.json",
            browser_endpoint="http://127.0.0.1:9222",
            receipt_dir=tmp_path / "receipts",
            process_runner=runner,
        )

        result = await transport.probe(target)
        assert result.ready is False
        assert result.owner_input_required is True


@pytest.mark.asyncio
async def test_probe_process_failure_is_owner_input_required_and_never_sends(tmp_path: Path):
    target = WakeTarget(
        route_id="r1",
        channel_id="c1",
        conversation_id="67c1e309-548c-8005-b0ff-90a6ea5e01b3",
        route_url="https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3",
    )

    runner = FakeProcessRunner(
        exit_code=1,
        stderr="Failed to connect to browser endpoint http://127.0.0.1:9222: ECONNREFUSED",
    )
    transport = ReviewGptWakeTransport(
        node_path="/usr/bin/node",
        cli_path="/opt/review-gpt/cli.js",
        config_path=tmp_path / "config.json",
        browser_endpoint="http://127.0.0.1:9222",
        receipt_dir=tmp_path / "receipts",
        process_runner=runner,
    )

    result = await transport.probe(target)
    assert result.ready is False
    assert result.owner_input_required is True
    assert "--send" not in runner.calls[0][0]


@pytest.mark.asyncio
async def test_probe_thread_content_timeout_is_transient_not_owner_input(tmp_path: Path):
    target = WakeTarget(
        route_id="r1",
        channel_id="c1",
        conversation_id="67c1e309-548c-8005-b0ff-90a6ea5e01b3",
        route_url="https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3",
    )

    # Production-discovered failure case:
    # exit code 1 with UNKNOWN and "Timed out waiting for ChatGPT thread content"
    error_output = (
        '{"code": "UNKNOWN", "message": '
        '"Timed out waiting for ChatGPT thread content for https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3"}'
    )
    runner = FakeProcessRunner(
        exit_code=1,
        stderr=error_output,
    )
    transport = ReviewGptWakeTransport(
        node_path="/usr/bin/node",
        cli_path="/opt/review-gpt/cli.js",
        config_path=tmp_path / "config.json",
        browser_endpoint="http://127.0.0.1:9222",
        receipt_dir=tmp_path / "receipts",
        process_runner=runner,
    )

    result = await transport.probe(target)
    assert result.ready is False
    assert result.owner_input_required is False
    assert "Timed out waiting for ChatGPT thread content" in (result.detail or "")
    assert "--send" not in runner.calls[0][0]


@pytest.mark.asyncio
async def test_probe_generic_nonzero_failure_is_transient_not_owner_input(tmp_path: Path):
    target = WakeTarget(
        route_id="r1",
        channel_id="c1",
        conversation_id="67c1e309-548c-8005-b0ff-90a6ea5e01b3",
        route_url="https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3",
    )

    generic_errors = [
        "Error: Navigation timeout of 30000 ms exceeded",
        '{"code": "UNKNOWN", "message": "Unknown internal error"}',
        "Process failed unexpectedly with code 1",
    ]

    for err in generic_errors:
        runner = FakeProcessRunner(exit_code=1, stderr=err)
        transport = ReviewGptWakeTransport(
            node_path="/usr/bin/node",
            cli_path="/opt/review-gpt/cli.js",
            config_path=tmp_path / "config.json",
            browser_endpoint="http://127.0.0.1:9222",
            receipt_dir=tmp_path / "receipts",
            process_runner=runner,
        )
        result = await transport.probe(target)
        assert result.ready is False
        assert result.owner_input_required is False
        assert "--send" not in runner.calls[0][0]


@pytest.mark.asyncio
async def test_probe_explicit_endpoint_and_auth_nonzero_failure_requires_owner_input(tmp_path: Path):
    target = WakeTarget(
        route_id="r1",
        channel_id="c1",
        conversation_id="67c1e309-548c-8005-b0ff-90a6ea5e01b3",
        route_url="https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3",
    )

    explicit_owner_errors = [
        "connect ECONNREFUSED 127.0.0.1:9222",
        "Failed to connect to browser endpoint http://127.0.0.1:9222",
        "Browser endpoint unreachable",
        "Cloudflare challenge detected: Just a moment...",
        "Please log in or sign up to continue",
        "Welcome to ChatGPT. Log in to get started.",
    ]

    for err in explicit_owner_errors:
        runner = FakeProcessRunner(exit_code=1, stderr=err)
        transport = ReviewGptWakeTransport(
            node_path="/usr/bin/node",
            cli_path="/opt/review-gpt/cli.js",
            config_path=tmp_path / "config.json",
            browser_endpoint="http://127.0.0.1:9222",
            receipt_dir=tmp_path / "receipts",
            process_runner=runner,
        )
        result = await transport.probe(target)
        assert result.ready is False
        assert result.owner_input_required is True
        assert "--send" not in runner.calls[0][0]


@pytest.mark.asyncio
async def test_probe_runner_exception_classification(tmp_path: Path):
    target = WakeTarget(
        route_id="r1",
        channel_id="c1",
        conversation_id="67c1e309-548c-8005-b0ff-90a6ea5e01b3",
        route_url="https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3",
    )

    # 1. Generic runner exception (e.g. timeout or spawn failure without endpoint evidence) -> transient
    generic_exceptions = [
        TimeoutError("Process timed out after 60.0s: /usr/bin/node"),
        RuntimeError("Internal spawn error"),
        OSError("Generic I/O error"),
    ]
    for exc in generic_exceptions:
        runner = FakeProcessRunner(exc=exc)
        transport = ReviewGptWakeTransport(
            node_path="/usr/bin/node",
            cli_path="/opt/review-gpt/cli.js",
            config_path=tmp_path / "config.json",
            browser_endpoint="http://127.0.0.1:9222",
            receipt_dir=tmp_path / "receipts",
            process_runner=runner,
        )
        result = await transport.probe(target)
        assert result.ready is False
        assert result.owner_input_required is False
        assert "--send" not in runner.calls[0][0]

    # 2. Runner exception proving endpoint/connection failure -> owner_input_required
    owner_exceptions = [
        ConnectionRefusedError("connect ECONNREFUSED 127.0.0.1:9222"),
        RuntimeError("Browser endpoint unreachable at http://127.0.0.1:9222"),
    ]
    for exc in owner_exceptions:
        runner = FakeProcessRunner(exc=exc)
        transport = ReviewGptWakeTransport(
            node_path="/usr/bin/node",
            cli_path="/opt/review-gpt/cli.js",
            config_path=tmp_path / "config.json",
            browser_endpoint="http://127.0.0.1:9222",
            receipt_dir=tmp_path / "receipts",
            process_runner=runner,
        )
        result = await transport.probe(target)
        assert result.ready is False
        assert result.owner_input_required is True
        assert "--send" not in runner.calls[0][0]



def test_deterministic_response_and_receipt_paths(tmp_path: Path):
    receipt_dir = tmp_path / "receipts"
    key = "wake_cont_123-abc"
    resp_path = deterministic_response_path(receipt_dir, key)
    rec_path = deterministic_receipt_path(receipt_dir, key)

    assert resp_path == receipt_dir / "wake_cont_123-abc.response.md"
    assert rec_path == receipt_dir / "wake_cont_123-abc.response.md.capture.json"

    # Sanitization of malicious / weird characters in key
    unsafe_key = "../secret/key:1*?"
    safe_resp_path = deterministic_response_path(receipt_dir, unsafe_key)
    assert ".." not in safe_resp_path.name
    assert ":" not in safe_resp_path.name
    assert safe_resp_path.parent == receipt_dir


def test_validate_committed_receipt(tmp_path: Path):
    endpoint = "http://127.0.0.1:9222"
    canonical = "https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3"
    rec_file = tmp_path / "valid.capture.json"

    valid_dict = _make_valid_receipt_dict(
        browser_endpoint=endpoint,
        chat_url=canonical,
        target_id="T1",
        turn_id="turn-1",
        turn_index=2,
    )
    rec_file.write_text(json.dumps(valid_dict), encoding="utf-8")
    assert validate_committed_receipt(rec_file, expected_endpoint=endpoint, expected_chat_url=canonical) is True

    # Bad schemaVersion
    bad_schema = dict(valid_dict, schemaVersion=1)
    rec_file.write_text(json.dumps(bad_schema), encoding="utf-8")
    assert validate_committed_receipt(rec_file, expected_endpoint=endpoint, expected_chat_url=canonical) is False

    # Mismatched chatUrl
    bad_chat = dict(valid_dict, chatUrl="https://chatgpt.com/c/other")
    rec_file.write_text(json.dumps(bad_chat), encoding="utf-8")
    assert validate_committed_receipt(rec_file, expected_endpoint=endpoint, expected_chat_url=canonical) is False

    # Mismatched browserEndpoint
    bad_ep = dict(valid_dict, browserEndpoint="http://127.0.0.1:9333")
    rec_file.write_text(json.dumps(bad_ep), encoding="utf-8")
    assert validate_committed_receipt(rec_file, expected_endpoint=endpoint, expected_chat_url=canonical) is False

    # Empty targetId
    bad_target = dict(valid_dict, targetId="")
    rec_file.write_text(json.dumps(bad_target), encoding="utf-8")
    assert validate_committed_receipt(rec_file, expected_endpoint=endpoint, expected_chat_url=canonical) is False

    # Missing committedUserTurn / empty turnId / negative index
    bad_turn1 = dict(valid_dict, committedUserTurn={"turnId": "", "turnIndex": 0})
    rec_file.write_text(json.dumps(bad_turn1), encoding="utf-8")
    assert validate_committed_receipt(rec_file, expected_endpoint=endpoint, expected_chat_url=canonical) is False

    bad_turn2 = dict(valid_dict, committedUserTurn={"turnId": "turn-1", "turnIndex": -1})
    rec_file.write_text(json.dumps(bad_turn2), encoding="utf-8")
    assert validate_committed_receipt(rec_file, expected_endpoint=endpoint, expected_chat_url=canonical) is False

    # Malformed json
    rec_file.write_text("{not valid json", encoding="utf-8")
    assert validate_committed_receipt(rec_file, expected_endpoint=endpoint, expected_chat_url=canonical) is False


@pytest.mark.asyncio
async def test_delivery_argv_structure(tmp_path: Path):
    target = WakeTarget(
        route_id="r1",
        channel_id="c1",
        conversation_id="67c1e309-548c-8005-b0ff-90a6ea5e01b3",
        route_url="https://chatgpt.com/g/g-p-123/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3",
    )
    req = WakeDeliveryRequest(
        target=target,
        continuation_id="cont_123",
        prompt="DBRIDGE_CONTINUE cont_123 prompt text",
        delivery_key="cont_123",
    )
    receipt_dir = tmp_path / "receipts"
    canonical = "https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3"
    rec_file = deterministic_receipt_path(receipt_dir, "cont_123")

    def write_receipt_on_deliver(argv: Sequence[str], timeout: float):
        rec_file.parent.mkdir(parents=True, exist_ok=True)
        rec_file.write_text(json.dumps(_make_valid_receipt_dict(chat_url=canonical)), encoding="utf-8")

    runner = FakeProcessRunner(on_run=write_receipt_on_deliver)
    transport = ReviewGptWakeTransport(
        node_path="/usr/bin/node",
        cli_path="/opt/review-gpt/cli.js",
        config_path=tmp_path / "review-gpt.config.json",
        browser_endpoint="http://127.0.0.1:9222",
        receipt_dir=receipt_dir,
        process_runner=runner,
    )

    result = await transport.deliver(req)
    assert result.disposition == "delivered"
    assert len(runner.calls) == 1

    argv, timeout = runner.calls[0]
    assert argv[0] == "/usr/bin/node"
    assert argv[1] == "/opt/review-gpt/cli.js"
    assert "--config" in argv
    assert argv[argv.index("--config") + 1] == str(tmp_path / "review-gpt.config.json")
    assert "--chat-url" in argv
    assert argv[argv.index("--chat-url") + 1] == canonical
    assert "--prompt" in argv
    assert argv[argv.index("--prompt") + 1] == "DBRIDGE_CONTINUE cont_123 prompt text"
    assert "--no-artifacts" in argv
    assert "--no-zip" in argv
    assert "--send" in argv
    assert "--response-file" in argv
    assert argv[argv.index("--response-file") + 1] == str(deterministic_response_path(receipt_dir, "cont_123"))
    assert "--format" in argv
    assert argv[argv.index("--format") + 1] == "json"
    assert "--full-output" in argv


@pytest.mark.asyncio
async def test_existing_valid_receipt_delivers_without_process_call(tmp_path: Path):
    target = WakeTarget(
        route_id="r1",
        channel_id="c1",
        conversation_id="67c1e309-548c-8005-b0ff-90a6ea5e01b3",
        route_url="https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3",
    )
    req = WakeDeliveryRequest(
        target=target,
        continuation_id="cont_already_done",
        prompt="DBRIDGE_CONTINUE cont_already_done",
        delivery_key="cont_already_done",
    )
    receipt_dir = tmp_path / "receipts"
    canonical = "https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3"
    rec_file = deterministic_receipt_path(receipt_dir, "cont_already_done")
    rec_file.parent.mkdir(parents=True, exist_ok=True)
    rec_file.write_text(json.dumps(_make_valid_receipt_dict(chat_url=canonical)), encoding="utf-8")

    runner = FakeProcessRunner()
    transport = ReviewGptWakeTransport(
        node_path="/usr/bin/node",
        cli_path="/opt/review-gpt/cli.js",
        config_path=tmp_path / "config.json",
        browser_endpoint="http://127.0.0.1:9222",
        receipt_dir=receipt_dir,
        process_runner=runner,
    )

    result = await transport.deliver(req)
    assert result.disposition == "delivered"
    assert result.receipt_path == rec_file
    assert len(runner.calls) == 0  # Proof that process runner was never called!


@pytest.mark.asyncio
async def test_existing_malformed_receipt_returns_uncertain_without_process_call(tmp_path: Path):
    target = WakeTarget(
        route_id="r1",
        channel_id="c1",
        conversation_id="67c1e309-548c-8005-b0ff-90a6ea5e01b3",
        route_url="https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3",
    )
    req = WakeDeliveryRequest(
        target=target,
        continuation_id="cont_malformed",
        prompt="DBRIDGE_CONTINUE cont_malformed",
        delivery_key="cont_malformed",
    )
    receipt_dir = tmp_path / "receipts"
    rec_file = deterministic_receipt_path(receipt_dir, "cont_malformed")
    rec_file.parent.mkdir(parents=True, exist_ok=True)
    rec_file.write_text("CORRUPTED_JSON_CONTENT", encoding="utf-8")

    runner = FakeProcessRunner()
    transport = ReviewGptWakeTransport(
        node_path="/usr/bin/node",
        cli_path="/opt/review-gpt/cli.js",
        config_path=tmp_path / "config.json",
        browser_endpoint="http://127.0.0.1:9222",
        receipt_dir=receipt_dir,
        process_runner=runner,
    )

    result = await transport.deliver(req)
    assert result.disposition == "uncertain"
    assert len(runner.calls) == 0  # Fail-closed without calling runner


@pytest.mark.asyncio
async def test_successful_cli_exit_with_valid_receipt_delivers(tmp_path: Path):
    target = WakeTarget(
        route_id="r1",
        channel_id="c1",
        conversation_id="67c1e309-548c-8005-b0ff-90a6ea5e01b3",
        route_url="https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3",
    )
    req = WakeDeliveryRequest(
        target=target,
        continuation_id="cont_success",
        prompt="DBRIDGE_CONTINUE cont_success",
        delivery_key="cont_success",
    )
    receipt_dir = tmp_path / "receipts"
    canonical = "https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3"
    rec_file = deterministic_receipt_path(receipt_dir, "cont_success")

    def write_receipt(argv: Sequence[str], timeout: float):
        rec_file.parent.mkdir(parents=True, exist_ok=True)
        rec_file.write_text(json.dumps(_make_valid_receipt_dict(chat_url=canonical)), encoding="utf-8")

    runner = FakeProcessRunner(exit_code=0, on_run=write_receipt)
    transport = ReviewGptWakeTransport(
        node_path="/usr/bin/node",
        cli_path="/opt/review-gpt/cli.js",
        config_path=tmp_path / "config.json",
        browser_endpoint="http://127.0.0.1:9222",
        receipt_dir=receipt_dir,
        process_runner=runner,
    )

    result = await transport.deliver(req)
    assert result.disposition == "delivered"
    assert result.receipt_path == rec_file


@pytest.mark.asyncio
async def test_exit_0_without_receipt_is_uncertain(tmp_path: Path):
    target = WakeTarget(
        route_id="r1",
        channel_id="c1",
        conversation_id="67c1e309-548c-8005-b0ff-90a6ea5e01b3",
        route_url="https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3",
    )
    req = WakeDeliveryRequest(
        target=target,
        continuation_id="cont_no_receipt",
        prompt="DBRIDGE_CONTINUE cont_no_receipt",
        delivery_key="cont_no_receipt",
    )
    receipt_dir = tmp_path / "receipts"

    runner = FakeProcessRunner(exit_code=0, stdout="Exited cleanly but did not produce sidecar")
    transport = ReviewGptWakeTransport(
        node_path="/usr/bin/node",
        cli_path="/opt/review-gpt/cli.js",
        config_path=tmp_path / "config.json",
        browser_endpoint="http://127.0.0.1:9222",
        receipt_dir=receipt_dir,
        process_runner=runner,
    )

    result = await transport.deliver(req)
    assert result.disposition == "uncertain"


@pytest.mark.asyncio
async def test_nonzero_exit_with_valid_receipt_delivers(tmp_path: Path):
    target = WakeTarget(
        route_id="r1",
        channel_id="c1",
        conversation_id="67c1e309-548c-8005-b0ff-90a6ea5e01b3",
        route_url="https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3",
    )
    req = WakeDeliveryRequest(
        target=target,
        continuation_id="cont_nonzero_with_receipt",
        prompt="DBRIDGE_CONTINUE cont_nonzero_with_receipt",
        delivery_key="cont_nonzero_with_receipt",
    )
    receipt_dir = tmp_path / "receipts"
    canonical = "https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3"
    rec_file = deterministic_receipt_path(receipt_dir, "cont_nonzero_with_receipt")

    def write_receipt(argv: Sequence[str], timeout: float):
        rec_file.parent.mkdir(parents=True, exist_ok=True)
        rec_file.write_text(json.dumps(_make_valid_receipt_dict(chat_url=canonical)), encoding="utf-8")

    runner = FakeProcessRunner(exit_code=1, stderr="Post-send timeout while waiting for completion", on_run=write_receipt)
    transport = ReviewGptWakeTransport(
        node_path="/usr/bin/node",
        cli_path="/opt/review-gpt/cli.js",
        config_path=tmp_path / "config.json",
        browser_endpoint="http://127.0.0.1:9222",
        receipt_dir=receipt_dir,
        process_runner=runner,
    )

    result = await transport.deliver(req)
    assert result.disposition == "delivered"
    assert result.receipt_path == rec_file


@pytest.mark.asyncio
async def test_nonzero_exit_without_receipt_classification(tmp_path: Path):
    target = WakeTarget(
        route_id="r1",
        channel_id="c1",
        conversation_id="67c1e309-548c-8005-b0ff-90a6ea5e01b3",
        route_url="https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3",
    )
    receipt_dir = tmp_path / "receipts"

    # Case A: Generic nonzero without receipt -> uncertain
    req_a = WakeDeliveryRequest(
        target=target,
        continuation_id="cont_generic_fail",
        prompt="DBRIDGE_CONTINUE cont_generic_fail",
        delivery_key="cont_generic_fail",
    )
    runner_a = FakeProcessRunner(exit_code=1, stderr="Connection reset midway")
    transport_a = ReviewGptWakeTransport(
        node_path="/usr/bin/node",
        cli_path="/opt/review-gpt/cli.js",
        config_path=tmp_path / "config.json",
        browser_endpoint="http://127.0.0.1:9222",
        receipt_dir=receipt_dir,
        process_runner=runner_a,
    )
    res_a = await transport_a.deliver(req_a)
    assert res_a.disposition == "uncertain"

    # Case B: Explicit before auto-send failure -> not_submitted
    req_b = WakeDeliveryRequest(
        target=target,
        continuation_id="cont_presubmit_fail",
        prompt="DBRIDGE_CONTINUE cont_presubmit_fail",
        delivery_key="cont_presubmit_fail",
    )
    runner_b = FakeProcessRunner(exit_code=1, stderr="Error before auto-send: validation failed on prompt flags")
    transport_b = ReviewGptWakeTransport(
        node_path="/usr/bin/node",
        cli_path="/opt/review-gpt/cli.js",
        config_path=tmp_path / "config.json",
        browser_endpoint="http://127.0.0.1:9222",
        receipt_dir=receipt_dir,
        process_runner=runner_b,
    )
    res_b = await transport_b.deliver(req_b)
    assert res_b.disposition == "not_submitted"

    # Case C: Explicit Cloudflare/login evidence before submission -> owner_input_required
    req_c = WakeDeliveryRequest(
        target=target,
        continuation_id="cont_cf_fail",
        prompt="DBRIDGE_CONTINUE cont_cf_fail",
        delivery_key="cont_cf_fail",
    )
    runner_c = FakeProcessRunner(exit_code=1, stderr="Cloudflare challenge detected: Just a moment...")
    transport_c = ReviewGptWakeTransport(
        node_path="/usr/bin/node",
        cli_path="/opt/review-gpt/cli.js",
        config_path=tmp_path / "config.json",
        browser_endpoint="http://127.0.0.1:9222",
        receipt_dir=receipt_dir,
        process_runner=runner_c,
    )
    res_c = await transport_c.deliver(req_c)
    assert res_c.disposition == "owner_input_required"


@pytest.mark.asyncio
async def test_spawn_failure_is_not_submitted(tmp_path: Path):
    target = WakeTarget(
        route_id="r1",
        channel_id="c1",
        conversation_id="67c1e309-548c-8005-b0ff-90a6ea5e01b3",
        route_url="https://chatgpt.com/c/67c1e309-548c-8005-b0ff-90a6ea5e01b3",
    )
    req = WakeDeliveryRequest(
        target=target,
        continuation_id="cont_spawn_fail",
        prompt="DBRIDGE_CONTINUE cont_spawn_fail",
        delivery_key="cont_spawn_fail",
    )
    receipt_dir = tmp_path / "receipts"

    runner = FakeProcessRunner(exc=FileNotFoundError("No such file or directory: '/usr/bin/node'"))
    transport = ReviewGptWakeTransport(
        node_path="/usr/bin/node",
        cli_path="/opt/review-gpt/cli.js",
        config_path=tmp_path / "config.json",
        browser_endpoint="http://127.0.0.1:9222",
        receipt_dir=receipt_dir,
        process_runner=runner,
    )

    result = await transport.deliver(req)
    assert result.disposition == "not_submitted"
    assert "No such file or directory" in (result.detail or "")
