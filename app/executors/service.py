from app.api.errors import BridgeError, ErrorCode
from app.executors.antigravity import AntigravityExecutor, AsyncioProcessRunner
from app.executors.cline import ClineExecutor
from app.executors.codex import CodexExecutor
from app.executors.models import ExecutorName, ExecutorRequest, ExecutorStatus, QuotaState
from app.executors.openrouter import OpenRouterExecutor
from app.executors.selector import ExecutorSelector
from app.jobs import JobRecord, JobService
from app.projects.models import Repository
from app.settings import ClineExecutorSettings, OpenRouterExecutorSettings
from app.worktrees import resolve_repository_worktree

_WORKTREE_EXECUTORS = (ExecutorName.OPENROUTER, ExecutorName.CLINE)
_MODEL_EXECUTORS = (ExecutorName.OPENROUTER, ExecutorName.CLINE)


def _without_busy(status: ExecutorStatus) -> ExecutorStatus:
    """Re-probe result with the transient busy flag cleared for idempotent retries."""
    return ExecutorStatus(
        status.executor,
        status.available,
        status.authenticated,
        False,
        status.model,
        status.quota_state,
        status.remaining_fraction,
        status.reset_time,
        status.last_error,
        status.last_success_at,
        status.version,
    )


class ExecutorService:
    def __init__(
        self,
        jobs: JobService,
        antigravity: AntigravityExecutor,
        selector: ExecutorSelector,
        codex: CodexExecutor | None = None,
        openrouter: OpenRouterExecutor | None = None,
        cline: ClineExecutor | None = None,
    ) -> None:
        self._jobs = jobs
        self._antigravity = antigravity
        self._selector = selector
        self._codex = codex if codex is not None else CodexExecutor()
        self._openrouter = (
            openrouter
            if openrouter is not None
            else OpenRouterExecutor(OpenRouterExecutorSettings())
        )
        self._cline = (
            cline
            if cline is not None
            else ClineExecutor(ClineExecutorSettings(), AsyncioProcessRunner())
        )

    async def status(self, repository: Repository) -> dict[str, object]:
        busy = self._jobs.repository_busy(repository)
        codex = ExecutorStatus(
            ExecutorName.CODEX,
            True,
            True,
            busy,
            None,
            QuotaState.UNKNOWN,
            None,
            None,
            None,
            None,
            None,
        )
        antigravity = await self._antigravity.probe(busy=busy)
        openrouter = self._openrouter.probe(busy=busy)
        cline = await self._cline.probe(busy=busy)
        return {
            "executors": [
                codex.public_dict(),
                antigravity.public_dict(),
                openrouter.public_dict(),
                cline.public_dict(),
            ]
        }

    async def start(
        self,
        repository: Repository,
        request: ExecutorRequest,
        request_id: str,
    ) -> JobRecord:
        busy = self._jobs.repository_busy(repository)
        if request.worktree_branch is not None and request.executor not in _WORKTREE_EXECUTORS:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "worktree_branch is only supported for the openrouter and cline executors",
            )
        if request.model is not None and request.executor not in _MODEL_EXECUTORS:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "model parameter is only supported for the openrouter and cline executors",
            )
        execution_root = None
        launch_repository = repository
        if request.executor in _WORKTREE_EXECUTORS and request.worktree_branch is not None:
            execution_root = await resolve_repository_worktree(repository, request.worktree_branch)
            launch_repository = Repository(
                repository.project_id, repository.id, execution_root, repository.capabilities
            )
        if request.executor is ExecutorName.CLINE:
            cline = await self._cline.probe(busy=busy)
            selection_status = _without_busy(cline) if (
                cline.busy
                and request.idempotency_key is not None
                and self._jobs.execution_by_idempotency(repository, request.idempotency_key)
                is not None
            ) else cline
            launch = self._cline.launch(launch_repository, request, selection_status)
        elif request.executor is ExecutorName.OPENROUTER:
            openrouter = self._openrouter.probe(busy=busy)
            selection_status = openrouter
            if (
                openrouter.busy
                and request.idempotency_key is not None
                and self._jobs.execution_by_idempotency(
                    repository, request.idempotency_key
                )
                is not None
            ):
                selection_status = ExecutorStatus(
                    openrouter.executor,
                    openrouter.available,
                    openrouter.authenticated,
                    False,
                    openrouter.model,
                    openrouter.quota_state,
                    openrouter.remaining_fraction,
                    openrouter.reset_time,
                    openrouter.last_error,
                    openrouter.last_success_at,
                    openrouter.version,
                )
            launch = self._openrouter.launch(launch_repository, request, selection_status)
        else:
            antigravity = await self._antigravity.probe(busy=busy)
            selection_status = antigravity
            if (
                antigravity.busy
                and request.idempotency_key is not None
                and self._jobs.execution_by_idempotency(
                    repository, request.idempotency_key
                )
                is not None
            ):
                selection_status = ExecutorStatus(
                    antigravity.executor,
                    antigravity.available,
                    antigravity.authenticated,
                    False,
                    antigravity.model,
                    antigravity.quota_state,
                    antigravity.remaining_fraction,
                    antigravity.reset_time,
                    antigravity.last_error,
                    antigravity.last_success_at,
                    antigravity.version,
                )
            selection = self._selector.select(request, selection_status)
            if selection.executor is ExecutorName.CODEX:
                codex_status = ExecutorStatus(
                    ExecutorName.CODEX,
                    True,
                    True,
                    busy,
                    None,
                    QuotaState.UNKNOWN,
                    None,
                    None,
                    None,
                    None,
                    None,
                )
                launch = self._codex.launch(repository, request, codex_status)
            else:
                launch = self._antigravity.launch(repository, request, selection_status)

        return await self._jobs.start_execution(
            repository,
            launch.executable,
            launch.arguments,
            request_id,
            timeout_seconds=request.timeout_seconds,
            output_limit_bytes=request.output_limit_bytes,
            stdin=launch.stdin,
            idempotency_key=request.idempotency_key,
            executor=launch.executor.value,
            executor_model=launch.model,
            executor_quota_state=launch.quota_state.value,
            environment_keys=launch.environment_keys,
            require_repository_idle=False,
            execution_root=execution_root,
            worktree_branch=request.worktree_branch,
        )
