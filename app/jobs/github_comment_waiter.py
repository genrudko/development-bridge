from __future__ import annotations

from typing import Any

from app.jobs.models import JobRecord


class GitHubJobCommentDelivery:
    HANDLER_NAME = "github-pr-comment"

    def __init__(self, jobs, projects, github) -> None:
        self._jobs = jobs
        self._projects = projects
        self._github = github
        jobs.register_durable_terminal_handler(self.HANDLER_NAME, self._handle)

    async def arm(
        self,
        *,
        repository,
        project_id: str,
        repository_id: str,
        job_ids: tuple[str, ...],
        policy: str,
        pull_number: int,
        body: str,
    ) -> dict[str, Any]:
        payload = {
            "project_id": project_id,
            "repository_id": repository_id,
            "pull_number": pull_number,
            "body": body,
        }
        return await self._jobs.wake_on_jobs_durable(
            repository, job_ids, policy, self.HANDLER_NAME, payload
        )

    async def _handle(
        self, payload: dict[str, object], records: tuple[JobRecord, ...], reason: str
    ) -> None:
        repository = self._projects.repositories.get(
            str(payload["project_id"]), str(payload["repository_id"])
        )
        lines = [str(payload["body"]).rstrip(), "", f"reason={reason}"]
        for record in records:
            line = f"{record.job_id} status={record.status.value}"
            if record.finished_at is not None:
                line += f" finished_at={record.finished_at}"
            if record.exit_code is not None:
                line += f" exit_code={record.exit_code}"
            if record.failure_reason is not None:
                line += f" failure_reason={record.failure_reason}"
            lines.append(line)
        await self._github.pull_comment(
            repository, int(payload["pull_number"]), "\n".join(lines)
        )
