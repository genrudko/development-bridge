from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import Capability, CapabilityPolicy
from app.projects import Repository, RepositoryMutationLock

from .models import ChangeApplyResult, ChangeOperation, ChangePlan
from .revision import ChangeRevisionCalculator


class ChangeService:
    MAX_OPERATIONS = 100
    MAX_FILE_BYTES = 1024 * 1024
    MAX_PLAN_BYTES = 4 * 1024 * 1024

    def __init__(
        self,
        policy: CapabilityPolicy,
        revisions: ChangeRevisionCalculator,
        mutations: RepositoryMutationLock | None = None,
    ) -> None:
        self._policy = policy
        self._revisions = revisions
        self._mutations = mutations or RepositoryMutationLock()

    async def plan(
        self,
        repository: Repository,
        operations: Sequence[Mapping[str, Any]],
        *,
        base_revision: str | None = None,
    ) -> ChangePlan:
        self._require_write(repository)
        current_revision = await self._revisions.calculate(repository)
        if base_revision is not None and base_revision != current_revision:
            raise self._revision_conflict(base_revision, current_revision)
        normalized = self._normalize_operations(repository, operations)
        tracked = await self._revisions.tracked_paths(repository)
        self._check_preconditions(repository, normalized, tracked)
        return self._build_plan(repository, current_revision, normalized)

    async def apply(
        self,
        repository: Repository,
        *,
        plan_id: str,
        base_revision: str,
        operations: Sequence[Mapping[str, Any]],
    ) -> ChangeApplyResult:
        self._require_write(repository)
        normalized = self._normalize_operations(repository, operations)
        plan = self._build_plan(repository, base_revision, normalized)
        if plan.plan_id != plan_id:
            raise BridgeError(
                ErrorCode.CHANGE_PLAN_INVALID,
                "plan_id does not match the normalized plan",
                details={"plan_id": plan_id},
            )
        async with self._mutations.acquire(repository):
            receipt = self._receipt_path(repository, plan_id)
            if receipt.exists():
                self._verify_final_state(repository, normalized)
                return ChangeApplyResult(
                    "already_applied",
                    plan_id,
                    await self._revisions.calculate(repository),
                    0,
                )

            current_revision = await self._revisions.calculate(repository)
            if current_revision != base_revision:
                raise self._revision_conflict(base_revision, current_revision)
            tracked = await self._revisions.tracked_paths(repository)
            self._check_preconditions(repository, normalized, tracked)
            applied = 0
            try:
                for operation in normalized:
                    self._apply_operation(repository, operation)
                    applied += 1
                self._verify_final_state(repository, normalized)
            except BridgeError:
                raise
            except OSError as exc:
                raise BridgeError(
                    ErrorCode.CHANGE_APPLY_FAILED,
                    "Change plan could not be fully applied",
                    details={"operations_applied": applied},
                ) from exc
            revision = await self._revisions.calculate(repository)
            try:
                self._write_receipt(receipt, plan, revision)
            except OSError as exc:
                raise BridgeError(
                    ErrorCode.CHANGE_APPLY_FAILED,
                    "Change receipt could not be persisted",
                    details={"operations_applied": len(normalized)},
                ) from exc
            return ChangeApplyResult(
                "applied",
                plan_id,
                revision,
                len(normalized),
                previous_revision=base_revision,
            )

    def _normalize_operations(
        self,
        repository: Repository,
        operations: Sequence[Mapping[str, Any]],
    ) -> tuple[ChangeOperation, ...]:
        if isinstance(operations, (str, bytes)) or not isinstance(operations, Sequence):
            raise self._plan_error("operations must be an array")
        if not 1 <= len(operations) <= self.MAX_OPERATIONS:
            raise self._plan_error(
                "operation count is outside the allowed range",
                maximum=self.MAX_OPERATIONS,
            )
        normalized = []
        occupied: set[str] = set()
        total_bytes = 0
        for index, raw in enumerate(operations):
            if not isinstance(raw, Mapping):
                raise self._plan_error("operation must be an object", operation=index)
            kind = raw.get("type")
            allowed = {
                "create": {"type", "path", "content"},
                "update": {"type", "path", "content", "expected_sha256"},
                "delete": {"type", "path", "expected_sha256"},
                "rename": {"type", "source", "destination", "expected_sha256"},
            }
            if kind not in allowed:
                raise self._plan_error("unknown change operation", operation=index)
            extras = set(raw) - allowed[kind]
            if extras:
                raise self._plan_error(
                    "operation contains unknown fields", operation=index
                )
            if kind == "rename":
                source = self._normalize_path(repository, raw.get("source"), index)
                destination = self._normalize_path(
                    repository, raw.get("destination"), index
                )
                paths = (source, destination)
                operation = ChangeOperation(
                    kind,
                    source=source,
                    destination=destination,
                    expected_sha256=self._normalize_hash(
                        raw.get("expected_sha256"), index
                    ),
                )
            else:
                path = self._normalize_path(repository, raw.get("path"), index)
                paths = (path,)
                content = None
                if kind in {"create", "update"}:
                    content = raw.get("content")
                    if not isinstance(content, str) or "\0" in content:
                        raise self._plan_error(
                            "content must be UTF-8 text without NUL", operation=index
                        )
                    size = len(content.encode("utf-8"))
                    if size > self.MAX_FILE_BYTES:
                        raise self._plan_error(
                            "file content exceeds the size limit",
                            operation=index,
                            limit=self.MAX_FILE_BYTES,
                        )
                    total_bytes += size
                expected = (
                    self._normalize_hash(raw.get("expected_sha256"), index)
                    if kind in {"update", "delete"}
                    else None
                )
                operation = ChangeOperation(kind, path=path, content=content, expected_sha256=expected)
            if any(path in occupied for path in paths):
                raise self._plan_error(
                    "a path may participate in only one operation", operation=index
                )
            occupied.update(paths)
            normalized.append(operation)
        if total_bytes > self.MAX_PLAN_BYTES:
            raise self._plan_error(
                "plan content exceeds the size limit", limit=self.MAX_PLAN_BYTES
            )
        return tuple(normalized)

    def _normalize_path(
        self, repository: Repository, value: Any, operation: int
    ) -> str:
        if not isinstance(value, str) or not value or "\0" in value:
            raise self._plan_error("path must be a non-empty string", operation=operation)
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or not path.parts
            or path.as_posix() == "."
            or ".." in path.parts
            or path.parts[0] == ".git"
        ):
            raise self._plan_error("path is outside the repository boundary", operation=operation)
        normalized = path.as_posix()
        target = repository.root.joinpath(*path.parts)
        current = repository.root
        for part in path.parts:
            current /= part
            if current.is_symlink():
                raise self._plan_error("symbolic links cannot be followed", operation=operation)
        parent = target.parent
        if not parent.is_dir():
            raise self._plan_error("parent directory does not exist", operation=operation)
        return normalized

    @staticmethod
    def _normalize_hash(value: Any, operation: int) -> str:
        if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
            raise ChangeService._plan_error(
                "expected_sha256 must be a SHA-256 digest", operation=operation
            )
        try:
            int(value[7:], 16)
        except ValueError as exc:
            raise ChangeService._plan_error(
                "expected_sha256 must be a SHA-256 digest", operation=operation
            ) from exc
        return value.lower()

    def _check_preconditions(
        self,
        repository: Repository,
        operations: tuple[ChangeOperation, ...],
        tracked: frozenset[str],
    ) -> None:
        for index, operation in enumerate(operations):
            if operation.type == "create":
                if self._path(repository, operation.path).exists():
                    raise self._precondition("create target already exists", index, operation.path)
            elif operation.type in {"update", "delete"}:
                self._require_tracked(operation.path, tracked, index)
                self._require_hash(repository, operation.path, operation.expected_sha256, index)
            else:
                self._require_tracked(operation.source, tracked, index)
                self._require_hash(repository, operation.source, operation.expected_sha256, index)
                if self._path(repository, operation.destination).exists():
                    raise self._precondition(
                        "rename destination already exists", index, operation.destination
                    )

    @staticmethod
    def _require_tracked(
        path: str | None, tracked: frozenset[str], operation: int
    ) -> None:
        if path not in tracked:
            raise BridgeError(
                ErrorCode.CHANGE_PRECONDITION_FAILED,
                "Destructive changes require a tracked file",
                details={"operation": operation, "path": path},
            )

    def _apply_operation(
        self, repository: Repository, operation: ChangeOperation
    ) -> None:
        if operation.type in {"create", "update"}:
            target = self._path(repository, operation.path)
            mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
            self._atomic_write(target, operation.content, mode)
        elif operation.type == "delete":
            self._path(repository, operation.path).unlink()
        else:
            os.replace(
                self._path(repository, operation.source),
                self._path(repository, operation.destination),
            )

    def _verify_final_state(
        self, repository: Repository, operations: tuple[ChangeOperation, ...]
    ) -> None:
        for index, operation in enumerate(operations):
            if operation.type in {"create", "update"}:
                expected = self._content_hash(operation.content)
                self._require_hash(repository, operation.path, expected, index)
            elif operation.type == "delete":
                if self._path(repository, operation.path).exists():
                    raise self._precondition("deleted path still exists", index, operation.path)
            else:
                if self._path(repository, operation.source).exists():
                    raise self._precondition("rename source still exists", index, operation.source)
                self._require_hash(
                    repository, operation.destination, operation.expected_sha256, index
                )

    def _require_hash(
        self,
        repository: Repository,
        path: str | None,
        expected: str | None,
        operation: int,
    ) -> None:
        target = self._path(repository, path)
        if target.is_symlink() or not target.is_file():
            raise self._precondition("expected regular file does not exist", operation, path)
        actual = self._file_hash(target)
        if actual != expected:
            raise BridgeError(
                ErrorCode.CHANGE_PRECONDITION_FAILED,
                "File content does not match the change plan",
                details={
                    "operation": operation,
                    "path": path,
                    "expected_sha256": expected,
                    "actual_sha256": actual,
                },
            )

    def _build_plan(
        self,
        repository: Repository,
        base_revision: str,
        operations: tuple[ChangeOperation, ...],
    ) -> ChangePlan:
        payload = {
            "project_id": repository.project_id,
            "repository_id": repository.id,
            "base_revision": base_revision,
            "operations": [operation.as_dict() for operation in operations],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        plan_id = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return ChangePlan(
            repository.project_id,
            repository.id,
            plan_id,
            base_revision,
            operations,
        )

    @staticmethod
    def _atomic_write(target: Path, content: str | None, mode: int) -> None:
        descriptor, temporary = tempfile.mkstemp(prefix=".bridge-change-", dir=target.parent)
        try:
            os.fchmod(descriptor, mode)
            with os.fdopen(descriptor, "wb") as destination:
                destination.write((content or "").encode("utf-8"))
                destination.flush()
                os.fsync(destination.fileno())
            os.replace(temporary, target)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise

    @staticmethod
    def _path(repository: Repository, path: str | None) -> Path:
        assert path is not None
        return repository.root.joinpath(*PurePosixPath(path).parts)

    @staticmethod
    def _file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(64 * 1024):
                digest.update(chunk)
        return "sha256:" + digest.hexdigest()

    @staticmethod
    def _content_hash(content: str | None) -> str:
        return "sha256:" + hashlib.sha256((content or "").encode("utf-8")).hexdigest()

    @staticmethod
    def _receipt_path(repository: Repository, plan_id: str) -> Path:
        identifier = plan_id.removeprefix("sha256:")
        return repository.root / ".git" / "development-bridge" / "receipts" / f"{identifier}.json"

    @staticmethod
    def _write_receipt(path: Path, plan: ChangePlan, revision: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"plan_id": plan.plan_id, "revision": revision},
            sort_keys=True,
            separators=(",", ":"),
        )
        descriptor, temporary = tempfile.mkstemp(prefix=".receipt-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as receipt:
                receipt.write(payload)
                receipt.flush()
                os.fsync(receipt.fileno())
            os.replace(temporary, path)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise

    def _require_write(self, repository: Repository) -> None:
        self._policy.require(
            repository.capabilities,
            Capability.WRITE,
            project_id=repository.project_id,
            repository_id=repository.id,
        )

    @staticmethod
    def _revision_conflict(expected: str, actual: str) -> BridgeError:
        return BridgeError(
            ErrorCode.REVISION_CONFLICT,
            "Repository revision does not match the change plan",
            details={"expected_revision": expected, "actual_revision": actual},
        )

    @staticmethod
    def _precondition(message: str, operation: int, path: str | None) -> BridgeError:
        return BridgeError(
            ErrorCode.CHANGE_PRECONDITION_FAILED,
            message,
            details={"operation": operation, "path": path},
        )

    @staticmethod
    def _plan_error(message: str, **details: int) -> BridgeError:
        return BridgeError(ErrorCode.CHANGE_PLAN_INVALID, message, details=details)
