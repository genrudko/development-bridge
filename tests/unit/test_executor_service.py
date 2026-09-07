from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import CapabilitySet
from app.executors.models import ExecutorLaunch, ExecutorName, ExecutorRequest, ExecutorStatus, QuotaState, TaskKind
from app.executors.selector import ExecutorSelector
from app.executors.service import ExecutorService
from app.projects.models import Repository


def request(executor=ExecutorName.ANTIGRAVITY):
    return ExecutorRequest("task", TaskKind.REVIEW, executor, 100, 2048, "same")


def status(quota=QuotaState.UNKNOWN, busy=False):
    return ExecutorStatus(ExecutorName.ANTIGRAVITY, True, True, busy, "gemini", quota,
        None, None, None, None, "agy 1")


class Jobs:
    def __init__(self, busy=False): self.busy, self.calls = busy, []
    def repository_busy(self, repository): return self.busy
    def execution_by_idempotency(self, repository, key): return None
    async def start_execution(self, *args, **kwargs):
        self.calls.append((args, kwargs)); return SimpleNamespace(job_id="job_1")


class Antigravity:
    def __init__(self, value): self.value, self.probes = value, []
    async def probe(self, *, busy): self.probes.append(busy); return self.value
    def launch(self, repository, request, status):
        return ExecutorLaunch("agy", ("-p", "prompt"), None, ("HOME",),
            ExecutorName.ANTIGRAVITY, "gemini", status.quota_state)


@pytest.fixture
def repository(tmp_path):
    return Repository("p", "r", tmp_path, CapabilitySet.from_mapping({"execute": True}))


@pytest.mark.asyncio
async def test_status_uses_repository_busy_and_returns_three_executors(repository):
    jobs, antigravity = Jobs(True), Antigravity(status())
    result = await ExecutorService(jobs, antigravity, ExecutorSelector()).status(repository)
    assert antigravity.probes == [True]
    assert [item["executor"] for item in result["executors"]] == ["codex", "antigravity", "openrouter"]


@pytest.mark.asyncio
async def test_explicit_antigravity_submits_one_durable_execution(repository):
    jobs, antigravity = Jobs(), Antigravity(status())
    job = await ExecutorService(jobs, antigravity, ExecutorSelector()).start(repository, request(), "req")
    assert job.job_id == "job_1" and len(jobs.calls) == 1
    assert jobs.calls[0][1]["executor"] == "antigravity"
    assert jobs.calls[0][1]["executor_quota_state"] == "unknown"


@pytest.mark.asyncio
async def test_explicit_codex_submits_durable_execution(repository):
    jobs, antigravity = Jobs(), Antigravity(status())
    job = await ExecutorService(jobs, antigravity, ExecutorSelector()).start(repository, request(ExecutorName.CODEX), "req")
    assert job.job_id == "job_1" and len(jobs.calls) == 1
    args, kwargs = jobs.calls[0]
    assert args[1] == "codex"
    assert args[2] == ("exec", "--sandbox", "workspace-write", "-")
    assert "You are executing one bounded Development Bridge repository task." in kwargs["stdin"]
    assert "Task:\ntask" in kwargs["stdin"]
    assert kwargs["executor"] == "codex"
    assert kwargs["executor_quota_state"] == "unknown"
    assert kwargs["executor_model"] is None
    assert kwargs["environment_keys"] == ("HOME", "SSH_CONNECTION")
    assert kwargs["require_repository_idle"] is False


@pytest.mark.asyncio
async def test_automatic_selection_codex_submits_durable_execution(repository):
    jobs, antigravity = Jobs(), Antigravity(status(quota=QuotaState.UNKNOWN))
    job = await ExecutorService(jobs, antigravity, ExecutorSelector()).start(repository, request(None), "req")
    assert job.job_id == "job_1" and len(jobs.calls) == 1
    args, kwargs = jobs.calls[0]
    assert args[1] == "codex"
    assert args[2] == ("exec", "--sandbox", "workspace-write", "-")
    assert kwargs["executor"] == "codex"
    assert kwargs["executor_quota_state"] == "unknown"


@pytest.mark.asyncio
async def test_busy_explicit_antigravity_submits_queueable_job(repository):
    jobs = Jobs(busy=True)
    antigravity = Antigravity(status(busy=True))
    job = await ExecutorService(jobs, antigravity, ExecutorSelector()).start(repository, request(), "req")
    assert job.job_id == "job_1"
    assert len(jobs.calls) == 1
    assert jobs.calls[0][1]["executor"] == "antigravity"
    assert jobs.calls[0][1]["require_repository_idle"] is False


@pytest.mark.asyncio
async def test_exhausted_antigravity_still_creates_no_job(repository):
    jobs = Jobs()
    with pytest.raises(BridgeError):
        await ExecutorService(
            jobs, Antigravity(status(QuotaState.EXHAUSTED)), ExecutorSelector()
        ).start(repository, request(), "req")
    assert jobs.calls == []


@pytest.mark.asyncio
async def test_busy_explicit_codex_submits_queueable_job(repository):
    jobs = Jobs(busy=True)
    antigravity = Antigravity(status(busy=True, quota=QuotaState.OK))
    job = await ExecutorService(jobs, antigravity, ExecutorSelector()).start(
        repository, request(ExecutorName.CODEX), "req"
    )
    assert job.job_id == "job_1"
    assert jobs.calls[0][1]["executor"] == "codex"
    assert jobs.calls[0][1]["require_repository_idle"] is False


@pytest.mark.asyncio
async def test_busy_automatic_selection_keeps_antigravity_when_quota_ok(repository):
    jobs = Jobs(busy=True)
    antigravity = Antigravity(status(busy=True, quota=QuotaState.OK))
    job = await ExecutorService(jobs, antigravity, ExecutorSelector()).start(
        repository, request(None), "req"
    )
    assert job.job_id == "job_1"
    assert jobs.calls[0][1]["executor"] == "antigravity"
    assert jobs.calls[0][1]["require_repository_idle"] is False


class FakeOpenRouter:
    def __init__(self, available=True, authenticated=True, last_error=None):
        self.available = available
        self.authenticated = authenticated
        self.last_error = last_error
        self.probes = []
        self.launch_roots = []

    def probe(self, *, busy):
        self.probes.append(busy)
        return ExecutorStatus(
            ExecutorName.OPENROUTER,
            self.available,
            self.authenticated,
            busy,
            "deepseek/deepseek-v4-flash-0731",
            QuotaState.UNKNOWN,
            None,
            None,
            self.last_error,
            None,
            None,
        )

    def launch(self, repository, request, status):
        self.launch_roots.append(repository.root)
        if not status.available or not status.authenticated:
            raise BridgeError(ErrorCode.POLICY_VIOLATION, "blocked", details={"reason": status.last_error})
        model = request.model or "deepseek/deepseek-v4-flash-0731"
        if model not in {"deepseek/deepseek-v4-flash-0731", "qwen/qwen3-coder-next"}:
            raise BridgeError(ErrorCode.POLICY_VIOLATION, "model not allowlisted", details={"reason": "model_not_allowlisted"})
        return ExecutorLaunch(
            "python3",
            ("worker.py", "--model", model),
            "prompt",
            ("HOME", "OPENROUTER_API_KEY"),
            ExecutorName.OPENROUTER,
            model,
            QuotaState.UNKNOWN,
        )


@pytest.mark.asyncio
async def test_explicit_openrouter_submits_durable_execution_and_persists_model(repository):
    jobs = Jobs()
    antigravity = Antigravity(status())
    openrouter = FakeOpenRouter()
    req = ExecutorRequest(
        "task",
        TaskKind.IMPLEMENTATION,
        ExecutorName.OPENROUTER,
        100,
        2048,
        "same",
        model="qwen/qwen3-coder-next",
    )
    job = await ExecutorService(jobs, antigravity, ExecutorSelector(), openrouter=openrouter).start(
        repository, req, "req_1"
    )
    assert job.job_id == "job_1"
    assert len(jobs.calls) == 1
    kwargs = jobs.calls[0][1]
    assert kwargs["executor"] == "openrouter"
    assert kwargs["executor_model"] == "qwen/qwen3-coder-next"
    assert kwargs["require_repository_idle"] is False
    assert openrouter.launch_roots == [repository.root]


@pytest.mark.asyncio
async def test_busy_explicit_openrouter_submits_queueable_job(repository):
    jobs = Jobs(busy=True)
    antigravity = Antigravity(status(busy=True))
    openrouter = FakeOpenRouter()
    req = ExecutorRequest(
        "task", TaskKind.IMPLEMENTATION, ExecutorName.OPENROUTER, 100, 2048, "same"
    )
    job = await ExecutorService(jobs, antigravity, ExecutorSelector(), openrouter=openrouter).start(
        repository, req, "req_1"
    )
    assert job.job_id == "job_1"
    assert jobs.calls[0][1]["executor"] == "openrouter"
    assert jobs.calls[0][1]["require_repository_idle"] is False


@pytest.mark.asyncio
async def test_model_on_non_openrouter_rejected(repository):
    jobs = Jobs()
    antigravity = Antigravity(status())
    openrouter = FakeOpenRouter()
    req = ExecutorRequest(
        "task",
        TaskKind.IMPLEMENTATION,
        ExecutorName.CODEX,
        100,
        2048,
        "same",
        model="qwen/qwen3-coder-next",
    )
    with pytest.raises(BridgeError) as exc_info:
        await ExecutorService(jobs, antigravity, ExecutorSelector(), openrouter=openrouter).start(
            repository, req, "req_1"
        )
    assert exc_info.value.code == ErrorCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_model_not_allowlisted_fails_closed_before_job_creation(repository):
    jobs = Jobs()
    antigravity = Antigravity(status())
    openrouter = FakeOpenRouter()
    req = ExecutorRequest(
        "task",
        TaskKind.IMPLEMENTATION,
        ExecutorName.OPENROUTER,
        100,
        2048,
        "same",
        model="forbidden/model",
    )
    with pytest.raises(BridgeError) as exc_info:
        await ExecutorService(jobs, antigravity, ExecutorSelector(), openrouter=openrouter).start(
            repository, req, "req_1"
        )
    assert exc_info.value.code == ErrorCode.POLICY_VIOLATION
    assert exc_info.value.details.get("reason") == "model_not_allowlisted"
    assert jobs.calls == []


@pytest.mark.asyncio
async def test_automatic_selection_unchanged(repository):
    jobs = Jobs()
    antigravity = Antigravity(status(quota=QuotaState.UNKNOWN))
    openrouter = FakeOpenRouter()
    req = ExecutorRequest("task", TaskKind.IMPLEMENTATION, None, 100, 2048, "same")
    job = await ExecutorService(jobs, antigravity, ExecutorSelector(), openrouter=openrouter).start(
        repository, req, "req_1"
    )
    assert job.job_id == "job_1"
    # Even with openrouter present, automatic selection picks codex (or antigravity when suitable), never openrouter!
    assert jobs.calls[0][1]["executor"] in {"codex", "antigravity"}
    assert jobs.calls[0][1]["executor"] != "openrouter"


@pytest.mark.asyncio
async def test_openrouter_worktree_selector_launches_from_selected_root_but_queues_canonical_repo(repository, monkeypatch):
    jobs = Jobs()
    antigravity = Antigravity(status())
    openrouter = FakeOpenRouter()
    linked = repository.root / "linked"
    linked.mkdir()

    async def resolve(repo, branch):
        assert repo is repository
        assert branch == "feature/linked"
        return linked

    monkeypatch.setattr("app.executors.service.resolve_repository_worktree", resolve)
    req = ExecutorRequest(
        "task", TaskKind.IMPLEMENTATION, ExecutorName.OPENROUTER, 100, 2048, "same",
        worktree_branch="feature/linked",
    )
    await ExecutorService(jobs, antigravity, ExecutorSelector(), openrouter=openrouter).start(
        repository, req, "req_1"
    )
    assert openrouter.launch_roots == [linked]
    args, kwargs = jobs.calls[0]
    assert args[0] is repository
    assert kwargs["execution_root"] == linked
    assert kwargs["worktree_branch"] == "feature/linked"
