from __future__ import annotations

from types import MappingProxyType

from app.api.errors import BridgeError, ErrorCode
from app.settings import BridgeSettings

from .models import TaskProfile


class TaskRegistry:
    def __init__(self, profiles: dict[tuple[str, str, str], TaskProfile]) -> None:
        self._profiles = MappingProxyType(dict(profiles))

    @classmethod
    def from_settings(cls, settings: BridgeSettings) -> TaskRegistry:
        profiles = {}
        for project in settings.projects:
            for repository in project.repositories:
                for configured in repository.tasks:
                    profile = TaskProfile(
                        project.id,
                        repository.id,
                        configured.id,
                        configured.name,
                        configured.executable,
                        configured.arguments,
                        configured.timeout_seconds,
                        configured.output_limit_bytes,
                    )
                    profiles[(project.id, repository.id, configured.id)] = profile
        return cls(profiles)

    def list(self, project_id: str, repository_id: str) -> tuple[TaskProfile, ...]:
        return tuple(
            profile
            for (project, repository, _), profile in self._profiles.items()
            if project == project_id and repository == repository_id
        )

    def get(self, project_id: str, repository_id: str, task_id: str) -> TaskProfile:
        profile = self._profiles.get((project_id, repository_id, task_id))
        if profile is None:
            raise BridgeError(
                ErrorCode.TASK_NOT_FOUND,
                "Task profile is not registered for the repository",
                details={
                    "project_id": project_id,
                    "repository_id": repository_id,
                    "task_id": task_id,
                },
            )
        return profile

    def __bool__(self) -> bool:
        return bool(self._profiles)
