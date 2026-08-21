from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ChangeOperation:
    type: str
    path: str | None = None
    source: str | None = None
    destination: str | None = None
    content: str | None = None
    expected_sha256: str | None = None

    def as_dict(self) -> dict[str, str]:
        return {
            key: value
            for key, value in (
                ("type", self.type),
                ("path", self.path),
                ("source", self.source),
                ("destination", self.destination),
                ("content", self.content),
                ("expected_sha256", self.expected_sha256),
            )
            if value is not None
        }


@dataclass(frozen=True, slots=True)
class ChangePlan:
    project_id: str
    repository_id: str
    plan_id: str
    base_revision: str
    operations: tuple[ChangeOperation, ...]

    def as_dict(self) -> dict[str, Any]:
        summary = {kind: 0 for kind in ("create", "update", "delete", "rename")}
        for operation in self.operations:
            summary[operation.type] += 1
        return {
            "project_id": self.project_id,
            "repository_id": self.repository_id,
            "plan_id": self.plan_id,
            "base_revision": self.base_revision,
            "operations": [operation.as_dict() for operation in self.operations],
            "summary": summary,
        }


@dataclass(frozen=True, slots=True)
class ChangeApplyResult:
    status: str
    plan_id: str
    revision: str
    operations_applied: int
    previous_revision: str | None = None

    def as_dict(self) -> dict[str, str | int]:
        result: dict[str, str | int] = {
            "status": self.status,
            "plan_id": self.plan_id,
            "revision": self.revision,
            "operations_applied": self.operations_applied,
        }
        if self.previous_revision is not None:
            result["previous_revision"] = self.previous_revision
        return result
