from __future__ import annotations

from dataclasses import dataclass


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

    def public_dict(self) -> dict[str, str | float | int]:
        return {
            "task_id": self.id,
            "name": self.name,
            "timeout_seconds": self.timeout_seconds,
            "output_limit_bytes": self.output_limit_bytes,
        }
