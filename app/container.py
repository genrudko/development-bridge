from __future__ import annotations

from dataclasses import dataclass

from app.api.errors import BridgeError, ErrorCode
from app.audit import AuditSink, LoggingAuditSink
from app.capabilities import CapabilityPolicy
from app.changes import ChangeRevisionCalculator, ChangeService
from app.files import FileService
from app.git import GitRunner, GitService
from app.jobs import JobService, JobStore
from app.projects import ProjectRegistry
from app.settings import BridgeSettings, load_settings
from app.tasks import TaskRegistry


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    settings: BridgeSettings
    projects: ProjectRegistry
    capability_policy: CapabilityPolicy
    audit: AuditSink
    git: GitService
    files: FileService
    changes: ChangeService
    tasks: TaskRegistry
    jobs: JobService


def build_container(
    settings: BridgeSettings | None = None,
    *,
    audit: AuditSink | None = None,
) -> ApplicationContainer:
    configured = settings or load_settings()
    projects = ProjectRegistry.from_settings(configured)
    tasks = TaskRegistry.from_settings(configured)
    policy = CapabilityPolicy()
    runner = GitRunner()
    audit_sink = audit or LoggingAuditSink()
    database_path = (
        configured.jobs.database_path.expanduser().resolve()
        if configured.jobs.database_path is not None
        else None
    )
    if database_path is not None and tasks:
        for project in projects.list():
            for repository in project.repositories:
                try:
                    database_path.relative_to(repository.root)
                except ValueError:
                    continue
                raise BridgeError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Job database must be outside registered repositories",
                    details={
                        "project_id": repository.project_id,
                        "repository_id": repository.id,
                    },
                )
    job_store = (
        JobStore(database_path)
        if tasks and database_path is not None
        else None
    )
    return ApplicationContainer(
        settings=configured,
        projects=projects,
        capability_policy=policy,
        audit=audit_sink,
        git=GitService(runner, policy),
        files=FileService(policy),
        changes=ChangeService(policy, ChangeRevisionCalculator(runner)),
        tasks=tasks,
        jobs=JobService(job_store, tasks, projects, policy, audit_sink),
    )
