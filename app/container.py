from __future__ import annotations

from dataclasses import dataclass

from app.audit import AuditSink, LoggingAuditSink
from app.capabilities import CapabilityPolicy
from app.changes import ChangeRevisionCalculator, ChangeService
from app.files import FileService
from app.git import GitRunner, GitService
from app.projects import ProjectRegistry
from app.settings import BridgeSettings, load_settings


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    settings: BridgeSettings
    projects: ProjectRegistry
    capability_policy: CapabilityPolicy
    audit: AuditSink
    git: GitService
    files: FileService
    changes: ChangeService


def build_container(
    settings: BridgeSettings | None = None,
    *,
    audit: AuditSink | None = None,
) -> ApplicationContainer:
    configured = settings or load_settings()
    projects = ProjectRegistry.from_settings(configured)
    policy = CapabilityPolicy()
    runner = GitRunner()
    return ApplicationContainer(
        settings=configured,
        projects=projects,
        capability_policy=policy,
        audit=audit or LoggingAuditSink(),
        git=GitService(runner, policy),
        files=FileService(policy),
        changes=ChangeService(policy, ChangeRevisionCalculator(runner)),
    )
