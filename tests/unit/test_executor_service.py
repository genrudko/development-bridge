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
async def test_status_uses_repository_busy_and_returns_both_executors(repository):
    jobs, antigravity = Jobs(True), Antigravity(status())
    result = await ExecutorService(jobs, antigravity, ExecutorSelector()).status(repository)
    assert antigravity.probes == [True]
    assert [item["executor"] for item in result["executors"]] == ["codex", "antigravity"]


@pytest.mark.asyncio
async def test_explicit_antigravity_submits_one_durable_execution(repository):
    jobs, antigravity = Jobs(), Antigravity(status())
    job = await ExecutorService(jobs, antigravity, ExecutorSelector()).start(repository, request(), "req")
    assert job.job_id == "job_1" and len(jobs.calls) == 1
    assert jobs.calls[0][1]["executor"] == "antigravity"
    assert jobs.calls[0][1]["executor_quota_state"] == "unknown"


@pytest.mark.asyncio
async def test_codex_milestone_boundary_never_submits(repository):
    jobs = Jobs()
    service = ExecutorService(jobs, Antigravity(status()), ExecutorSelector())
    with pytest.raises(BridgeError) as caught:
        await service.start(repository, request(None), "req")
    assert caught.value.code is ErrorCode.POLICY_VIOLATION
    assert caught.value.details == {"selection_reason": "automatic_quota_unknown"}
    assert jobs.calls == []


@pytest.mark.asyncio
async def test_busy_and_exhausted_create_no_job(repository):
    for state in (status(busy=True), status(QuotaState.EXHAUSTED)):
        jobs = Jobs()
        with pytest.raises(BridgeError):
            await ExecutorService(jobs, Antigravity(state), ExecutorSelector()).start(repository, request(), "req")
        assert jobs.calls == []
