from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import stat
import uuid
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

from app.api.errors import BridgeError, ErrorCode
from app.git.runner import GitRunner
from app.jobs import JobService
from app.projects import Repository

logger = logging.getLogger(__name__)

DEFAULT_OVERLAY_DIR = Path("/home/eodadmin/.local/state/development-bridge/eod-overlay")
MAX_FILES = 64
MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MiB
MAX_TOTAL_BYTES = 8 * 1024 * 1024  # 8 MiB
DEFAULT_TIMEOUT_SECONDS = 180.0
MAX_OUTPUT_BYTES = 65_536
MAX_SUMMARY_CHARS = 2048

ELIGIBLE_PREFIXES = ("src/templates/", "src/static/")


def _bound_text(text: str, max_chars: int = MAX_SUMMARY_CHARS) -> str:
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[-max_chars:]


def _validate_canonical_path(p: Any) -> str:
    if not isinstance(p, str) or not p:
        raise BridgeError(
            ErrorCode.INVALID_ARGUMENT,
            "Explicit paths must contain non-empty strings",
        )
    if "\\" in p or "\0" in p or "//" in p or p.startswith("/") or p.startswith("./") or p.startswith("../"):
        raise BridgeError(
            ErrorCode.INVALID_ARGUMENT,
            f"Explicit path is not canonical: {p}",
        )
    parts = p.split("/")
    if any(part in (".", "..", "") for part in parts):
        raise BridgeError(
            ErrorCode.INVALID_ARGUMENT,
            f"Explicit path contains non-canonical segments: {p}",
        )
    if not any(p.startswith(prefix) for prefix in ELIGIBLE_PREFIXES):
        raise BridgeError(
            ErrorCode.INVALID_ARGUMENT,
            f"Explicit path must be under canonical src/templates/ or src/static/: {p}",
        )
    return p


class EodDevelopmentOverlayService:
    def __init__(
        self,
        jobs: JobService,
        git_runner: GitRunner,
        *,
        overlay_dir: Path | str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        spawn: Callable[..., Awaitable[Any]] = asyncio.create_subprocess_exec,
    ) -> None:
        self._jobs = jobs
        self._git_runner = git_runner
        self._overlay_dir = Path(overlay_dir).expanduser() if overlay_dir else DEFAULT_OVERLAY_DIR
        self._timeout_seconds = timeout_seconds
        self._spawn = spawn

    async def apply(
        self,
        repository: Repository,
        paths: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        self._validate_repository(repository)

        async def _do_apply() -> dict[str, Any]:
            eligible_files = await self._discover_dirty_eligible_files(repository)
            selected_paths = self._filter_and_validate_paths(eligible_files, paths)

            if not selected_paths:
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    "No eligible dirty template or static files found to apply",
                    details={"project_id": repository.project_id, "repository_id": repository.id},
                )

            if len(selected_paths) > MAX_FILES:
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    f"Overlay file count ({len(selected_paths)}) exceeds maximum limit of {MAX_FILES}",
                    details={"file_count": len(selected_paths), "limit": MAX_FILES},
                )

            file_records, total_bytes = self._snapshot_files(repository, selected_paths)

            run_id = f"overlay-{uuid.uuid4().hex}"
            bundle_payload = {
                "version": 1,
                "run_id": run_id,
                "files": file_records,
            }

            self._prepare_overlay_dir()
            tmp_path = self._overlay_dir / f".bundle-{run_id}.tmp"
            bundle_path = self._overlay_dir / f"bundle-{run_id}.json"

            try:
                bundle_json = json.dumps(bundle_payload, indent=2).encode("utf-8")
                fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                try:
                    os.write(fd, bundle_json)
                finally:
                    os.close(fd)
                os.chmod(tmp_path, 0o600)
                os.replace(tmp_path, bundle_path)
                os.chmod(bundle_path, 0o600)

                unit_name = f"eod-overlay-{run_id}"
                cmd = (
                    "/usr/bin/systemd-run",
                    "--user",
                    f"--unit={unit_name}",
                    "--wait",
                    "--pipe",
                    "--collect",
                    f"--property=RuntimeMaxSec={int(self._timeout_seconds)}s",
                    "/usr/bin/sudo",
                    "-n",
                    "/usr/local/sbin/eod-development-controller",
                    "local-hot-refresh",
                    str(bundle_path),
                    run_id,
                )
                exit_code, stdout, stderr = await self._run_trampoline(cmd, unit_name=unit_name)
                return {
                    "run_id": run_id,
                    "applied_files": [f["path"] for f in file_records],
                    "file_count": len(file_records),
                    "total_bytes": total_bytes,
                    "exit_code": exit_code,
                    "stdout": _bound_text(stdout),
                    "stderr": _bound_text(stderr),
                }
            finally:
                if bundle_path.exists():
                    try:
                        bundle_path.unlink()
                    except OSError:
                        pass
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass

        return await self._jobs.run_when_repository_idle(
            repository, _do_apply, operation_name="eod_development_overlay_apply"
        )

    async def rollback(self, repository: Repository) -> dict[str, Any]:
        self._validate_repository(repository)

        async def _do_rollback() -> dict[str, Any]:
            unit_name = f"eod-overlay-rollback-{uuid.uuid4().hex}"
            cmd = (
                "/usr/bin/systemd-run",
                "--user",
                f"--unit={unit_name}",
                "--wait",
                "--pipe",
                "--collect",
                f"--property=RuntimeMaxSec={int(self._timeout_seconds)}s",
                "/usr/bin/sudo",
                "-n",
                "/usr/local/sbin/eod-development-controller",
                "local-hot-refresh-clear",
            )
            exit_code, stdout, stderr = await self._run_trampoline(cmd, unit_name=unit_name)
            return {
                "cleared": True,
                "exit_code": exit_code,
                "stdout": _bound_text(stdout),
                "stderr": _bound_text(stderr),
            }

        return await self._jobs.run_when_repository_idle(
            repository, _do_rollback, operation_name="eod_development_overlay_rollback"
        )

    def _validate_repository(self, repository: Repository) -> None:
        if repository.project_id != "eod" or repository.id != "eod":
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                "Development overlay is only supported on project 'eod' and repository 'eod'",
                details={"project_id": repository.project_id, "repository_id": repository.id},
            )

    def _prepare_overlay_dir(self) -> Path:
        if os.path.islink(self._overlay_dir):
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                f"Overlay inbox directory is a symlink: {self._overlay_dir}",
                details={"overlay_dir": str(self._overlay_dir)},
            )
        if self._overlay_dir.exists():
            if not self._overlay_dir.is_dir():
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    f"Overlay inbox is not a directory: {self._overlay_dir}",
                    details={"overlay_dir": str(self._overlay_dir)},
                )
            try:
                os.chmod(self._overlay_dir, 0o700)
            except OSError as exc:
                raise BridgeError(
                    ErrorCode.INTERNAL_ERROR,
                    f"Failed to set overlay directory permissions: {exc}",
                ) from exc
        else:
            try:
                self._overlay_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
                os.chmod(self._overlay_dir, 0o700)
            except OSError as exc:
                raise BridgeError(
                    ErrorCode.INTERNAL_ERROR,
                    f"Failed to create overlay directory: {exc}",
                ) from exc
        return self._overlay_dir

    async def _discover_dirty_eligible_files(self, repository: Repository) -> set[str]:
        result = await self._git_runner.run(
            repository,
            ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        )
        tokens = result.stdout.split("\0")
        eligible_dirty: set[str] = set()

        idx = 0
        while idx < len(tokens):
            token = tokens[idx]
            if not token:
                idx += 1
                continue
            if len(token) < 3:
                idx += 1
                continue
            code = token[:2]
            raw_path = token[3:]

            if "R" in code or "C" in code:
                idx += 1
                orig_path = tokens[idx] if idx < len(tokens) else ""
                if any(raw_path.startswith(p) for p in ELIGIBLE_PREFIXES) or any(orig_path.startswith(p) for p in ELIGIBLE_PREFIXES):
                    raise BridgeError(
                        ErrorCode.POLICY_VIOLATION,
                        f"Eligible file rename is not supported in overlay: {raw_path}",
                        details={"path": raw_path, "orig_path": orig_path, "status": code},
                    )
                idx += 1
                continue

            is_eligible = any(raw_path.startswith(p) for p in ELIGIBLE_PREFIXES)
            if not is_eligible:
                idx += 1
                continue

            # Fail closed on eligible deletion, rename, type-change, conflict
            if "D" in code:
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    f"Eligible file deletion is not supported in overlay: {raw_path}",
                    details={"path": raw_path, "status": code},
                )
            if "T" in code:
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    f"Eligible file type-change is not supported in overlay: {raw_path}",
                    details={"path": raw_path, "status": code},
                )
            if "U" in code or code in ("AA", "DD", "UU", "DU", "UD", "AU", "UA"):
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    f"Eligible file conflict is not supported in overlay: {raw_path}",
                    details={"path": raw_path, "status": code},
                )
            if not all(c in "AM? " for c in code):
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    f"Eligible file status '{code}' is not supported in overlay: {raw_path}",
                    details={"path": raw_path, "status": code},
                )

            eligible_dirty.add(raw_path)
            idx += 1

        return eligible_dirty

    def _filter_and_validate_paths(
        self,
        eligible_dirty: set[str],
        explicit_paths: Sequence[str] | None,
    ) -> list[str]:
        if explicit_paths is None:
            return sorted(eligible_dirty)

        seen: set[str] = set()
        validated: list[str] = []
        for p in explicit_paths:
            canonical_p = _validate_canonical_path(p)
            if canonical_p in seen:
                raise BridgeError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"Duplicate path in explicit paths list: {p}",
                )
            seen.add(canonical_p)

            if canonical_p not in eligible_dirty:
                raise BridgeError(
                    ErrorCode.CHANGE_PRECONDITION_FAILED,
                    f"Explicit path is not dirty or does not exist: {p}",
                    details={"path": p},
                )
            validated.append(canonical_p)

        return validated

    def _snapshot_files(
        self,
        repository: Repository,
        rel_paths: Sequence[str],
    ) -> tuple[list[dict[str, str]], int]:
        file_records: list[dict[str, str]] = []
        total_bytes = 0
        repo_root = repository.root.resolve()

        for rel_path in rel_paths:
            # Check every parent component and the leaf for symlinks
            parts = rel_path.split("/")
            curr = repo_root
            for part in parts:
                curr = curr / part
                if curr.is_symlink() or os.path.islink(curr):
                    raise BridgeError(
                        ErrorCode.POLICY_VIOLATION,
                        f"Symlink rejected in overlay path: {rel_path}",
                        details={"path": rel_path},
                    )

            full_path = curr
            resolved = full_path.resolve()
            if not resolved.is_relative_to(repo_root):
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    f"Overlay path resolves outside repository root: {rel_path}",
                    details={"path": rel_path},
                )
            resolved_rel = resolved.relative_to(repo_root).as_posix()
            if not any(resolved_rel.startswith(p) for p in ELIGIBLE_PREFIXES):
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    f"Resolved overlay path is not under eligible prefixes: {rel_path}",
                    details={"path": rel_path, "resolved": resolved_rel},
                )

            # Open and inspect regular file identity
            try:
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(str(full_path), flags)
            except OSError as exc:
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION if isinstance(exc, (PermissionError, FileNotFoundError)) else ErrorCode.INTERNAL_ERROR,
                    f"Could not open overlay file {rel_path}: {exc}",
                    details={"path": rel_path},
                ) from exc

            try:
                st = os.fstat(fd)
                if not stat.S_ISREG(st.st_mode):
                    raise BridgeError(
                        ErrorCode.POLICY_VIOLATION,
                        f"Not a regular file: {rel_path}",
                        details={"path": rel_path},
                    )
                if st.st_size > MAX_FILE_BYTES:
                    raise BridgeError(
                        ErrorCode.POLICY_VIOLATION,
                        f"File {rel_path} exceeds maximum size of 2 MiB ({st.st_size} bytes)",
                        details={"path": rel_path, "bytes": st.st_size, "limit": MAX_FILE_BYTES},
                    )
                data = os.read(fd, MAX_FILE_BYTES + 1)
                if len(data) > MAX_FILE_BYTES:
                    raise BridgeError(
                        ErrorCode.POLICY_VIOLATION,
                        f"File {rel_path} exceeds maximum size of 2 MiB",
                        details={"path": rel_path, "limit": MAX_FILE_BYTES},
                    )
            finally:
                os.close(fd)

            size = len(data)
            total_bytes += size
            if total_bytes > MAX_TOTAL_BYTES:
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    f"Overlay exceeds maximum total size of 8 MiB ({total_bytes} bytes)",
                    details={"total_bytes": total_bytes, "limit": MAX_TOTAL_BYTES},
                )

            sha256 = hashlib.sha256(data).hexdigest()
            b64_content = base64.b64encode(data).decode("ascii")
            file_records.append({
                "path": rel_path,
                "content": b64_content,
                "sha256": sha256,
            })

        return file_records, total_bytes

    @staticmethod
    async def _read_bounded(stream: Any, limit: int) -> tuple[bytes, bool]:
        output = bytearray()
        truncated = False
        while chunk := await stream.read(8192):
            remaining = max(0, limit - len(output))
            output.extend(chunk[:remaining])
            truncated = truncated or len(chunk) > remaining
        return bytes(output), truncated

    async def _run_trampoline(
        self,
        command: tuple[str, ...],
        *,
        unit_name: str,
    ) -> tuple[int, str, str]:
        runtime_dir = f"/run/user/{os.getuid()}"
        env = {
            "XDG_RUNTIME_DIR": runtime_dir,
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path={runtime_dir}/bus",
        }
        try:
            process = await self._spawn(
                *command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except OSError as exc:
            raise BridgeError(
                ErrorCode.INTERNAL_ERROR,
                f"Failed to spawn user-systemd trampoline: {exc}",
            ) from exc

        stdout_task = asyncio.create_task(self._read_bounded(process.stdout, MAX_OUTPUT_BYTES))
        stderr_task = asyncio.create_task(self._read_bounded(process.stderr, MAX_OUTPUT_BYTES))
        try:
            await asyncio.wait_for(process.wait(), timeout=self._timeout_seconds)
        except TimeoutError as exc:
            process.kill()
            await process.wait()

            # Stop transient user unit on timeout before returning
            stop_cmd = (
                "/usr/bin/systemctl",
                "--user",
                "stop",
                unit_name,
            )
            try:
                stop_process = await self._spawn(
                    *stop_cmd,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
                await asyncio.wait_for(stop_process.wait(), timeout=5.0)
            except Exception as stop_exc:
                logger.warning("Failed to stop transient unit %s: %s", unit_name, stop_exc)

            stdout_bytes, _ = await stdout_task
            stderr_bytes, _ = await stderr_task
            raise BridgeError(
                ErrorCode.INTERNAL_ERROR,
                f"Development overlay controller timed out after {int(self._timeout_seconds)}s",
                details={
                    "unit": unit_name,
                    "stdout": _bound_text(stdout_bytes.decode("utf-8", errors="replace")),
                    "stderr": _bound_text(stderr_bytes.decode("utf-8", errors="replace")),
                },
            ) from exc

        stdout_bytes, _ = await stdout_task
        stderr_bytes, _ = await stderr_task
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        if process.returncode != 0:
            combined = (stderr + " " + stdout).lower()
            if "sudo:" in combined or "password is required" in combined or "permission denied" in combined:
                raise BridgeError(
                    ErrorCode.PERMISSION_DENIED,
                    f"Sudo authentication or bootstrap missing for overlay controller: {stderr.strip() or stdout.strip()}",
                    details={"exit_code": process.returncode, "stderr": _bound_text(stderr), "stdout": _bound_text(stdout)},
                )
            raise BridgeError(
                ErrorCode.INTERNAL_ERROR,
                f"Development overlay controller failed (exit {process.returncode}): {stderr.strip() or stdout.strip()}",
                details={"exit_code": process.returncode, "stderr": _bound_text(stderr), "stdout": _bound_text(stdout)},
            )

        return process.returncode, stdout, stderr

