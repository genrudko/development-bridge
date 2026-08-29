from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    model_validator,
)

IDENTIFIER_PATTERN = r"^[a-z][a-z0-9-]{0,62}$"


class ServerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = "development-bridge"
    host: str = "127.0.0.1"
    port: int = Field(default=8789, ge=1, le=65535)
    endpoint: str = "/mcp"
    public_base_url: AnyHttpUrl | None = None
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*")
    x_trigger_token: SecretStr | None = Field(default=None, repr=False, exclude=True)

    @model_validator(mode="after")
    def public_base_url_is_canonical_https_origin(self) -> ServerSettings:
        if self.public_base_url is None:
            return self
        if self.public_base_url.scheme != "https":
            raise ValueError("server.public_base_url must use HTTPS")
        if (
            self.public_base_url.username is not None
            or self.public_base_url.password is not None
        ):
            raise ValueError("server.public_base_url must not contain credentials")
        if self.public_base_url.path not in {None, "", "/"}:
            raise ValueError("server.public_base_url must not contain a path")
        if self.public_base_url.query is not None or self.public_base_url.fragment is not None:
            raise ValueError("server.public_base_url must not contain query or fragment")
        return self


class ArtifactSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    path: str = Field(min_length=1, max_length=4096)
    media_type: str = Field(
        min_length=3,
        max_length=255,
        pattern=r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$",
    )
    required: bool = True
    max_bytes: int = Field(default=67_108_864, ge=1, le=1_073_741_824)

    @model_validator(mode="after")
    def path_is_repository_relative(self) -> ArtifactSettings:
        path = Path(self.path)
        if path.is_absolute() or ".." in path.parts or path.parts[0] == ".git":
            raise ValueError("artifact path must be repository-relative")
        if "\0" in self.path or self.path in {"", "."}:
            raise ValueError("artifact path is invalid")
        return self


class TaskProfileSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    executable: str = Field(min_length=1, max_length=4096)
    arguments: tuple[str, ...] = ()
    timeout_seconds: float = Field(default=300, gt=0, le=3600)
    output_limit_bytes: int = Field(default=262_144, ge=1024, le=1_048_576)
    artifacts: tuple[ArtifactSettings, ...] = ()

    @model_validator(mode="after")
    def artifact_ids_are_unique(self) -> TaskProfileSettings:
        identifiers = [artifact.id for artifact in self.artifacts]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"duplicate artifact id in task {self.id}")
        return self


class JobSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    database_path: Path | None = None
    artifact_directory: Path | None = None
    artifact_export_ttl_seconds: int = Field(default=600, ge=60, le=3600)
    max_concurrency: int = Field(default=8, ge=1, le=32)


def _default_managed_repository_root() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home) if data_home else Path.home() / ".local" / "share"
    return base / "development-bridge" / "repositories"


class ManagedRepositorySettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    root: Path = Field(default_factory=_default_managed_repository_root)


def _default_github_artifact_root() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home) if data_home else Path.home() / ".local" / "share"
    return base / "development-bridge" / "github-artifacts"


class GitHubSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    token: SecretStr | None = Field(default=None, repr=False, exclude=True)
    classic_token: SecretStr | None = Field(default=None, repr=False, exclude=True)
    timeout_seconds: float = Field(default=20, gt=0, le=120)
    response_limit_bytes: int = Field(default=2_097_152, ge=65_536, le=16_777_216)
    artifact_directory: Path = Field(default_factory=_default_github_artifact_root)
    artifact_max_bytes: int = Field(default=268_435_456, ge=1_048_576, le=1_073_741_824)
    artifact_export_ttl_seconds: int = Field(default=600, ge=60, le=3600)


class TelegramKnowledgeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    api_id: int | None = Field(default=None, gt=0)
    api_hash: SecretStr | None = Field(default=None, repr=False)
    session_path: Path | None = None
    sync_batch_size: int = Field(default=2000, ge=1, le=5000)
    recent_window_size: int = Field(default=100, ge=0, le=500)


def _default_route_registry_path() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return base / "development-bridge" / "routes.json"


class CoordinatorRoutingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    route_registry_path: Path = Field(default_factory=_default_route_registry_path)


class TelegramSupervisorSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    enabled: bool = False
    chat_id: int | None = None
    topic_id: int | None = Field(default=None, gt=0)
    channel_id: str = Field(default="telegram-supervisor", min_length=1, max_length=64)


class KnowledgeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    database_path: Path | None = None
    attachment_directory: Path | None = None
    attachment_max_bytes: int = Field(
        default=536_870_912, ge=1_048_576, le=4_294_967_296
    )
    attachment_export_ttl_seconds: int = Field(default=600, ge=60, le=3600)
    telegram: TelegramKnowledgeSettings = Field(default_factory=TelegramKnowledgeSettings)


class OAuthSettings(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, url_preserve_empty_path=True
    )
    enabled: bool = False
    issuer_url: AnyHttpUrl | None = None
    resource_url: AnyHttpUrl | None = None
    database_path: Path | None = None
    owner_verifier: SecretStr | None = Field(default=None, repr=False, exclude=True)
    access_token_ttl_seconds: int = Field(default=900, ge=60, le=86_400)
    refresh_token_ttl_seconds: int = Field(
        default=2_592_000, ge=3600, le=31_536_000
    )

    @model_validator(mode="after")
    def enabled_oauth_is_complete(self) -> OAuthSettings:
        if not self.enabled:
            return self
        missing = [
            name
            for name, value in (
                ("issuer_url", self.issuer_url),
                ("resource_url", self.resource_url),
                ("database_path", self.database_path),
            )
            if value is None
        ]
        if missing:
            raise ValueError(
                "enabled OAuth requires " + ", ".join(f"oauth.{name}" for name in missing)
            )
        return self


class DesktopNodeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    token: SecretStr | None = Field(default=None, repr=False, exclude=True)
    offline_after_seconds: float = Field(default=45, gt=1, le=300)
    claim_timeout_seconds: float = Field(default=25, gt=0, le=60)
    call_timeout_seconds: float = Field(default=300, gt=0, le=300)
    max_pending_commands: int = Field(default=32, ge=1, le=256)
    max_request_bytes: int = Field(default=262_144, ge=4096, le=2_097_152)
    max_arguments_bytes: int = Field(default=131_072, ge=1024, le=1_048_576)
    max_result_bytes: int = Field(default=1_048_576, ge=4096, le=8_388_608)
    result_artifact_directory: Path = Field(
        default_factory=lambda: Path.home() / ".local" / "state" / "development-bridge" / "desktop-results"
    )
    result_artifact_ttl_seconds: int = Field(default=3600, ge=60, le=86_400)
    max_result_upload_bytes: int = Field(default=67_108_864, ge=1_048_576, le=268_435_456)
    journal_path: Path | None = None
    journal_history_limit: int = Field(default=200, ge=20, le=5000)
    journal_max_bytes: int = Field(default=5_242_880, ge=65_536, le=67_108_864)


class RepositorySettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    path: Path
    capabilities: Mapping[str, bool] = Field(default_factory=dict)
    tasks: tuple[TaskProfileSettings, ...] = ()

    @model_validator(mode="after")
    def task_ids_are_unique(self) -> RepositorySettings:
        identifiers = [task.id for task in self.tasks]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"duplicate task id in repository {self.id}")
        return self


class ProjectSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    repositories: tuple[RepositorySettings, ...] = ()

    @model_validator(mode="after")
    def repository_ids_are_unique(self) -> ProjectSettings:
        identifiers = [repository.id for repository in self.repositories]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"duplicate repository id in project {self.id}")
        return self


class BridgeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: int = Field(default=1, ge=1, le=1)
    server: ServerSettings = Field(default_factory=ServerSettings)
    jobs: JobSettings = Field(default_factory=JobSettings)
    managed_repositories: ManagedRepositorySettings = Field(
        default_factory=ManagedRepositorySettings
    )
    github: GitHubSettings = Field(default_factory=GitHubSettings)
    knowledge: KnowledgeSettings = Field(default_factory=KnowledgeSettings)
    telegram_supervisor: TelegramSupervisorSettings = Field(default_factory=TelegramSupervisorSettings)
    coordinator: CoordinatorRoutingSettings = Field(default_factory=CoordinatorRoutingSettings)
    oauth: OAuthSettings = Field(default_factory=OAuthSettings)
    desktop_nodes: DesktopNodeSettings = Field(default_factory=DesktopNodeSettings)
    projects: tuple[ProjectSettings, ...] = ()

    @model_validator(mode="after")
    def project_ids_are_unique(self) -> BridgeSettings:
        identifiers = [project.id for project in self.projects]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate project id")
        if any(
            repository.tasks
            for project in self.projects
            for repository in project.repositories
        ) and self.jobs.database_path is None:
            raise ValueError("jobs.database_path is required when task profiles exist")
        if any(
            task.artifacts
            for project in self.projects
            for repository in project.repositories
            for task in repository.tasks
        ) and self.jobs.artifact_directory is None:
            raise ValueError(
                "jobs.artifact_directory is required when task artifacts exist"
            )
        if self.oauth.enabled:
            assert self.oauth.issuer_url is not None
            assert self.oauth.resource_url is not None
            issuer = self.oauth.issuer_url
            resource = self.oauth.resource_url
            if (issuer.scheme, issuer.host, issuer.port) != (
                resource.scheme,
                resource.host,
                resource.port,
            ):
                raise ValueError("embedded OAuth issuer and resource must share an origin")
            if resource.path != self.server.endpoint:
                raise ValueError("oauth.resource_url must identify the MCP endpoint")
            if resource.query or resource.fragment:
                raise ValueError("oauth.resource_url cannot contain query or fragment")
            if issuer.scheme != "https" and issuer.host not in {
                "localhost",
                "127.0.0.1",
                "[::1]",
            }:
                raise ValueError("remote OAuth URLs must use HTTPS")
        return self


def load_settings(
    path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> BridgeSettings:
    """Load and fully validate Bridge settings before service construction."""
    environment = os.environ if environ is None else environ
    configured_path = path or environment.get("DEVELOPMENT_BRIDGE_CONFIG")
    if configured_path is None:
        settings = BridgeSettings()
    else:
        config_path = Path(configured_path).expanduser().resolve(strict=True)
        with config_path.open("r", encoding="utf-8") as config_file:
            raw: Any = yaml.safe_load(config_file) or {}
        if not isinstance(raw, dict):
            raise ValueError("Bridge configuration root must be an object")
        if isinstance(raw.get("oauth"), dict) and "owner_verifier" in raw["oauth"]:
            raise ValueError(
                "OAuth owner verifier must be supplied through the deployment environment"
            )
        if isinstance(raw.get("github"), dict) and (
            "token" in raw["github"] or "classic_token" in raw["github"]
        ):
            raise ValueError("GitHub tokens must be supplied through the deployment environment")
        if isinstance(raw.get("server"), dict) and "x_trigger_token" in raw["server"]:
            raise ValueError(
                "X trigger token must be supplied through the deployment environment"
            )
        if isinstance(raw.get("desktop_nodes"), dict) and "token" in raw["desktop_nodes"]:
            raise ValueError("Desktop node token must be supplied through the deployment environment")
        settings = BridgeSettings.model_validate(raw)

    server_updates: dict[str, Any] = {}
    if host := environment.get("DEVELOPMENT_BRIDGE_HOST"):
        server_updates["host"] = host
    if port := environment.get("DEVELOPMENT_BRIDGE_PORT"):
        server_updates["port"] = int(port)
    if token := environment.get("DEVELOPMENT_BRIDGE_X_TRIGGER_TOKEN"):
        server_updates["x_trigger_token"] = token
    if server_updates:
        validated_server = ServerSettings.model_validate(
            {
                **settings.server.model_dump(),
                **(
                    {"x_trigger_token": settings.server.x_trigger_token}
                    if settings.server.x_trigger_token is not None
                    else {}
                ),
                **server_updates,
            }
        )
        settings = settings.model_copy(update={"server": validated_server})
    environment_updates: dict[str, Any] = {}

    telegram_updates: dict[str, Any] = {}
    if api_id := environment.get("DEVELOPMENT_BRIDGE_TELEGRAM_API_ID"):
        telegram_updates["api_id"] = int(api_id)
    if api_hash := environment.get("DEVELOPMENT_BRIDGE_TELEGRAM_API_HASH"):
        telegram_updates["api_hash"] = api_hash
    if session_path := environment.get("DEVELOPMENT_BRIDGE_TELEGRAM_SESSION_PATH"):
        telegram_updates["session_path"] = session_path
    if telegram_updates:
        telegram = TelegramKnowledgeSettings.model_validate(
            {**settings.knowledge.telegram.model_dump(), **telegram_updates}
        )
        environment_updates["knowledge"] = KnowledgeSettings.model_validate(
            {**settings.knowledge.model_dump(), "telegram": telegram}
        )

    coordinator_updates: dict[str, Any] = {}
    if route_path := environment.get("DEVELOPMENT_BRIDGE_ROUTE_REGISTRY_PATH"):
        coordinator_updates["route_registry_path"] = Path(route_path)
    if coordinator_updates:
        environment_updates["coordinator"] = CoordinatorRoutingSettings.model_validate(
            {**settings.coordinator.model_dump(), **coordinator_updates}
        )

    supervisor_updates: dict[str, Any] = {}
    if raw_enabled := environment.get("DEVELOPMENT_BRIDGE_TELEGRAM_SUPERVISOR_ENABLED"):
        normalized = raw_enabled.strip().lower()
        if normalized not in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
            raise ValueError("DEVELOPMENT_BRIDGE_TELEGRAM_SUPERVISOR_ENABLED must be a boolean")
        supervisor_updates["enabled"] = normalized in {"1", "true", "yes", "on"}
    if chat_id := environment.get("DEVELOPMENT_BRIDGE_TELEGRAM_SUPERVISOR_CHAT_ID"):
        supervisor_updates["chat_id"] = int(chat_id)
    if topic_id := environment.get("DEVELOPMENT_BRIDGE_TELEGRAM_SUPERVISOR_TOPIC_ID"):
        supervisor_updates["topic_id"] = int(topic_id)
    if channel_id := environment.get("DEVELOPMENT_BRIDGE_TELEGRAM_SUPERVISOR_CHANNEL_ID"):
        supervisor_updates["channel_id"] = channel_id
    if supervisor_updates:
        environment_updates["telegram_supervisor"] = TelegramSupervisorSettings.model_validate(
            {**settings.telegram_supervisor.model_dump(), **supervisor_updates}
        )

    if owner_verifier := environment.get("DEVELOPMENT_BRIDGE_OWNER_VERIFIER"):
        environment_updates["oauth"] = OAuthSettings.model_validate(
            {**settings.oauth.model_dump(), "owner_verifier": owner_verifier}
        )

    github_updates: dict[str, Any] = {}
    if github_token := environment.get("DEVELOPMENT_BRIDGE_GITHUB_TOKEN"):
        github_updates["token"] = github_token
    if github_classic_token := environment.get("DEVELOPMENT_BRIDGE_GITHUB_CLASSIC_TOKEN"):
        github_updates["classic_token"] = github_classic_token
    if github_updates:
        environment_updates["github"] = GitHubSettings.model_validate(
            {
                **settings.github.model_dump(),
                **(
                    {"token": settings.github.token}
                    if settings.github.token is not None
                    else {}
                ),
                **(
                    {"classic_token": settings.github.classic_token}
                    if settings.github.classic_token is not None
                    else {}
                ),
                **github_updates,
            }
        )
    desktop_updates: dict[str, Any] = {}
    if desktop_token := environment.get("DEVELOPMENT_BRIDGE_DESKTOP_NODE_TOKEN"):
        desktop_updates["token"] = desktop_token
    if desktop_journal := environment.get("DEVELOPMENT_BRIDGE_DESKTOP_NODE_JOURNAL_PATH"):
        desktop_updates["journal_path"] = Path(desktop_journal)
    if desktop_updates:
        environment_updates["desktop_nodes"] = DesktopNodeSettings.model_validate(
            {**settings.desktop_nodes.model_dump(), **desktop_updates}
        )

    if environment_updates:
        settings = settings.model_copy(update=environment_updates)
    return settings
