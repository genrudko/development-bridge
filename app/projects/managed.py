from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
import unicodedata
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
REFERENCE_CAPABILITIES = CapabilitySet.from_mapping(
    {"read": True, "git_read": True, "github_contribute": True}
)
FORK_CAPABILITIES = CapabilitySet.from_mapping(
    {"read": True, "write": True, "git_read": True, "git_write": True, "execute": True}
)
MANAGED_KINDS = {"reference": REFERENCE_CAPABILITIES, "fork": FORK_CAPABILITIES}


class ManagedCloneRunner(Protocol):
    async def clone(
        self, url: str, destination: Path, depth: int, requested_ref: str | None
    ) -> None: ...

    async def inspect(self, repository: Path) -> tuple[str, str]: ...

    async def is_clean(self, repository: Path) -> bool: ...

    async def configure_fork(
        self, repository: Path, push_url: str, upstream_url: str
    ) -> None: ...


class SubprocessManagedCloneRunner:
    def __init__(self, timeout_seconds: float = 300) -> None:
        self.timeout_seconds = timeout_seconds

    async def clone(
        self, url: str, destination: Path, depth: int, requested_ref: str | None
    ) -> None:
        arguments = ["git", "clone", "--depth", str(depth), "--single-branch"]
        if requested_ref is not None:
            arguments.extend(["--branch", requested_ref])
        arguments.extend(["--", url, str(destination)])
        await self._run(*arguments)

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

    async def is_clean(self, repository: Path) -> bool:
        status = await self._run("git", "-C", str(repository), "status", "--porcelain")
        return not status.strip()

    async def configure_fork(
        self, repository: Path, push_url: str, upstream_url: str
    ) -> None:
        await self._run("git", "-C", str(repository), "remote", "set-url", "--push", "origin", push_url)
        await self._run("git", "-C", str(repository), "remote", "add", "upstream", upstream_url)

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
    requested_ref: str | None = None
    kind: str = "reference"
    storage_repository_id: str | None = None

    def as_dict(self) -> dict[str, str | int | None]:
        return {
            "project_id": self.project_id,
            "repository_id": self.repository_id,
            "origin_url": self.origin_url,
            "depth": self.depth,
            "created_at": self.created_at,
            "requested_ref": self.requested_ref,
            "kind": self.kind,
            "storage_repository_id": self.storage_repository_id,
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
        self,
        project_id: str,
        repository_id: str,
        url: str,
        depth: int = 50,
        requested_ref: str | None = None,
        *,
        kind: str = "reference",
        push_url: str | None = None,
        upstream_url: str | None = None,
    ) -> dict:
        self.projects.get(project_id)
        origin_url = self._validate_url(url)
        if isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= 10_000:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT, "Clone depth must be between 1 and 10000"
            )
        requested_ref = self._validate_ref(requested_ref)
        if kind not in MANAGED_KINDS:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Managed repository kind is invalid")
        if kind == "fork":
            if not isinstance(push_url, str) or re.fullmatch(r"git@github\.com:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git", push_url) is None:
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fork push URL is invalid")
            upstream_url = self._validate_url(upstream_url or "")
        elif push_url is not None or upstream_url is not None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Reference clones cannot configure fork remotes")
        async with self._lock:
            key = (project_id, repository_id)
            if self.projects.repositories.is_configured(*key):
                raise self._conflict(project_id, repository_id)
            existing = self._records.get(key)
            if existing is not None:
                if (
                    existing.origin_url != origin_url
                    or existing.requested_ref != requested_ref
                    or existing.kind != kind
                ):
                    raise self._conflict(project_id, repository_id)
                if not self._valid_managed_target(self._record_target(existing)):
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
                await self.runner.clone(origin_url, clone_path, depth, requested_ref)
                if not self._valid_managed_target(clone_path):
                    raise BridgeError(
                        ErrorCode.REPOSITORY_CLONE_FAILED,
                        "Clone did not produce a Git repository",
                    )
                branch, head = await self.runner.inspect(clone_path)
                if kind == "reference":
                    alias = await self._alias_candidate(origin_url, branch, head)
                    if alias is not None:
                        storage_id = alias.storage_repository_id or alias.repository_id
                        record = ManagedRepositoryRecord(
                            project_id, repository_id, origin_url, depth,
                            datetime.now(UTC).isoformat(), requested_ref, kind, storage_id,
                        )
                        updated = {**self._records, key: record}
                        self._write_manifest(updated)
                        self.projects.repositories.register_managed(self._repository(record))
                        self._records = updated
                        return self._metadata_dict(record, "aliased", branch, head)
                if kind == "fork":
                    assert push_url is not None and upstream_url is not None
                    await self.runner.configure_fork(clone_path, push_url, upstream_url)
                os.replace(clone_path, target)
                installed = True
                record = ManagedRepositoryRecord(
                    project_id,
                    repository_id,
                    origin_url,
                    depth,
                    datetime.now(UTC).isoformat(),
                    requested_ref,
                    kind,
                    None,
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
                old_keys = {
                    "project_id", "repository_id", "origin_url", "depth", "created_at"
                }
                allowed = {*old_keys, "requested_ref", "kind", "storage_repository_id"}
                if not isinstance(entry, dict) or not old_keys <= set(entry) or not set(entry) <= allowed:
                    raise ValueError("invalid entry shape")
                record = ManagedRepositoryRecord(
                    **entry,
                    **({"requested_ref": None} if "requested_ref" not in entry else {}),
                    **({"kind": "reference"} if "kind" not in entry else {}),
                    **({"storage_repository_id": None} if "storage_repository_id" not in entry else {}),
                )
                self._validate_record(record)
                key = (record.project_id, record.repository_id)
                if key in records or self.projects.repositories.is_configured(*key):
                    raise ValueError("repository collision")
                records[key] = record
            for key, record in records.items():
                storage_id = record.storage_repository_id
                if storage_id is not None:
                    target_record = records.get((record.project_id, storage_id))
                    if (
                        storage_id == record.repository_id
                        or target_record is None
                        or target_record.storage_repository_id is not None
                        or target_record.kind != "reference"
                        or record.kind != "reference"
                        or target_record.origin_url != record.origin_url
                    ):
                        raise ValueError("invalid managed repository storage alias")
                if not self._valid_managed_target(self._record_target(record)):
                    raise ValueError("repository directory missing")
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
        self._validate_ref(record.requested_ref)
        if record.kind not in MANAGED_KINDS:
            raise ValueError("invalid managed repository kind")
        if record.storage_repository_id is not None and not IDENTIFIER.fullmatch(record.storage_repository_id):
            raise ValueError("invalid storage repository identifier")

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
    def _validate_ref(requested_ref: str | None) -> str | None:
        if requested_ref is None:
            return None
        forbidden = " ~^:?*[\\"
        if (
            not isinstance(requested_ref, str)
            or not 1 <= len(requested_ref) <= 1024
            or requested_ref.startswith("-")
            or requested_ref in {"@", "."}
            or requested_ref.startswith("/")
            or requested_ref.endswith(("/", "."))
            or ".." in requested_ref
            or "//" in requested_ref
            or "@{" in requested_ref
            or any(character in forbidden for character in requested_ref)
            or any(
                character.isspace()
                or unicodedata.category(character).startswith("C")
                for character in requested_ref
            )
            or any(part.startswith(".") for part in requested_ref.split("/"))
        ):
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "ref must be a safe Git branch or tag name",
            )
        return requested_ref

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

    def _record_target(self, record: ManagedRepositoryRecord) -> Path:
        return self._target(
            record.project_id, record.storage_repository_id or record.repository_id
        )

    async def _alias_candidate(
        self, origin_url: str, branch: str, head: str
    ) -> ManagedRepositoryRecord | None:
        candidates = sorted(
            (
                record for record in self._records.values()
                if record.kind == "reference" and record.origin_url == origin_url
            ),
            key=lambda record: (record.depth, record.created_at),
            reverse=True,
        )
        seen_targets: set[Path] = set()
        for record in candidates:
            target = self._record_target(record)
            if target in seen_targets:
                continue
            seen_targets.add(target)
            try:
                existing_branch, existing_head = await self.runner.inspect(target)
                if (
                    existing_branch == branch
                    and existing_head == head
                    and await self.runner.is_clean(target)
                ):
                    return record
            except (BridgeError, OSError, ValueError):
                continue
        return None

    def _repository(self, record: ManagedRepositoryRecord) -> Repository:
        return Repository(
            record.project_id,
            record.repository_id,
            self._record_target(record),
            MANAGED_KINDS[record.kind],
        )

    async def _metadata(self, record: ManagedRepositoryRecord, status: str) -> dict:
        branch, head = await self.runner.inspect(self._record_target(record))
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
            "requested_ref": record.requested_ref,
            "branch": branch,
            "head": head,
            "depth": record.depth,
            "kind": record.kind,
            "storage_repository_id": record.storage_repository_id or record.repository_id,
            "storage_shared": record.storage_repository_id is not None,
            "capabilities": MANAGED_KINDS[record.kind].as_dict(),
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
