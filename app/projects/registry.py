from __future__ import annotations

from types import MappingProxyType
from typing import Callable, Mapping

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import CapabilitySet
from app.settings import BridgeSettings

from .models import Project, Repository


class RepositoryRegistry:
    def __init__(self, repositories: Mapping[tuple[str, str], Repository]) -> None:
        self._repositories = MappingProxyType(dict(repositories))
        self._configured = frozenset(repositories)
        self._managed_access_callback: Callable[[str, str], None] | None = None

    @classmethod
    def from_settings(cls, settings: BridgeSettings) -> RepositoryRegistry:
        repositories: dict[tuple[str, str], Repository] = {}
        for project in settings.projects:
            for configured in project.repositories:
                try:
                    root = configured.path.expanduser().resolve(strict=True)
                except OSError as exc:
                    raise BridgeError(
                        ErrorCode.INVALID_ARGUMENT,
                        "Configured repository path does not exist",
                        details={
                            "project_id": project.id,
                            "repository_id": configured.id,
                        },
                    ) from exc
                if not root.is_dir() or not (root / ".git").exists():
                    raise BridgeError(
                        ErrorCode.INVALID_ARGUMENT,
                        "Configured path is not a Git repository root",
                        details={
                            "project_id": project.id,
                            "repository_id": configured.id,
                        },
                    )
                repository = Repository(
                    project_id=project.id,
                    id=configured.id,
                    root=root,
                    capabilities=CapabilitySet.from_mapping(configured.capabilities),
                )
                repositories[(project.id, configured.id)] = repository
        return cls(repositories)

    def get(self, project_id: str, repository_id: str) -> Repository:
        repository = self._repositories.get((project_id, repository_id))
        if repository is None:
            raise BridgeError(
                ErrorCode.REPOSITORY_NOT_FOUND,
                "Repository is not registered",
                details={
                    "project_id": project_id,
                    "repository_id": repository_id,
                },
            )
        key = (project_id, repository_id)
        if key not in self._configured and self._managed_access_callback is not None:
            self._managed_access_callback(project_id, repository_id)
        return repository

    def for_project(self, project_id: str) -> tuple[Repository, ...]:
        return tuple(
            repository
            for (registered_project, _), repository in self._repositories.items()
            if registered_project == project_id
        )

    def is_configured(self, project_id: str, repository_id: str) -> bool:
        return (project_id, repository_id) in self._configured

    def set_managed_access_callback(
        self, callback: Callable[[str, str], None] | None
    ) -> None:
        self._managed_access_callback = callback

    def register_managed(self, repository: Repository) -> None:
        key = (repository.project_id, repository.id)
        if key in self._repositories:
            raise BridgeError(
                ErrorCode.REPOSITORY_CONFLICT,
                "Repository identifier is already registered",
                details={"project_id": repository.project_id, "repository_id": repository.id},
            )
        self._repositories = MappingProxyType({**self._repositories, key: repository})


class ProjectRegistry:
    def __init__(
        self,
        projects: Mapping[str, Project],
        repositories: RepositoryRegistry,
    ) -> None:
        self._projects = MappingProxyType(dict(projects))
        self.repositories = repositories

    @classmethod
    def from_settings(cls, settings: BridgeSettings) -> ProjectRegistry:
        repositories = RepositoryRegistry.from_settings(settings)
        projects = {
            configured.id: Project(
                id=configured.id,
                name=configured.name,
                repositories=repositories.for_project(configured.id),
            )
            for configured in settings.projects
        }
        return cls(projects, repositories)

    def list(self) -> tuple[Project, ...]:
        return tuple(self.get(project_id) for project_id in self._projects)

    def get(self, project_id: str) -> Project:
        project = self._projects.get(project_id)
        if project is None:
            raise BridgeError(
                ErrorCode.PROJECT_NOT_FOUND,
                "Project is not registered",
                details={"project_id": project_id},
            )
        return Project(
            id=project.id,
            name=project.name,
            repositories=self.repositories.for_project(project.id),
        )
