from __future__ import annotations

from dataclasses import dataclass

from app.audit import AuditSink, LoggingAuditSink
from app.capabilities import CapabilityPolicy
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


def build_container(
    settings: BridgeSettings | None = None,
    *,
    audit: AuditSink | None = None,
) -> ApplicationContainer:
    configured = settings or load_settings()
    projects = ProjectRegistry.from_settings(configured)
    policy = CapabilityPolicy()
    return ApplicationContainer(
        settings=configured,
        projects=projects,
        capability_policy=policy,
        audit=audit or LoggingAuditSink(),
        git=GitService(GitRunner(), policy),
        files=FileService(policy),
    )
