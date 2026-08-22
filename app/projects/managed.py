from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import CapabilitySet

from .models import Repository
from .registry import ProjectRegistry


MANIFEST_MAX_BYTES = 1_048_576
MANIFEST_MAX_REPOSITORIES = 4096
IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
REFERENCE_CAPABILITIES = CapabilitySet.from_mapping({"read": True, "git_read": True})


class ManagedCloneRunner(Protocol):
    async def clone(self, url: str, destination: Path, depth: int) -> None: ...

    async def inspect(self, repository: Path) -> tuple[str, str]: ...


class SubprocessManagedCloneRunner:
    def __init__(self, timeout_seconds: float = 300) -> None:
        self.timeout_seconds = timeout_seconds

    async def clone(self, url: str, destination: Path, depth: int) -> None:
        await self._run(
            "git", "clone", "--depth", str(depth), "--single-branch", "--", url,
            str(destination),
        )

    async def inspect(self, repository: Path) -> tuple[str, str]:
        inside = await self._run(
            "git", "-C", str(repository), "rev-parse", "--is-inside-work-tree"
        )
        if inside.strip() != "true":
            raise BridgeError(
                ErrorCode.REPOSITORY_CLONE_FAILED,
                "Cloned directory is not a Git worktree",
            )
        branch = (await self._run(
            "git", "-C", str(repository), "branch", "--show-current"
        )).strip()
        head = (await self._run(
            "git", "-C", str(repository), "rev-parse", "HEAD"
        )).strip()
        return branch, head

    async def _run(self, *arguments: str) -> str:
        process = await asyncio.create_subprocess_exec(
            *arguments,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.timeout_seconds
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise BridgeError(
                ErrorCode.REPOSITORY_CLONE_FAILED,
                "Git clone operation timed out",
                retryable=True,
            ) from exc
        if process.returncode != 0:
            raise BridgeError(
                ErrorCode.REPOSITORY_CLONE_FAILED,
                "Git clone operation failed",
                retryable=True,
            )
        if len(stdout) + len(stderr) > 1_048_576:
            raise BridgeError(
                ErrorCode.REPOSITORY_CLONE_FAILED,
                "Git clone output exceeded the safety limit",
            )
        return stdout.decode("utf-8", errors="replace")


@dataclass(frozen=True, slots=True)
class ManagedRepositoryRecord:
    project_id: str
    repository_id: str
    origin_url: str
    depth: int
    created_at: str

    def as_dict(self) -> dict[str, str | int]:
        return {
            "project_id": self.project_id,
            "repository_id": self.repository_id,
            "origin_url": self.origin_url,
            "depth": self.depth,
            "created_at": self.created_at,
        }


class ManagedRepositoryService:
    def __init__(
        self,
        root: Path,
        projects: ProjectRegistry,
        runner: ManagedCloneRunner | None = None,
    ) -> None:
        self.root = root.expanduser().resolve()
        self.manifest_path = self.root / "manifest.json"
        self.projects = projects
        self.runner = runner or SubprocessManagedCloneRunner()
        self._records: dict[tuple[str, str], ManagedRepositoryRecord] = {}
        self._lock = asyncio.Lock()
        self._load()

    async def clone(
        self, project_id: str, repository_id: str, url: str, depth: int = 50
    ) -> dict:
        self.projects.get(project_id)
        origin_url = self._validate_url(url)
        if isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= 10_000:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT, "Clone depth must be between 1 and 10000"
            )
        async with self._lock:
            key = (project_id, repository_id)
            if self.projects.repositories.is_configured(*key):
                raise self._conflict(project_id, repository_id)
            existing = self._records.get(key)
            if existing is not None:
                if existing.origin_url != origin_url:
                    raise self._conflict(project_id, repository_id)
                if not self._valid_managed_target(self._target(*key)):
                    raise BridgeError(
                        ErrorCode.MANAGED_REPOSITORY_STATE_CORRUPT,
                        "Managed repository directory is invalid",
                        details={
                            "project_id": project_id,
                            "repository_id": repository_id,
                        },
                    )
                return await self._metadata(existing, "already_present")

            target = self._target(project_id, repository_id)
            if target.exists():
                raise BridgeError(
                    ErrorCode.MANAGED_REPOSITORY_STATE_CORRUPT,
                    "Managed repository directory is not recorded in the manifest",
                    details={"project_id": project_id, "repository_id": repository_id},
                )

            target.parent.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix=".clone-", dir=target.parent))
            clone_path = staging / "repository"
            installed = False
            try:
                await self.runner.clone(origin_url, clone_path, depth)
                if not self._valid_managed_target(clone_path):
                    raise BridgeError(
                        ErrorCode.REPOSITORY_CLONE_FAILED,
                        "Clone did not produce a Git repository",
                    )
                branch, head = await self.runner.inspect(clone_path)
                os.replace(clone_path, target)
                installed = True
                record = ManagedRepositoryRecord(
                    project_id,
                    repository_id,
                    origin_url,
                    depth,
                    datetime.now(UTC).isoformat(),
                )
                updated = {**self._records, key: record}
                self._write_manifest(updated)
                self.projects.repositories.register_managed(self._repository(record))
                self._records = updated
                return self._metadata_dict(record, "cloned", branch, head)
            except BridgeError:
                if installed and target.exists():
                    shutil.rmtree(target)
                raise
            except (OSError, ValueError) as exc:
                if installed and target.exists():
                    shutil.rmtree(target)
                raise BridgeError(
                    ErrorCode.REPOSITORY_CLONE_FAILED,
                    "Managed repository clone could not be completed",
                ) from exc
            finally:
                shutil.rmtree(staging, ignore_errors=True)

    def _load(self) -> None:
        if not self.manifest_path.exists():
            return
        try:
            if self.manifest_path.stat().st_size > MANIFEST_MAX_BYTES:
                raise ValueError("manifest too large")
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            entries = payload["repositories"]
            if set(payload) != {"repositories"} or not isinstance(entries, list):
                raise ValueError("invalid manifest shape")
            if len(entries) > MANIFEST_MAX_REPOSITORIES:
                raise ValueError("too many entries")
            records: dict[tuple[str, str], ManagedRepositoryRecord] = {}
            for entry in entries:
                if not isinstance(entry, dict) or set(entry) != {
                    "project_id", "repository_id", "origin_url", "depth", "created_at"
                }:
                    raise ValueError("invalid entry shape")
                record = ManagedRepositoryRecord(**entry)
                self._validate_record(record)
                key = (record.project_id, record.repository_id)
                if key in records or self.projects.repositories.is_configured(*key):
                    raise ValueError("repository collision")
                target = self._target(*key)
                if not self._valid_managed_target(target):
                    raise ValueError("repository directory missing")
                records[key] = record
        except (BridgeError, OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise BridgeError(
                ErrorCode.MANAGED_REPOSITORY_STATE_CORRUPT,
                "Managed repository manifest is invalid",
            ) from exc
        for record in records.values():
            self.projects.repositories.register_managed(self._repository(record))
        self._records = records

    def _validate_record(self, record: ManagedRepositoryRecord) -> None:
        self.projects.get(record.project_id)
        if not IDENTIFIER.fullmatch(record.project_id) or not IDENTIFIER.fullmatch(
            record.repository_id
        ):
            raise ValueError("invalid identifier")
        self._validate_url(record.origin_url)
        if (
            not isinstance(record.depth, int)
            or isinstance(record.depth, bool)
            or not 1 <= record.depth <= 10_000
        ):
            raise ValueError("invalid depth")
        if not isinstance(record.created_at, str) or len(record.created_at) > 100:
            raise ValueError("invalid timestamp")

    @staticmethod
    def _validate_url(url: str) -> str:
        if not isinstance(url, str) or len(url) > 2048:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Repository URL is invalid")
        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Repository URL is invalid") from exc
        if (
            parsed.scheme != "https"
            or hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or not parsed.path
            or port is not None and not 1 <= port <= 65535
            or any(ord(character) < 33 for character in url)
        ):
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "Repository URL must be public HTTPS without credentials, query, or fragment",
            )
        return url

    def _target(self, project_id: str, repository_id: str) -> Path:
        if not IDENTIFIER.fullmatch(project_id) or not IDENTIFIER.fullmatch(repository_id):
            raise ValueError("invalid managed repository identifier")
        return self.root / project_id / repository_id

    @staticmethod
    def _valid_managed_target(target: Path) -> bool:
        git_directory = target / ".git"
        try:
            return (
                target.is_dir()
                and not target.is_symlink()
                and target.resolve(strict=True) == target
                and git_directory.is_dir()
                and not git_directory.is_symlink()
            )
        except OSError:
            return False

    def _repository(self, record: ManagedRepositoryRecord) -> Repository:
        return Repository(
            record.project_id,
            record.repository_id,
            self._target(record.project_id, record.repository_id),
            REFERENCE_CAPABILITIES,
        )

    async def _metadata(self, record: ManagedRepositoryRecord, status: str) -> dict:
        branch, head = await self.runner.inspect(
            self._target(record.project_id, record.repository_id)
        )
        return self._metadata_dict(record, status, branch, head)

    @staticmethod
    def _metadata_dict(
        record: ManagedRepositoryRecord, status: str, branch: str, head: str
    ) -> dict:
        return {
            "status": status,
            "project_id": record.project_id,
            "repository_id": record.repository_id,
            "origin_url": record.origin_url,
            "branch": branch,
            "head": head,
            "depth": record.depth,
            "capabilities": REFERENCE_CAPABILITIES.as_dict(),
        }

    def _write_manifest(
        self, records: dict[tuple[str, str], ManagedRepositoryRecord]
    ) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"repositories": [record.as_dict() for record in records.values()]},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        temporary = self.root / f".manifest-{os.getpid()}-{id(records)}.tmp"
        try:
            with temporary.open("xb") as file:
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.manifest_path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _conflict(project_id: str, repository_id: str) -> BridgeError:
        return BridgeError(
            ErrorCode.REPOSITORY_CONFLICT,
            "Repository identifier is already in use",
            details={"project_id": project_id, "repository_id": repository_id},
        )
