from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import Capability, CapabilityPolicy
from app.projects import Repository, RepositoryMutationLock

from .models import GitCommit
from .runner import GitRunner
from .write_models import GitCommitResult, GitPushPlan, GitPushResult, GitStageResult

if TYPE_CHECKING:
    from app.changes.revision import ChangeRevisionCalculator


class GitWriteService:
    MAX_PATHS = 100
    MAX_MESSAGE_BYTES = 16 * 1024
    MAX_PUSH_COMMITS = 100
    _REMOTE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")

    def __init__(
        self,
        runner: GitRunner,
        policy: CapabilityPolicy,
        revisions: ChangeRevisionCalculator,
        mutations: RepositoryMutationLock,
    ) -> None:
        self._runner = runner
        self._policy = policy
        self._revisions = revisions
        self._mutations = mutations

    async def stage(
        self,
        repository: Repository,
        paths: list[str] | tuple[str, ...],
        *,
        base_revision: str | None = None,
    ) -> GitStageResult:
        self._require_write(repository)
        normalized = self._normalize_paths(paths)
        async with self._mutations.acquire(repository):
            previous = await self._revisions.calculate(repository)
            if base_revision is not None and base_revision != previous:
                raise self._revision_conflict(base_revision, previous)
            await self._ensure_no_operation(repository)
            await self._runner.run(
                repository,
                ["--literal-pathspecs", "add", "-A", "--", *normalized],
            )
            revision = await self._revisions.calculate(repository)
            return GitStageResult(
                "staged",
                previous,
                revision,
                await self._head(repository),
                await self._index_revision(repository),
                normalized,
                await self._staged_file_count(repository),
            )

    async def commit(
        self,
        repository: Repository,
        *,
        message: str,
        idempotency_key: str,
        expected_head: str | None = None,
        expected_index_revision: str | None = None,
    ) -> GitCommitResult:
        self._require_write(repository)
        message = self._normalize_message(message)
        key = self._normalize_key(idempotency_key)
        payload = {
            "message": message,
            "expected_head": expected_head,
            "expected_index_revision": expected_index_revision,
        }
        async with self._mutations.acquire(repository):
            receipt = self._read_receipt(repository, "commit", key, payload)
            if receipt is not None:
                return self._commit_result(receipt, "already_committed")
            await self._ensure_no_operation(repository)
            head = await self._head(repository)
            index_revision = await self._index_revision(repository)
            if expected_head is not None and expected_head != head:
                raise self._revision_conflict(expected_head, head)
            if (
                expected_index_revision is not None
                and expected_index_revision != index_revision
            ):
                raise self._revision_conflict(expected_index_revision, index_revision)
            empty = await self._runner.run(
                repository, ["diff", "--cached", "--quiet"], check=False
            )
            if empty.returncode == 0:
                raise BridgeError(ErrorCode.GIT_INDEX_EMPTY, "Git index has no changes")
            if empty.returncode != 1:
                raise BridgeError(ErrorCode.GIT_COMMAND_FAILED, "Git index could not be inspected")
            await self._runner.run(
                repository,
                ["commit", "--file=-", "--cleanup=verbatim"],
                input_text=message,
            )
            new_head = await self._head(repository)
            result = GitCommitResult(
                "committed",
                await self._commit_metadata(repository, new_head),
                head,
                new_head,
                await self._index_revision(repository),
            )
            self._write_receipt(repository, "commit", key, payload, result.as_dict())
            return result

    async def push_plan(
        self,
        repository: Repository,
        *,
        remote: str | None = None,
        remote_branch: str | None = None,
    ) -> GitPushPlan:
        self._require_write(repository)
        await self._ensure_no_operation(repository)
        local_branch = await self._local_branch(repository)
        upstream_remote, upstream_branch = await self._upstream(repository)
        if remote is None:
            remote = upstream_remote
        if remote_branch is None:
            remote_branch = upstream_branch
        if remote is None or remote_branch is None:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "remote and remote_branch are required when no upstream is configured",
            )
        self._validate_remote(remote)
        await self._require_branch(repository, remote_branch)
        await self._require_remote(repository, remote)
        local_head = await self._head(repository)
        remote_ref = f"refs/heads/{remote_branch}"
        remote_head = await self._remote_head(repository, remote, remote_ref)
        set_upstream = upstream_remote is None
        if remote_head == local_head:
            action, fast_forward = "up_to_date", True
            commits: tuple[GitCommit, ...] = ()
            count = 0
        elif remote_head is None:
            action, fast_forward = "create", True
            commits, count = await self._push_commits(repository, local_head, None)
        else:
            ancestor = await self._runner.run(
                repository,
                ["merge-base", "--is-ancestor", remote_head, local_head],
                check=False,
            )
            fast_forward = ancestor.returncode == 0
            action = "update" if fast_forward else "rejected"
            if fast_forward:
                commits, count = await self._push_commits(repository, local_head, remote_head)
            else:
                commits, count = (), 0
        plan_id = self._plan_id(
            repository, local_branch, local_head, remote, remote_ref, remote_head
        )
        return GitPushPlan(
            plan_id,
            local_branch,
            local_head,
            remote,
            remote_branch,
            remote_ref,
            remote_head,
            action,
            fast_forward,
            set_upstream,
            commits,
            count,
            count > self.MAX_PUSH_COMMITS,
        )

    async def push(
        self,
        repository: Repository,
        *,
        plan_id: str,
        local_branch: str,
        local_head: str,
        remote: str,
        remote_branch: str,
        remote_head: str | None,
        set_upstream: bool,
        idempotency_key: str,
    ) -> GitPushResult:
        self._require_write(repository)
        key = self._normalize_key(idempotency_key)
        self._validate_remote(remote)
        payload = {
            "plan_id": plan_id,
            "local_branch": local_branch,
            "local_head": local_head,
            "remote": remote,
            "remote_branch": remote_branch,
            "remote_head": remote_head,
            "set_upstream": set_upstream,
        }
        async with self._mutations.acquire(repository):
            receipt = self._read_receipt(repository, "push", key, payload)
            if receipt is not None:
                return self._push_result(receipt, "already_pushed")
            await self._ensure_no_operation(repository)
            await self._require_remote(repository, remote)
            await self._require_branch(repository, local_branch)
            await self._require_branch(repository, remote_branch)
            actual_branch = await self._local_branch(repository)
            actual_head = await self._head(repository)
            remote_ref = f"refs/heads/{remote_branch}"
            expected_plan = self._plan_id(
                repository,
                local_branch,
                local_head,
                remote,
                remote_ref,
                remote_head,
            )
            if plan_id != expected_plan:
                raise BridgeError(ErrorCode.GIT_PUSH_PLAN_INVALID, "Push plan is invalid")
            if actual_branch != local_branch or actual_head != local_head:
                raise self._revision_conflict(local_head, actual_head)
            upstream_remote, upstream_branch = await self._upstream(repository)
            if set_upstream and (upstream_remote is not None or upstream_branch is not None):
                raise BridgeError(
                    ErrorCode.GIT_PUSH_PLAN_INVALID,
                    "set_upstream cannot replace an existing upstream",
                )
            actual_remote = await self._remote_head(repository, remote, remote_ref)
            if actual_remote != remote_head:
                raise BridgeError(
                    ErrorCode.GIT_PUSH_PLAN_INVALID,
                    "Remote branch changed after the push plan was created",
                    details={"expected_remote_head": remote_head, "actual_remote_head": actual_remote},
                )
            if remote_head == local_head:
                status = "already_up_to_date"
            else:
                if remote_head is not None:
                    ancestor = await self._runner.run(
                        repository,
                        ["merge-base", "--is-ancestor", remote_head, local_head],
                        check=False,
                    )
                    if ancestor.returncode != 0:
                        raise BridgeError(
                            ErrorCode.GIT_PUSH_REJECTED,
                            "Push is not a fast-forward update",
                        )
                arguments = ["push"]
                if set_upstream:
                    arguments.append("--set-upstream")
                arguments.extend([remote, f"{local_head}:{remote_ref}"])
                pushed = await self._runner.run(repository, arguments, check=False)
                if pushed.returncode != 0:
                    raise BridgeError(
                        ErrorCode.GIT_PUSH_REJECTED,
                        "Git push was rejected",
                        retryable=True,
                        details={"repository_id": repository.id},
                    )
                if set_upstream:
                    await self._runner.run(
                        repository,
                        ["branch", "--set-upstream-to", f"{remote}/{remote_branch}", local_branch],
                    )
                status = "pushed"
            result = GitPushResult(
                status,
                plan_id,
                remote,
                remote_branch,
                remote_head,
                local_head,
                local_head,
                await self._upstream_name(repository),
            )
            self._write_receipt(repository, "push", key, payload, result.as_dict())
            return result

    def _require_write(self, repository: Repository) -> None:
        self._policy.require(
            repository.capabilities,
            Capability.GIT_WRITE,
            project_id=repository.project_id,
            repository_id=repository.id,
        )

    @classmethod
    def _normalize_paths(cls, paths: Any) -> tuple[str, ...]:
        if not isinstance(paths, (list, tuple)) or not 1 <= len(paths) <= cls.MAX_PATHS:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "paths must be a non-empty bounded array")
        normalized = []
        for value in paths:
            if not isinstance(value, str) or not value or "\0" in value:
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "path must be a non-empty string")
            path = PurePosixPath(value)
            if path.is_absolute() or ".." in path.parts or path.parts[0] == ".git":
                raise BridgeError(ErrorCode.POLICY_VIOLATION, "Path is outside the repository boundary")
            normalized.append(path.as_posix())
        if len(set(normalized)) != len(normalized):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "paths must be unique")
        return tuple(normalized)

    @classmethod
    def _normalize_message(cls, message: Any) -> str:
        if not isinstance(message, str) or not message.strip() or "\0" in message:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "message must be non-empty UTF-8 text")
        if len(message.encode("utf-8")) > cls.MAX_MESSAGE_BYTES:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "message exceeds the size limit")
        return message

    @staticmethod
    def _normalize_key(key: Any) -> str:
        if not isinstance(key, str) or not key or len(key) > 200 or "\0" in key:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "idempotency_key is invalid")
        return key

    @classmethod
    def _validate_remote(cls, remote: str) -> None:
        if not cls._REMOTE.fullmatch(remote):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "remote name is invalid")

    async def _require_branch(self, repository: Repository, branch: str) -> None:
        if not isinstance(branch, str) or not branch or "\0" in branch or len(branch) > 1024:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "branch name is invalid")
        result = await self._runner.run(
            repository, ["check-ref-format", f"refs/heads/{branch}"], check=False
        )
        if result.returncode != 0:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "branch name is invalid")

    async def _ensure_no_operation(self, repository: Repository) -> None:
        git_dir = repository.root / ".git"
        if any(
            (git_dir / marker).exists()
            for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "rebase-merge", "rebase-apply")
        ):
            raise BridgeError(ErrorCode.GIT_OPERATION_IN_PROGRESS, "A Git operation is in progress")

    async def _head(self, repository: Repository) -> str:
        return (await self._runner.run(repository, ["rev-parse", "--verify", "HEAD"])).stdout.strip()

    async def _index_revision(self, repository: Repository) -> str:
        result = await self._runner.run(repository, ["ls-files", "--stage", "-z"])
        return "sha256:" + hashlib.sha256(result.stdout.encode("utf-8")).hexdigest()

    async def _staged_file_count(self, repository: Repository) -> int:
        result = await self._runner.run(repository, ["diff", "--cached", "--name-only", "-z"])
        return len([path for path in result.stdout.split("\0") if path])

    async def _local_branch(self, repository: Repository) -> str:
        result = await self._runner.run(repository, ["symbolic-ref", "--short", "HEAD"], check=False)
        if result.returncode != 0 or not result.stdout.strip():
            raise BridgeError(ErrorCode.GIT_PUSH_PLAN_INVALID, "Push requires a named local branch")
        return result.stdout.strip()

    async def _upstream(self, repository: Repository) -> tuple[str | None, str | None]:
        result = await self._runner.run(
            repository, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], check=False
        )
        if result.returncode != 0:
            return None, None
        value = result.stdout.strip()
        remote, separator, branch = value.partition("/")
        return (remote, branch) if separator else (None, None)

    async def _upstream_name(self, repository: Repository) -> str | None:
        remote, branch = await self._upstream(repository)
        return f"{remote}/{branch}" if remote and branch else None

    async def _require_remote(self, repository: Repository, remote: str) -> None:
        result = await self._runner.run(repository, ["remote", "get-url", remote], check=False)
        if result.returncode != 0:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Git remote is not configured", details={"remote": remote})

    async def _remote_head(self, repository: Repository, remote: str, remote_ref: str) -> str | None:
        result = await self._runner.run(repository, ["ls-remote", "--heads", remote, remote_ref])
        line = result.stdout.strip()
        return line.split("\t", 1)[0] if line else None

    async def _push_commits(
        self, repository: Repository, local_head: str, remote_head: str | None
    ) -> tuple[tuple[GitCommit, ...], int]:
        range_value = f"{remote_head}..{local_head}" if remote_head else local_head
        count = int((await self._runner.run(repository, ["rev-list", "--count", range_value])).stdout.strip())
        result = await self._runner.run(
            repository,
            ["log", f"--max-count={self.MAX_PUSH_COMMITS}", "--format=%H%x1f%P%x1f%an%x1f%ae%x1f%aI%x1f%s%x1e", range_value],
        )
        commits = []
        for record in result.stdout.split("\x1e"):
            record = record.strip("\n")
            if record:
                sha, parents, name, email, authored_at, subject = record.split("\x1f", 5)
                commits.append(GitCommit(sha, tuple(parents.split()) if parents else (), name, email, authored_at, subject))
        return tuple(commits), count

    async def _commit_metadata(self, repository: Repository, revision: str) -> GitCommit:
        result = await self._runner.run(
            repository, ["show", "-s", "--format=%H%x1f%P%x1f%an%x1f%ae%x1f%aI%x1f%s", revision]
        )
        sha, parents, name, email, authored_at, subject = result.stdout.rstrip("\n").split("\x1f", 5)
        return GitCommit(sha, tuple(parents.split()) if parents else (), name, email, authored_at, subject)

    @staticmethod
    def _plan_id(repository: Repository, local_branch: str, local_head: str, remote: str, remote_ref: str, remote_head: str | None) -> str:
        payload = [repository.project_id, repository.id, local_branch, local_head, remote, remote_ref, remote_head]
        canonical = json.dumps(payload, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _revision_conflict(expected: str, actual: str) -> BridgeError:
        return BridgeError(ErrorCode.REVISION_CONFLICT, "Git state does not match the guarded revision", details={"expected_revision": expected, "actual_revision": actual})

    @staticmethod
    def _receipt_path(repository: Repository, kind: str, key: str):
        digest = hashlib.sha256(key.encode()).hexdigest()
        return repository.root / ".git" / "development-bridge" / "git-write-receipts" / kind / f"{digest}.json"

    def _read_receipt(self, repository: Repository, kind: str, key: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        path = self._receipt_path(repository, kind, key)
        if not path.exists():
            return None
        stored = json.loads(path.read_text(encoding="utf-8"))
        if stored.get("key") != key or stored.get("payload") != payload:
            raise BridgeError(ErrorCode.IDEMPOTENCY_CONFLICT, "idempotency_key was already used with a different request")
        return stored["result"]

    def _write_receipt(self, repository: Repository, kind: str, key: str, payload: dict[str, Any], result: dict[str, Any]) -> None:
        path = self._receipt_path(repository, kind, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps({"key": key, "payload": payload, "result": result}, sort_keys=True, separators=(",", ":"))
        descriptor, temporary = tempfile.mkstemp(prefix=".receipt-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as target:
                target.write(data)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, path)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise

    @staticmethod
    def _commit_result(payload: dict[str, Any], status: str) -> GitCommitResult:
        commit = payload["commit"]
        return GitCommitResult(status, GitCommit(commit["sha"], tuple(commit["parents"]), commit["author_name"], commit["author_email"], commit["authored_at"], commit["subject"]), payload["previous_head"], payload["head"], payload["index_revision"])

    @staticmethod
    def _push_result(payload: dict[str, Any], status: str) -> GitPushResult:
        return GitPushResult(status, payload["plan_id"], payload["remote"], payload["remote_branch"], payload["previous_remote_head"], payload["remote_head"], payload["local_head"], payload["upstream"])
