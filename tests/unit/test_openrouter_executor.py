from pathlib import Path
import pytest
from pydantic import SecretStr

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import CapabilitySet
from app.executors.models import (
    ExecutorLaunch,
    ExecutorName,
    ExecutorRequest,
    ExecutorStatus,
    QuotaState,
    TaskKind,
)
from app.executors.openrouter import OpenRouterExecutor
from app.projects.models import Repository
from app.settings import OpenRouterExecutorSettings


@pytest.fixture
def repository(tmp_path):
    return Repository("p", "r", tmp_path, CapabilitySet.from_mapping({"execute": True}))


def test_openrouter_probe_disabled():
    settings = OpenRouterExecutorSettings(enabled=False, api_key=SecretStr("sk-test"))
    executor = OpenRouterExecutor(settings)
    status = executor.probe(busy=False)
    assert status.executor is ExecutorName.OPENROUTER
    assert status.available is False
    assert status.authenticated is False
    assert status.last_error == "disabled"
    assert status.busy is False


def test_openrouter_probe_missing_key():
    settings = OpenRouterExecutorSettings(enabled=True, api_key=None)
    executor = OpenRouterExecutor(settings)
    status = executor.probe(busy=False)
    assert status.available is False
    assert status.authenticated is False
    assert status.last_error == "missing_key"


def test_openrouter_probe_ready():
    settings = OpenRouterExecutorSettings(enabled=True, api_key=SecretStr("sk-test"))
    executor = OpenRouterExecutor(settings)
    status = executor.probe(busy=True)
    assert status.available is True
    assert status.authenticated is True
    assert status.last_error is None
    assert status.busy is True
    assert status.quota_state is QuotaState.UNKNOWN
    assert status.model == "deepseek/deepseek-v4-flash-0731"


def test_openrouter_launch_default_model_and_env(repository):
    settings = OpenRouterExecutorSettings(
        enabled=True, api_key=SecretStr("sk-test"), max_turns=75
    )
    executor = OpenRouterExecutor(settings)
    status = executor.probe(busy=False)
    request = ExecutorRequest("implement feature X", TaskKind.IMPLEMENTATION, ExecutorName.OPENROUTER, 300, 262144, None)
    launch = executor.launch(repository, request, status)

    assert launch.executor is ExecutorName.OPENROUTER
    assert launch.model == "deepseek/deepseek-v4-flash-0731"
    assert launch.quota_state is QuotaState.UNKNOWN
    assert "OPENROUTER_API_KEY" in launch.environment_keys
    assert "--model" in launch.arguments
    model_idx = launch.arguments.index("--model")
    assert launch.arguments[model_idx + 1] == "deepseek/deepseek-v4-flash-0731"
    max_turns_idx = launch.arguments.index("--max-turns")
    assert launch.arguments[max_turns_idx + 1] == "75"
    assert "Task:\nimplement feature X" in launch.stdin


def test_openrouter_launch_custom_allowlisted_model(repository):
    settings = OpenRouterExecutorSettings(enabled=True, api_key=SecretStr("sk-test"))
    executor = OpenRouterExecutor(settings)
    status = executor.probe(busy=False)
    request = ExecutorRequest(
        "implement feature X",
        TaskKind.IMPLEMENTATION,
        ExecutorName.OPENROUTER,
        300,
        262144,
        None,
        model="qwen/qwen3-coder-next",
    )
    launch = executor.launch(repository, request, status)
    assert launch.model == "qwen/qwen3-coder-next"
    model_idx = launch.arguments.index("--model")
    assert launch.arguments[model_idx + 1] == "qwen/qwen3-coder-next"


def test_openrouter_launch_rejects_non_allowlisted_model(repository):
    settings = OpenRouterExecutorSettings(enabled=True, api_key=SecretStr("sk-test"))
    executor = OpenRouterExecutor(settings)
    status = executor.probe(busy=False)
    request = ExecutorRequest(
        "task",
        TaskKind.IMPLEMENTATION,
        ExecutorName.OPENROUTER,
        300,
        262144,
        None,
        model="untrusted/model",
    )
    with pytest.raises(BridgeError) as exc_info:
        executor.launch(repository, request, status)
    assert exc_info.value.code == ErrorCode.POLICY_VIOLATION
    assert exc_info.value.details.get("reason") == "model_not_allowlisted"


def test_openrouter_launch_rejects_when_disabled(repository):
    settings = OpenRouterExecutorSettings(enabled=False, api_key=SecretStr("sk-test"))
    executor = OpenRouterExecutor(settings)
    status = executor.probe(busy=False)
    request = ExecutorRequest("task", TaskKind.IMPLEMENTATION, ExecutorName.OPENROUTER, 300, 262144, None)
    with pytest.raises(BridgeError) as exc_info:
        executor.launch(repository, request, status)
    assert exc_info.value.code == ErrorCode.POLICY_VIOLATION
    assert exc_info.value.details.get("reason") == "disabled"


def test_openrouter_launch_rejects_when_missing_key(repository):
    settings = OpenRouterExecutorSettings(enabled=True, api_key=None)
    executor = OpenRouterExecutor(settings)
    status = executor.probe(busy=False)
    request = ExecutorRequest("task", TaskKind.IMPLEMENTATION, ExecutorName.OPENROUTER, 300, 262144, None)
    with pytest.raises(BridgeError) as exc_info:
        executor.launch(repository, request, status)
    assert exc_info.value.code == ErrorCode.POLICY_VIOLATION
    assert exc_info.value.details.get("reason") == "missing_key"


@pytest.mark.parametrize("task", ["", "x" * 65537])
def test_openrouter_launch_rejects_invalid_task_size(repository, task):
    settings = OpenRouterExecutorSettings(enabled=True, api_key=SecretStr("sk-test"))
    executor = OpenRouterExecutor(settings)
    status = executor.probe(busy=False)
    with pytest.raises(BridgeError) as exc_info:
        executor.launch(repository, ExecutorRequest(task, TaskKind.OTHER, ExecutorName.OPENROUTER, 20, 1024, None), status)
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT
