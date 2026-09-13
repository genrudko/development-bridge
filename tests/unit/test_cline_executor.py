import json
from pathlib import Path

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import CapabilitySet
from app.executors.antigravity import ProcessResult
from app.executors.cline import ClineExecutor
from app.executors.models import (
    ExecutorName,
    ExecutorRequest,
    ExecutorStatus,
    QuotaState,
    TaskKind,
)
from app.projects.models import Repository
from app.settings import ClineExecutorSettings


def write_auth(config_dir: Path, provider: str = "cline-pass") -> None:
    path = config_dir / "data" / "settings" / "providers.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"providers": {provider: {"tokenSource": "local"}}}), encoding="utf-8")


class FakeRunner:
    def __init__(self, *, returncode=0, stdout=b"3.0.61\n", stderr=b"", timed_out=False):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out
        self.calls: list[tuple[str, ...]] = []

    async def run(self, argv, *, cwd, timeout_seconds, output_limit_bytes, env):
        self.calls.append(tuple(argv))
        return ProcessResult(
            self.returncode, self.stdout, self.stderr, self.timed_out, False, False
        )


@pytest.fixture
def repository(tmp_path):
    return Repository("p", "r", tmp_path, CapabilitySet.from_mapping({"execute": True}))


def settings_for(tmp_path, *, enabled=True, executable=None, model=None):
    cline = tmp_path / "cline"
    cline.write_text("#!/bin/sh\necho 3.0.61\n", encoding="utf-8")
    cline.chmod(0o755)
    values = {
        "enabled": enabled,
        "executable": cline if executable is None else executable,
        "config_directory": tmp_path / "cline-config",
    }
    if model is not None:
        values["model"] = model
    return ClineExecutorSettings(**values)


def ready_status():
    return ExecutorStatus(
        ExecutorName.CLINE, True, True, False, "cline-pass/deepseek-v4-flash",
        QuotaState.UNKNOWN, None, None, None, None, "3.0.61",
    )


def blocked_status(last_error, available=True):
    return ExecutorStatus(
        ExecutorName.CLINE, available, False, False, "cline-pass/deepseek-v4-flash",
        QuotaState.UNKNOWN, None, None, last_error, None, "3.0.61",
    )


def request(task="task", *, model=None, task_kind=TaskKind.IMPLEMENTATION):
    return ExecutorRequest(
        task, task_kind, ExecutorName.CLINE, 300, 262144, None, model=model
    )


@pytest.mark.asyncio
async def test_cline_probe_disabled(tmp_path):
    executor = ClineExecutor(settings_for(tmp_path, enabled=False), FakeRunner())
    status = await executor.probe(busy=False)
    assert status.executor is ExecutorName.CLINE
    assert status.available is False
    assert status.authenticated is False
    assert status.last_error == "disabled"
    assert status.busy is False


@pytest.mark.asyncio
async def test_cline_probe_binary_missing(tmp_path):
    executor = ClineExecutor(
        settings_for(tmp_path, executable=tmp_path / "absent-cline"), FakeRunner()
    )
    status = await executor.probe(busy=False)
    assert status.available is False
    assert status.authenticated is False
    assert status.last_error == "binary_missing"


@pytest.mark.asyncio
async def test_cline_probe_auth_required_without_local_evidence(tmp_path):
    executor = ClineExecutor(settings_for(tmp_path), FakeRunner())
    status = await executor.probe(busy=False)
    assert status.available is True
    assert status.authenticated is False
    assert status.last_error == "auth_required"
    assert status.version == "3.0.61"
    assert status.model == "cline-pass/deepseek-v4-flash"


@pytest.mark.asyncio
async def test_cline_probe_ready_with_local_auth_evidence(tmp_path):
    settings = settings_for(tmp_path)
    write_auth(settings.config_directory)
    status = await ClineExecutor(settings, FakeRunner()).probe(busy=True)
    assert status.available is True
    assert status.authenticated is True
    assert status.last_error is None
    assert status.busy is True
    assert status.quota_state is QuotaState.UNKNOWN
    assert status.version == "3.0.61"
    assert status.model == "cline-pass/deepseek-v4-flash"


@pytest.mark.asyncio
async def test_cline_probe_rejects_auth_for_different_configured_provider(tmp_path):
    settings = settings_for(tmp_path).model_copy(update={"provider": "enterprise-pass"})
    write_auth(settings.config_directory, "cline-pass")
    status = await ClineExecutor(settings, FakeRunner()).probe(busy=False)
    assert status.available is True
    assert status.authenticated is False
    assert status.last_error == "auth_required"


@pytest.mark.asyncio
async def test_cline_probe_only_runs_version_and_fails_closed_on_error(tmp_path):
    settings = settings_for(tmp_path)
    write_auth(settings.config_directory)
    runner = FakeRunner()
    await ClineExecutor(settings, runner).probe(busy=False)
    assert len(runner.calls) == 1
    assert runner.calls[0][-1] == "--version"

    failing = ClineExecutor(settings, FakeRunner(returncode=1, stdout=b""))
    status = await failing.probe(busy=False)
    assert status.available is False
    assert status.authenticated is False
    assert status.last_error == "probe_failed"


def test_cline_launch_rejects_when_disabled(repository, tmp_path):
    executor = ClineExecutor(settings_for(tmp_path, enabled=False), FakeRunner())
    with pytest.raises(BridgeError) as exc_info:
        executor.launch(repository, request(), blocked_status("disabled", available=False))
    assert exc_info.value.code == ErrorCode.POLICY_VIOLATION
    assert exc_info.value.details.get("reason") == "disabled"


def test_cline_launch_rejects_when_auth_required(repository, tmp_path):
    executor = ClineExecutor(settings_for(tmp_path), FakeRunner())
    with pytest.raises(BridgeError) as exc_info:
        executor.launch(repository, request(), blocked_status("auth_required"))
    assert exc_info.value.code == ErrorCode.POLICY_VIOLATION
    assert exc_info.value.details.get("reason") == "auth_required"


def test_cline_launch_uses_worker_adapter_and_default_model(repository, tmp_path):
    settings = settings_for(tmp_path)
    executor = ClineExecutor(settings, FakeRunner())
    launch = executor.launch(repository, request("implement feature X"), ready_status())
    assert launch.executor is ExecutorName.CLINE
    assert launch.model == "cline-pass/deepseek-v4-flash"
    assert launch.quota_state is QuotaState.UNKNOWN
    assert launch.stdin is not None and "Task:\nimplement feature X" in launch.stdin
    assert launch.environment_keys == ("HOME", "SSH_CONNECTION")
    assert Path(launch.executable).name.startswith("python")
    assert launch.arguments[0].endswith("cline_worker.py")
    model_idx = launch.arguments.index("--model")
    assert launch.arguments[model_idx + 1] == "cline-pass/deepseek-v4-flash"
    provider_idx = launch.arguments.index("--provider")
    assert launch.arguments[provider_idx + 1] == "cline-pass"
    executable_idx = launch.arguments.index("--executable")
    assert launch.arguments[executable_idx + 1] == str(settings.executable)
    assert "--json" not in launch.arguments


def test_cline_launch_honors_explicit_model_override(repository, tmp_path):
    executor = ClineExecutor(settings_for(tmp_path), FakeRunner())
    launch = executor.launch(
        repository, request(model="anthropic/claude-sonnet-4"), ready_status()
    )
    assert launch.model == "anthropic/claude-sonnet-4"
    model_idx = launch.arguments.index("--model")
    assert launch.arguments[model_idx + 1] == "anthropic/claude-sonnet-4"


def test_cline_launch_rejects_malformed_model(repository, tmp_path):
    executor = ClineExecutor(settings_for(tmp_path), FakeRunner())
    with pytest.raises(BridgeError) as exc_info:
        executor.launch(repository, request(model="bad slug"), ready_status())
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT
    assert exc_info.value.details.get("reason") == "invalid_model_slug"


@pytest.mark.parametrize("task", ["", "x" * 65537])
def test_cline_launch_rejects_invalid_task_size(repository, tmp_path, task):
    executor = ClineExecutor(settings_for(tmp_path), FakeRunner())
    with pytest.raises(BridgeError) as exc_info:
        executor.launch(repository, request(task, task_kind=TaskKind.OTHER), ready_status())
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT
