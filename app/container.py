from __future__ import annotations

from dataclasses import dataclass

from app.api.capability_exports import CapabilityExportRegistry
from app.api.errors import BridgeError, ErrorCode
from app.audit import AuditSink, LoggingAuditSink
from app.auth import BridgeOAuthProvider, OAuthStore
from app.bridge_restart import BridgeRestartService
from app.capabilities import CapabilityPolicy
from app.changes import ChangeRevisionCalculator, ChangeService
from app.chatgpt_share import (
    ChatGPTShareService,
    ChatGPTShareTransport,
    UrllibChatGPTShareTransport,
)
from app.commands import RepositoryCommandService
from app.coordinator import (
    CoordinatorService,
    CoordinatorWakeDeliveryService,
    ReviewGptWakeTransport,
    RouteRegistry,
    WakeTransport,
)
from app.desktop_nodes import DesktopNodeService
from app.files import FileService
from app.executors import AntigravityExecutor, AsyncioProcessRunner, ExecutorSelector, ExecutorService
from app.git import GitRunner, GitService, GitWorkspaceService, GitWriteService
from app.github import (
    GitHubActionsArtifactExportService,
    GitHubArtifactSnapshot,
    GitHubHostService,
    GitHubTransport,
    UrllibGitHubTransport,
)
from app.jobs import (
    ArtifactStorage,
    JobArtifactExportService,
    JobArtifactExportSubject,
    JobService,
    JobStore,
)
from app.jobs.github_comment_waiter import GitHubJobCommentDelivery
from app.knowledge import (
    AttachmentExportRegistry,
    AttachmentStorage,
    KnowledgeAttachmentExportService,
    KnowledgeAttachmentService,
    KnowledgeService,
    KnowledgeStore,
    TelegramKnowledgeService,
)
from app.knowledge.telegram import TelegramAdapter, TelethonTelegramAdapter
from app.projects import (
    ManagedCloneRunner,
    ManagedRepositoryService,
    ProjectRegistry,
    RepositoryMutationLock,
)
from app.settings import BridgeSettings, load_settings
from app.tasks import TaskRegistry
from app.telegram_supervisor import TelegramSupervisorService


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    settings: BridgeSettings
    projects: ProjectRegistry
    managed_repositories: ManagedRepositoryService
    capability_policy: CapabilityPolicy
    audit: AuditSink
    git: GitService
    git_write: GitWriteService
    git_workspace: GitWorkspaceService
    files: FileService
    changes: ChangeService
    tasks: TaskRegistry
    jobs: JobService
    executors: ExecutorService
    job_artifact_exports: JobArtifactExportService
    github: GitHubHostService
    github_job_comments: GitHubJobCommentDelivery
    github_artifact_exports: GitHubActionsArtifactExportService
    oauth: BridgeOAuthProvider | None
    knowledge: KnowledgeService | None
    telegram_knowledge: TelegramKnowledgeService | None
    telegram_supervisor: TelegramSupervisorService | None
    knowledge_attachments: KnowledgeAttachmentService | None
    knowledge_attachment_exports: KnowledgeAttachmentExportService | None
    chatgpt_share: ChatGPTShareService
    coordinator: CoordinatorService
    route_registry: RouteRegistry
    commands: RepositoryCommandService
    bridge_restart: BridgeRestartService
    desktop_nodes: DesktopNodeService
    coordinator_wake_delivery: CoordinatorWakeDeliveryService | None


def build_container(
    settings: BridgeSettings | None = None,
    *,
    audit: AuditSink | None = None,
    telegram_adapter: TelegramAdapter | None = None,
    managed_clone_runner: ManagedCloneRunner | None = None,
    github_transport: GitHubTransport | None = None,
    github_fork_transport: GitHubTransport | None = None,
    chatgpt_share_transport: ChatGPTShareTransport | None = None,
    review_gpt_transport: WakeTransport | None = None,
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
    desktop_journal_path = (
        configured.desktop_nodes.journal_path.expanduser().resolve()
        if configured.desktop_nodes.journal_path is not None
        else None
    )
    desktop_result_directory = (
        configured.desktop_nodes.result_artifact_directory.expanduser().resolve()
    )
    managed_repository_root = configured.managed_repositories.root.expanduser().resolve()
    github_artifact_directory = configured.github.artifact_directory.expanduser().resolve()
    for state_path, label in (
        (database_path, "Job database"),
        (artifact_directory, "Artifact directory"),
        (oauth_database_path, "OAuth database"),
        (knowledge_database_path, "Knowledge database"),
        (telegram_session_path, "Telegram session"),
        (knowledge_attachment_directory, "Knowledge attachment directory"),
        (desktop_journal_path, "Desktop operation journal"),
        (desktop_result_directory, "Desktop result artifact directory"),
        (managed_repository_root, "Managed repository root"),
        (github_artifact_directory, "GitHub artifact directory"),
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
    managed_repositories = ManagedRepositoryService(
        managed_repository_root, projects, managed_clone_runner
    )
    job_store = (
        JobStore(database_path)
        if database_path is not None
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
    jobs = JobService(
        job_store,
        tasks,
        projects,
        policy,
        audit_sink,
        ArtifactStorage(artifact_directory)
        if artifact_directory is not None
        else None,
        max_concurrency=configured.jobs.max_concurrency,
    )
    executors = ExecutorService(
        jobs,
        AntigravityExecutor(configured.executors.antigravity, AsyncioProcessRunner()),
        ExecutorSelector(),
    )
    job_artifact_exports = JobArtifactExportService(
        jobs,
        projects,
        CapabilityExportRegistry[JobArtifactExportSubject](
            configured.jobs.artifact_export_ttl_seconds
        ),
        (
            str(configured.server.public_base_url)
            if configured.server.public_base_url is not None
            else None
        ),
        configured.server.endpoint,
    )
    github_token = (
        configured.github.token.get_secret_value()
        if configured.github.token is not None
        else None
    )
    github_classic_token = (
        configured.github.classic_token.get_secret_value()
        if configured.github.classic_token is not None
        else None
    )
    if github_transport is None and github_token is not None:
        github_transport = UrllibGitHubTransport(
            github_token,
            timeout_seconds=configured.github.timeout_seconds,
            response_limit_bytes=configured.github.response_limit_bytes,
        )
    if github_fork_transport is None and github_classic_token is not None:
        github_fork_transport = UrllibGitHubTransport(
            github_classic_token,
            timeout_seconds=configured.github.timeout_seconds,
            response_limit_bytes=configured.github.response_limit_bytes,
        )
    github = GitHubHostService(
        runner, policy, github_transport, managed_repositories,
        fork_transport=github_fork_transport,
    )
    github_job_comments = GitHubJobCommentDelivery(jobs, projects, github)
    github_artifact_exports = GitHubActionsArtifactExportService(
        github,
        CapabilityExportRegistry[GitHubArtifactSnapshot](
            configured.github.artifact_export_ttl_seconds
        ),
        github_artifact_directory,
        str(configured.server.public_base_url) if configured.server.public_base_url else None,
        configured.server.endpoint,
        configured.github.artifact_max_bytes,
    )
    route_registry = RouteRegistry(configured.coordinator.route_registry_path)
    coordinator = CoordinatorService(
        route_registry.path.parent / "coordinator-wakes.json",
        browser_preflight_required=True,
    )

    async def resume_coordinator_waiter(payload, records, reason):
        route_id = payload.get("route_id")
        if route_id is not None:
            route = route_registry.resolve(str(route_id))
            if route is None:
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    f"durable coordinator waiter route no longer exists: {route_id}",
                    retryable=True,
                )
            channel_id = str(route["channel_id"])
        else:
            channel_id = str(payload["channel_id"])
        await coordinator.arm_job_continuation(
            records, reason, channel_id=channel_id,
            message=(str(payload["message"]) if payload.get("message") is not None else None),
        )

    jobs.register_durable_terminal_handler("coordinator", resume_coordinator_waiter)
    supervisor_settings = configured.telegram_supervisor
    telegram_supervisor = None
    if supervisor_settings.enabled:
        telegram_supervisor = TelegramSupervisorService(
            enabled=True,
            api_id=telegram.api_id,
            api_hash=(telegram.api_hash.get_secret_value() if telegram.api_hash is not None else None),
            session_path=telegram_session_path,
            chat_id=supervisor_settings.chat_id,
            topic_id=supervisor_settings.topic_id,
            channel_id=supervisor_settings.channel_id,
            coordinator=coordinator,
            route_registry=route_registry,
        )
    wake_settings = configured.coordinator_wake_delivery
    coordinator_wake_delivery = None
    if wake_settings.enabled:
        transport = review_gpt_transport
        if transport is None and wake_settings.primary_transport == "review-gpt":
            rg = wake_settings.review_gpt
            assert rg.node_executable is not None
            assert rg.cli_path is not None
            assert rg.config_path is not None
            assert rg.browser_endpoint is not None
            assert rg.receipt_directory is not None
            transport = ReviewGptWakeTransport(
                node_path=rg.node_executable,
                cli_path=rg.cli_path,
                config_path=rg.config_path,
                browser_endpoint=rg.browser_endpoint,
                receipt_dir=rg.receipt_directory,
                timeout_seconds=rg.process_timeout_seconds,
                browser_start_command=rg.browser_start_command,
                browser_stop_command=rg.browser_stop_command,
                browser_lifecycle_timeout_seconds=rg.browser_lifecycle_timeout_seconds,
            )
        coordinator_wake_delivery = CoordinatorWakeDeliveryService(
            coordinator,
            route_registry,
            transport=transport,
            enabled=True,
            poll_interval_seconds=wake_settings.poll_interval_seconds,
        )
    commands = RepositoryCommandService(jobs, policy)
    return ApplicationContainer(
        settings=configured,
        projects=projects,
        managed_repositories=managed_repositories,
        capability_policy=policy,
        audit=audit_sink,
        git=GitService(runner, policy),
        git_write=GitWriteService(
            runner, policy, revisions, mutations, github_token=github_token
        ),
        git_workspace=GitWorkspaceService(runner, policy, revisions, mutations),
        files=FileService(policy),
        changes=ChangeService(policy, revisions, mutations),
        tasks=tasks,
        jobs=jobs,
        executors=executors,
        job_artifact_exports=job_artifact_exports,
        github=github,
        github_job_comments=github_job_comments,
        github_artifact_exports=github_artifact_exports,
        oauth=oauth,
        knowledge=(
            KnowledgeService(knowledge_store)
            if knowledge_store is not None
            else None
        ),
        telegram_knowledge=telegram_knowledge,
        telegram_supervisor=telegram_supervisor,
        knowledge_attachments=knowledge_attachments,
        knowledge_attachment_exports=knowledge_attachment_exports,
        chatgpt_share=ChatGPTShareService(
            chatgpt_share_transport or UrllibChatGPTShareTransport()
        ),
        coordinator=coordinator,
        route_registry=route_registry,
        commands=commands,
        bridge_restart=BridgeRestartService(jobs),
        desktop_nodes=DesktopNodeService(
            configured.desktop_nodes,
            str(configured.server.public_base_url) if configured.server.public_base_url else None,
            configured.server.endpoint,
        ),
        coordinator_wake_delivery=coordinator_wake_delivery,
    )
