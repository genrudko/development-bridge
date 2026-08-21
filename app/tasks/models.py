from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ArtifactDeclaration:
    id: str
    path: str
    media_type: str
    required: bool
    max_bytes: int

    def public_dict(self) -> dict[str, str | bool | int]:
        return {
            "artifact_id": self.id,
            "path": self.path,
            "media_type": self.media_type,
            "required": self.required,
            "max_bytes": self.max_bytes,
        }


@dataclass(frozen=True, slots=True)
class TaskProfile:
    project_id: str
    repository_id: str
    id: str
    name: str
    executable: str
    arguments: tuple[str, ...]
    timeout_seconds: float
    output_limit_bytes: int
    artifacts: tuple[ArtifactDeclaration, ...] = ()

    def public_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.id,
            "name": self.name,
            "timeout_seconds": self.timeout_seconds,
            "output_limit_bytes": self.output_limit_bytes,
            "artifacts": [artifact.public_dict() for artifact in self.artifacts],
        }
