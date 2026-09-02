from pathlib import Path
import pytest

from app.api.errors import BridgeError
from app.capabilities import CapabilitySet
from app.executors.codex import CodexExecutor
from app.executors.models import ExecutorName, ExecutorRequest, ExecutorStatus, QuotaState, TaskKind
from app.projects.models import Repository


def codex_status():
    return ExecutorStatus(
        ExecutorName.CODEX, True, True, False, None, QuotaState.UNKNOWN,
        None, None, None, None, None
    )


def test_codex_launch_builds_expected_argv_and_invariants(tmp_path):
    executor = CodexExecutor()
    repo = Repository("p", "r", tmp_path, CapabilitySet.from_mapping({"execute": True}))
    req = ExecutorRequest("implement feature X", TaskKind.IMPLEMENTATION, ExecutorName.CODEX, 300, 262144, None)
    launch = executor.launch(repo, req, codex_status())

    assert launch.executable == "codex"
    assert launch.arguments == ("exec", "--sandbox", "workspace-write", "-")
    assert launch.executor is ExecutorName.CODEX
    assert launch.quota_state is QuotaState.UNKNOWN
    assert launch.model is None
    assert launch.environment_keys == ("HOME", "SSH_CONNECTION")
    assert "You are executing one bounded Development Bridge repository task." in launch.stdin
    assert "Task:\nimplement feature X" in launch.stdin
    assert "Verification:\n- Run targeted tests for changed behavior." in launch.stdin
    assert "- Work only inside the current repository." in launch.stdin
    assert "- Do not push or deploy." in launch.stdin


def test_codex_launch_review_task_kind(tmp_path):
    executor = CodexExecutor()
    repo = Repository("p", "r", tmp_path, CapabilitySet.from_mapping({"execute": True}))
    req = ExecutorRequest("review changes", TaskKind.REVIEW, ExecutorName.CODEX, 300, 262144, None)
    launch = executor.launch(repo, req, codex_status())

    assert "Verification:\n- Do not run test suites unless the task explicitly asks." in launch.stdin


def test_codex_launch_custom_executable(tmp_path):
    executor = CodexExecutor("/custom/path/to/codex")
    repo = Repository("p", "r", tmp_path, CapabilitySet.from_mapping({"execute": True}))
    req = ExecutorRequest("task", TaskKind.OTHER, ExecutorName.CODEX, 300, 262144, None)
    launch = executor.launch(repo, req, codex_status())
    assert launch.executable == "/custom/path/to/codex"


@pytest.mark.parametrize("task", ["", "x" * 65537])
def test_codex_launch_rejects_invalid_task_size(tmp_path, task):
    executor = CodexExecutor()
    repo = Repository("p", "r", tmp_path, CapabilitySet.from_mapping({"execute": True}))
    with pytest.raises(BridgeError):
        executor.launch(repo, ExecutorRequest(task, TaskKind.OTHER, None, 20, 1024, None), codex_status())
