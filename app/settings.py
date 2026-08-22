from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

import yaml
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, SecretStr, model_validator


IDENTIFIER_PATTERN = r"^[a-z][a-z0-9-]{0,62}$"


class ServerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = "development-bridge"
    host: str = "127.0.0.1"
    port: int = Field(default=8789, ge=1, le=65535)
    endpoint: str = "/mcp"
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*")


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


class TelegramKnowledgeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    api_id: int | None = Field(default=None, gt=0)
    api_hash: SecretStr | None = Field(default=None, repr=False)
    session_path: Path | None = None
    sync_batch_size: int = Field(default=2000, ge=1, le=5000)
    recent_window_size: int = Field(default=100, ge=0, le=500)


class KnowledgeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    database_path: Path | None = None
    attachment_directory: Path | None = None
    attachment_max_bytes: int = Field(
        default=536_870_912, ge=1_048_576, le=4_294_967_296
    )
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
    knowledge: KnowledgeSettings = Field(default_factory=KnowledgeSettings)
    oauth: OAuthSettings = Field(default_factory=OAuthSettings)
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
        settings = BridgeSettings.model_validate(raw)

    server_updates: dict[str, Any] = {}
    if host := environment.get("DEVELOPMENT_BRIDGE_HOST"):
        server_updates["host"] = host
    if port := environment.get("DEVELOPMENT_BRIDGE_PORT"):
        server_updates["port"] = int(port)
    if server_updates:
        validated_server = ServerSettings.model_validate(
            {**settings.server.model_dump(), **server_updates}
        )
        settings = BridgeSettings.model_validate(
            {**settings.model_dump(), "server": validated_server}
        )
    if owner_verifier := environment.get("DEVELOPMENT_BRIDGE_OWNER_VERIFIER"):
        validated_oauth = OAuthSettings.model_validate(
            {**settings.oauth.model_dump(), "owner_verifier": owner_verifier}
        )
        settings = BridgeSettings.model_validate(
            {**settings.model_dump(), "oauth": validated_oauth}
        )
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
        knowledge = KnowledgeSettings.model_validate(
            {**settings.knowledge.model_dump(), "telegram": telegram}
        )
        settings = BridgeSettings.model_validate(
            {**settings.model_dump(), "knowledge": knowledge}
        )
    return settings
