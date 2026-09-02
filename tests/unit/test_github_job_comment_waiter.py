from __future__ import annotations

import pytest

from app.jobs.models import JobRecord, JobStatus
from app.jobs.github_comment_waiter import GitHubJobCommentDelivery


class FakeJobs:
    def __init__(self):
        self.handler = None
        self.waiter_call = None

    def register_durable_terminal_handler(self, name, handler):
        assert name == "github-pr-comment"
        self.handler = handler

    async def wake_on_jobs_durable(self, repository, job_ids, policy, handler_name, payload):
        self.waiter_call = (repository, job_ids, policy, handler_name, payload)
        return {"waiter_id": "wait_1", "state": "waiting", "durable": True}


class FakeRepositories:
    def __init__(self, repository):
        self.repository = repository

    def get(self, project_id, repository_id):
        assert (project_id, repository_id) == ("development-bridge", "development-bridge")
        return self.repository


class FakeProjects:
    def __init__(self, repository):
        self.repositories = FakeRepositories(repository)


class FakeGitHub:
    def __init__(self):
        self.calls = []

    async def pull_comment(self, repository, pull_number, body):
        self.calls.append((repository, pull_number, body))
        return {"id": 1, "body": body}


@pytest.mark.asyncio
async def test_github_job_comment_delivery_arms_durable_waiter_and_posts_terminal_evidence():
    repository = object()
    jobs = FakeJobs()
    github = FakeGitHub()
    service = GitHubJobCommentDelivery(jobs, FakeProjects(repository), github)

    result = await service.arm(
        repository=repository,
        project_id="development-bridge",
        repository_id="development-bridge",
        job_ids=("job_abc",),
        policy="all_terminal",
        pull_number=2,
        body="DBRIDGE-WORK-SOAK-6A95 checkpoint=1 chat_marker=WORK_SOAK_6A95_1",
    )

    assert result["state"] == "waiting"
    assert jobs.waiter_call[1:4] == (("job_abc",), "all_terminal", "github-pr-comment")
    payload = jobs.waiter_call[4]
    record = JobRecord(
        job_id="job_abc",
        project_id="development-bridge",
        repository_id="development-bridge",
        task_id="__repository_exec__",
        request_id="req_1",
        status=JobStatus.SUCCEEDED,
        created_at="2026-09-01T00:00:00+00:00",
        finished_at="2026-09-01T00:01:00+00:00",
        exit_code=0,
    )

    await jobs.handler(payload, (record,), "all_terminal")

    assert len(github.calls) == 1
    called_repository, pull_number, body = github.calls[0]
    assert called_repository is repository
    assert pull_number == 2
    assert "DBRIDGE-WORK-SOAK-6A95 checkpoint=1" in body
    assert "reason=all_terminal" in body
    assert "job_abc status=succeeded" in body
    assert "finished_at=2026-09-01T00:01:00+00:00" in body
