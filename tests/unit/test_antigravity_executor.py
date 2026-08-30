import os
import asyncio
from pathlib import Path

import pytest

from app.api.errors import BridgeError
from app.capabilities import CapabilitySet
from app.executors.antigravity import AntigravityExecutor, AsyncioProcessRunner, ProcessResult
from app.executors.models import ExecutorName, ExecutorRequest, ExecutorStatus, QuotaState, TaskKind
from app.projects.models import Repository
from app.settings import AntigravityExecutorSettings


class FakeRunner:
    def __init__(self, results=()):
        self.results = list(results)
        self.calls = []

    async def run(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return self.results.pop(0)


def result(returncode=0, stdout=b"", stderr=b"", timed_out=False):
    return ProcessResult(returncode, stdout, stderr, timed_out, False, False)


def make_executor(tmp_path, *, enabled=True, executable=None, results=(), model=None):
    path = executable or tmp_path / "agy"
    if executable is None:
        path.write_text("fake")
    runner = FakeRunner(results)
    settings = AntigravityExecutorSettings(enabled=enabled, executable=path, model=model)
    return AntigravityExecutor(settings, runner), runner


@pytest.mark.asyncio
async def test_probe_reports_missing_binary_without_auth_probe(tmp_path):
    executor, runner = make_executor(tmp_path, executable=tmp_path / "missing")
    status = await executor.probe(busy=False)
    assert status.public_dict() == {"executor": "antigravity", "available": False,
        "authenticated": False, "busy": False, "quota_state": "unknown",
        "last_error": "binary_missing"}
    assert runner.calls == []


@pytest.mark.asyncio
async def test_probe_classifies_auth_required_and_redacts_diagnostics(tmp_path):
    executor, _ = make_executor(tmp_path, results=[result(stdout=b"agy 1.2.3\n"),
        result(1, stderr=b"authentication required code=ABCD-1234 https://accounts.test/secret")])
    status = await executor.probe(busy=False)
    assert status.available and not status.authenticated
    assert status.last_error == "auth_required"
    assert "ABCD" not in str(status.public_dict()) and "https://" not in str(status.public_dict())


@pytest.mark.asyncio
async def test_probe_marks_callable_runtime_with_unknown_quota(tmp_path):
    executor, runner = make_executor(tmp_path, results=[result(stdout=b"agy 1.2.3\n"),
        result(stdout=b'{"status":"SUCCESS","response":"BRIDGE_PROBE_OK","model":"gemini"}')])
    status = await executor.probe(busy=True)
    assert status.available and status.authenticated and status.busy
    assert status.quota_state is QuotaState.UNKNOWN and status.version == "agy 1.2.3"
    assert runner.calls[1][0][1:] == ("-p", "Reply with exactly BRIDGE_PROBE_OK", "--output-format", "json", "--sandbox", "--print-timeout", "15s")
    assert set(runner.calls[1][1]["env"]) <= {"PATH", "LANG", "LC_ALL", "HOME", "SSH_CONNECTION"}


@pytest.mark.asyncio
@pytest.mark.parametrize(("probe_result", "error"), [
    (result(timed_out=True), "probe_timeout"),
    (result(1, stderr=b"resource exhausted"), "quota_exhausted"),
    (result(stdout=b'{"status":"ERROR","response":"no"}'), "runtime_probe_failed"),
])
async def test_probe_normalizes_failures(tmp_path, probe_result, error):
    executor, _ = make_executor(tmp_path, results=[result(stdout=b"agy 1"), probe_result])
    probed = await executor.probe(busy=False)
    assert probed.last_error == error
    if error == "quota_exhausted":
        assert probed.quota_state is QuotaState.EXHAUSTED


@pytest.mark.asyncio
async def test_process_runner_terminates_process_group_when_cancelled(tmp_path):
    pid_file = tmp_path / "pid"
    task = asyncio.create_task(AsyncioProcessRunner().run(
        (os.sys.executable, "-c", f"import os,time; open({str(pid_file)!r},'w').write(str(os.getpid())); time.sleep(30)"),
        cwd=tmp_path, timeout_seconds=60, output_limit_bytes=1024, env={"PATH": os.environ["PATH"]}))
    for _ in range(100):
        if pid_file.exists(): break
        await asyncio.sleep(.01)
    pid = int(pid_file.read_text())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def callable_status(**changes):
    values = dict(executor=ExecutorName.ANTIGRAVITY, available=True, authenticated=True,
        busy=False, model=None, quota_state=QuotaState.UNKNOWN, remaining_fraction=None,
        reset_time=None, last_error=None, last_success_at=None, version="agy 1")
    values.update(changes)
    return ExecutorStatus(**values)


def test_launch_builds_documented_headless_argv_and_bounded_prompt(tmp_path):
    executor, _ = make_executor(tmp_path, model="gemini-3.1-pro")
    repository = Repository("project", "repo", tmp_path, CapabilitySet.from_mapping({"execute": True}))
    request = ExecutorRequest("make change", TaskKind.IMPLEMENTATION, ExecutorName.ANTIGRAVITY, 901, 262144, None)
    launch = executor.launch(repository, request, callable_status())
    assert launch.arguments[0] == "-p"
    assert launch.arguments[-4:] == ("--print-timeout", "900s", "--model", "gemini-3.1-pro")
    assert "--cwd" not in launch.arguments
    assert "AGENTS.md" in launch.arguments[1] and "Do not push or deploy" in launch.arguments[1]
    assert launch.stdin is None and launch.environment_keys == ("HOME", "SSH_CONNECTION")


def test_review_launch_does_not_force_test_suite(tmp_path):
    executor, _ = make_executor(tmp_path)
    repository = Repository("p", "r", tmp_path, CapabilitySet.from_mapping({"execute": True}))
    request = ExecutorRequest("inspect only", TaskKind.REVIEW, ExecutorName.ANTIGRAVITY, 60, 4096, None)
    launch = executor.launch(repository, request, callable_status())
    prompt = launch.arguments[1]
    assert "Do not run test suites unless the task explicitly asks." in prompt
    assert "pytest -q" not in prompt


@pytest.mark.parametrize(("changes", "reason"), [
    ({"available": False}, "unavailable"), ({"authenticated": False}, "auth_required"),
    ({"busy": True}, "busy"), ({"quota_state": QuotaState.EXHAUSTED}, "quota_exhausted"),
])
def test_launch_rejects_hard_gates(tmp_path, changes, reason):
    executor, _ = make_executor(tmp_path)
    repository = Repository("p", "r", tmp_path, CapabilitySet.from_mapping({"execute": True}))
    request = ExecutorRequest("task", TaskKind.REVIEW, ExecutorName.ANTIGRAVITY, 20, 1024, None)
    with pytest.raises(BridgeError) as caught:
        executor.launch(repository, request, callable_status(**changes))
    assert caught.value.details["reason"] == reason


@pytest.mark.parametrize("task", ["", "x" * 65537])
def test_launch_rejects_invalid_task_size(tmp_path, task):
    executor, _ = make_executor(tmp_path)
    repository = Repository("p", "r", tmp_path, CapabilitySet.from_mapping({"execute": True}))
    with pytest.raises(BridgeError):
        executor.launch(repository, ExecutorRequest(task, TaskKind.OTHER, None, 20, 1024, None), callable_status())
