from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


IDENTIFIER_PATTERN = r"^[a-z][a-z0-9-]{0,62}$"


class ServerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = "development-bridge"
    host: str = "127.0.0.1"
    port: int = Field(default=8789, ge=1, le=65535)
    endpoint: str = "/mcp"


class RepositorySettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    path: Path
    capabilities: Mapping[str, bool] = Field(default_factory=dict)


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
    projects: tuple[ProjectSettings, ...] = ()

    @model_validator(mode="after")
    def project_ids_are_unique(self) -> BridgeSettings:
        identifiers = [project.id for project in self.projects]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate project id")
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
        settings = BridgeSettings.model_validate(raw)

    server_updates: dict[str, Any] = {}
    if host := environment.get("DEVELOPMENT_BRIDGE_HOST"):
        server_updates["host"] = host
    if port := environment.get("DEVELOPMENT_BRIDGE_PORT"):
        server_updates["port"] = int(port)
    if server_updates:
        settings = settings.model_copy(
            update={"server": settings.server.model_copy(update=server_updates)}
        )
    return settings

