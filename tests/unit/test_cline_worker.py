import io
import json
import subprocess

from app.executors.cline_worker import ClineWorker, emit, parse_jsonl_events

SUCCESS_LINE = (
    '{"type":"run_start","sessionId":"sess_123","providerId":"cline-pass",'
    '"modelId":"cline-pass/deepseek-v4-flash"}'
)
RESULT_LINE = (
    '{"type":"run_result","finishReason":"completed","iterations":2,'
    '"usage":{"inputTokens":3,"outputTokens":4,"totalTokens":7},'
    '"durationMs":1234,"text":"worker finished","model":"cline-pass/deepseek-v4-flash"}'
)


def completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(["cline"], returncode, stdout=stdout, stderr=stderr)


class FakeRunner:
    def __init__(self, result):
        self.result = result
        self.commands: list[list[str]] = []
        self.kwargs: list[dict] = []

    def __call__(self, command, **kwargs):
        self.commands.append(list(command))
        self.kwargs.append(kwargs)
        return self.result


def worker(**overrides):
    values = {
        "executable": "cline",
        "provider": "cline-pass",
        "model": "cline-pass/deepseek-v4-flash",
        "task": "do the thing",
    }
    values.update(overrides)
    return ClineWorker(**values)


def test_parse_jsonl_events_extracts_terminal_evidence():
    evidence = parse_jsonl_events(f"{SUCCESS_LINE}\n{RESULT_LINE}\n")
    assert evidence.session_id == "sess_123"
    assert evidence.finish_reason == "completed"
    assert evidence.response == "worker finished"
    assert evidence.model == "cline-pass/deepseek-v4-flash"
    assert evidence.iterations == 2
    assert evidence.duration_ms == 1234.0
    assert evidence.usage == {"inputTokens": 3, "outputTokens": 4, "totalTokens": 7}
    assert evidence.malformed_events == 0


def test_parse_jsonl_events_tolerates_noise_and_garbage():
    evidence = parse_jsonl_events(f"not json\n\n{SUCCESS_LINE}\n[1,2]\n{RESULT_LINE}")
    assert evidence.malformed_events == 2
    assert evidence.finish_reason == "completed"


def test_worker_success_returns_single_normalized_result():
    runner = FakeRunner(completed(f"{SUCCESS_LINE}\n{RESULT_LINE}\n"))
    result = worker(config_directory="/tmp/cline-config", runner=runner).run()
    assert result["status"] == "SUCCESS"
    assert result["response"] == "worker finished"
    assert result["session_id"] == "sess_123"
    assert result["model"] == "cline-pass/deepseek-v4-flash"
    assert result["finish_reason"] == "completed"
    assert result["iterations"] == 2
    assert result["usage"] == {"inputTokens": 3, "outputTokens": 4, "totalTokens": 7}
    command = runner.commands[0]
    assert command[0] == "cline"
    assert "--json" in command
    assert command[command.index("--provider") + 1] == "cline-pass"
    assert command[command.index("--model") + 1] == "cline-pass/deepseek-v4-flash"
    assert command[command.index("--config") + 1] == "/tmp/cline-config"
    assert command[-1] == "do the thing"
    assert "-t" not in command and "--timeout" not in command


def test_worker_reports_missing_run_result_as_error():
    result = worker(runner=FakeRunner(completed(f"{SUCCESS_LINE}\n"))).run()
    assert result["status"] == "ERROR"
    assert result["reason"] == "run_result_missing"
    assert "exit_code=0" in result["diagnostic"]


def test_worker_reports_non_completed_finish_reason_as_error():
    line = RESULT_LINE.replace('"finishReason":"completed"', '"finishReason":"max_iterations"')
    result = worker(runner=FakeRunner(completed(line))).run()
    assert result["status"] == "ERROR"
    assert result["reason"] == "finish_reason_max_iterations"


def test_worker_rejects_completed_result_when_cli_exit_is_nonzero():
    result = worker(
        runner=FakeRunner(completed(RESULT_LINE, stderr="cline failed", returncode=2))
    ).run()
    assert result["status"] == "ERROR"
    assert result["reason"] == "nonzero_exit"
    assert "exit_code=2" in result["diagnostic"]


def test_worker_reports_aborted_run_as_error():
    aborted = '{"type":"run_aborted","reason":"external_abort"}'
    result = worker(runner=FakeRunner(completed(aborted))).run()
    assert result["status"] == "ERROR"
    assert result["reason"] == "run_aborted"
    assert "external_abort" in result["error"]


def test_worker_reports_unstartable_executable():
    def runner(command, **kwargs):
        raise OSError("no such file")

    result = worker(runner=runner).run()
    assert result["status"] == "ERROR"
    assert result["reason"] == "executable_unavailable"


def test_worker_scrubs_secret_material_from_diagnostics():
    stdout = '{"type":"run_start","sessionId":"s","apiKey":"sk-live-abcdef123456"}\n'
    stderr = "auth failed token=supersecretvalue\n"
    result = worker(runner=FakeRunner(completed(stdout, stderr, returncode=2))).run()
    assert result["status"] == "ERROR"
    blob = json.dumps(result)
    assert "sk-live-abcdef123456" not in blob
    assert "supersecretvalue" not in blob
    assert "exit_code=2" in result["diagnostic"]


def test_worker_bounds_large_responses():
    big = json.dumps({"type": "run_result", "finishReason": "completed", "text": "x" * 200_000})
    result = worker(runner=FakeRunner(completed(big))).run()
    assert result["status"] == "SUCCESS"
    assert len(result["response"]) <= 32768


def test_emit_writes_exactly_one_json_object(capsys):
    code = emit({"status": "SUCCESS", "response": "ok"})
    assert code == 0
    captured = capsys.readouterr()
    assert captured.out.count("\n") == 1
    assert json.loads(captured.out) == {"status": "SUCCESS", "response": "ok"}


def test_emit_returns_nonzero_for_errors(capsys):
    code = emit({"status": "ERROR", "reason": "run_result_missing"})
    assert code == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "run_result_missing"


def test_worker_missing_task_is_reported_by_main(monkeypatch, capsys):
    from app.executors import cline_worker

    monkeypatch.setattr(cline_worker.sys, "stdin", io.StringIO(""))
    monkeypatch.setattr(
        cline_worker.sys,
        "argv",
        ["cline_worker.py", "--executable", "cline", "--provider", "cline-pass", "--model", "m/n"],
    )
    code = cline_worker.main()
    assert code == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "missing_task"


def test_worker_parser_defaults_to_clinepass_without_payg_fallback():
    from app.executors import cline_worker

    arguments = cline_worker._parser().parse_args(["--model", "m/n"])
    assert arguments.provider == "cline-pass"
    assert arguments.model == "m/n"
    assert arguments.executable == "cline"
