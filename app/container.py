from __future__ import annotations

from dataclasses import dataclass

from app.api.errors import BridgeError, ErrorCode
from app.auth import BridgeOAuthProvider, OAuthStore
from app.audit import AuditSink, LoggingAuditSink
from app.capabilities import CapabilityPolicy
from app.changes import ChangeRevisionCalculator, ChangeService
from app.files import FileService
from app.git import GitRunner, GitService, GitWorkspaceService, GitWriteService
from app.jobs import ArtifactStorage, JobService, JobStore
from app.knowledge import (
    AttachmentStorage,
    AttachmentExportRegistry,
    KnowledgeAttachmentService,
    KnowledgeAttachmentExportService,
    KnowledgeService,
    KnowledgeStore,
    TelegramKnowledgeService,
)
from app.knowledge.telegram import TelegramAdapter, TelethonTelegramAdapter
from app.projects import ProjectRegistry, RepositoryMutationLock
from app.settings import BridgeSettings, load_settings
from app.tasks import TaskRegistry


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    settings: BridgeSettings
    projects: ProjectRegistry
    capability_policy: CapabilityPolicy
    audit: AuditSink
    git: GitService
    git_write: GitWriteService
    git_workspace: GitWorkspaceService
    files: FileService
    changes: ChangeService
    tasks: TaskRegistry
    jobs: JobService
    oauth: BridgeOAuthProvider | None
    knowledge: KnowledgeService | None
    telegram_knowledge: TelegramKnowledgeService | None
    knowledge_attachments: KnowledgeAttachmentService | None
    knowledge_attachment_exports: KnowledgeAttachmentExportService | None


def build_container(
    settings: BridgeSettings | None = None,
    *,
    audit: AuditSink | None = None,
    telegram_adapter: TelegramAdapter | None = None,
) -> ApplicationContainer:
    configured = settings or load_settings()
    projects = ProjectRegistry.from_settings(configured)
    tasks = TaskRegistry.from_settings(configured)
    policy = CapabilityPolicy()
    runner = GitRunner()
    mutations = RepositoryMutationLock()
    revisions = ChangeRevisionCalculator(runner)
    audit_sink = audit or LoggingAuditSink()
    database_path = (
        configured.jobs.database_path.expanduser().resolve()
        if configured.jobs.database_path is not None
        else None
    )
    artifact_directory = (
        configured.jobs.artifact_directory.expanduser().resolve()
        if configured.jobs.artifact_directory is not None
        else None
    )
    oauth_database_path = (
        configured.oauth.database_path.expanduser().resolve()
        if configured.oauth.database_path is not None
        else None
    )
    knowledge_database_path = (
        configured.knowledge.database_path.expanduser().resolve()
        if configured.knowledge.database_path is not None
        else None
    )
    telegram_session_path = (
        configured.knowledge.telegram.session_path.expanduser().resolve()
        if configured.knowledge.telegram.session_path is not None
        else None
    )
    knowledge_attachment_directory = (
        configured.knowledge.attachment_directory.expanduser().resolve()
        if configured.knowledge.attachment_directory is not None
        else None
    )
    for state_path, label in (
        (database_path, "Job database"),
        (artifact_directory, "Artifact directory"),
        (oauth_database_path, "OAuth database"),
        (knowledge_database_path, "Knowledge database"),
        (telegram_session_path, "Telegram session"),
        (knowledge_attachment_directory, "Knowledge attachment directory"),
    ):
        if state_path is None:
            continue
        for project in projects.list():
            for repository in project.repositories:
                try:
                    state_path.relative_to(repository.root)
                except ValueError:
                    continue
                raise BridgeError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"{label} must be outside registered repositories",
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
    oauth = None
    if configured.oauth.enabled:
        if configured.oauth.owner_verifier is None:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "DEVELOPMENT_BRIDGE_OWNER_VERIFIER is required when OAuth is enabled",
            )
        assert oauth_database_path is not None
        assert configured.oauth.issuer_url is not None
        assert configured.oauth.resource_url is not None
        oauth_store = OAuthStore(oauth_database_path)
        oauth_store.initialize()
        oauth = BridgeOAuthProvider(
            oauth_store,
            issuer_url=str(configured.oauth.issuer_url),
            resource_url=str(configured.oauth.resource_url),
            owner_verifier=configured.oauth.owner_verifier.get_secret_value(),
            access_token_ttl_seconds=configured.oauth.access_token_ttl_seconds,
            refresh_token_ttl_seconds=configured.oauth.refresh_token_ttl_seconds,
        )
    knowledge_store = (
        KnowledgeStore(knowledge_database_path)
        if knowledge_database_path is not None
        else None
    )
    telegram = configured.knowledge.telegram
    telegram_knowledge = None
    configured_adapter = telegram_adapter
    if configured_adapter is None and (
        telegram.api_id is not None
        and telegram.api_hash is not None
        and telegram_session_path is not None
    ):
        configured_adapter = TelethonTelegramAdapter(
            telegram.api_id,
            telegram.api_hash.get_secret_value(),
            telegram_session_path,
        )
    if knowledge_store is not None and configured_adapter is not None:
        telegram_knowledge = TelegramKnowledgeService(
            knowledge_store,
            configured_adapter,
            default_batch_size=telegram.sync_batch_size,
            recent_window_size=telegram.recent_window_size,
        )
    knowledge_attachments = None
    knowledge_attachment_exports = None
    if knowledge_store is not None and knowledge_attachment_directory is not None:
        knowledge_attachments = KnowledgeAttachmentService(
            knowledge_store,
            AttachmentStorage(
                knowledge_attachment_directory,
                configured.knowledge.attachment_max_bytes,
            ),
            configured_adapter,
        )
        knowledge_attachment_exports = KnowledgeAttachmentExportService(
            knowledge_attachments,
            AttachmentExportRegistry(
                configured.knowledge.attachment_export_ttl_seconds
            ),
            (
                str(configured.server.public_base_url)
                if configured.server.public_base_url is not None
                else None
            ),
            configured.server.endpoint,
        )
    return ApplicationContainer(
        settings=configured,
        projects=projects,
        capability_policy=policy,
        audit=audit_sink,
        git=GitService(runner, policy),
        git_write=GitWriteService(runner, policy, revisions, mutations),
        git_workspace=GitWorkspaceService(runner, policy, revisions, mutations),
        files=FileService(policy),
        changes=ChangeService(policy, revisions, mutations),
        tasks=tasks,
        jobs=JobService(
            job_store,
            tasks,
            projects,
            policy,
            audit_sink,
            ArtifactStorage(artifact_directory)
            if artifact_directory is not None
            else None,
        ),
        oauth=oauth,
        knowledge=(
            KnowledgeService(knowledge_store)
            if knowledge_store is not None
            else None
        ),
        telegram_knowledge=telegram_knowledge,
        knowledge_attachments=knowledge_attachments,
        knowledge_attachment_exports=knowledge_attachment_exports,
    )
