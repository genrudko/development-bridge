from app.api.errors import BridgeError, ErrorCode
from app.executors.antigravity import AntigravityExecutor
from app.executors.codex import CodexExecutor
from app.executors.models import ExecutorName, ExecutorRequest, ExecutorStatus, QuotaState
from app.executors.selector import ExecutorSelector
from app.jobs import JobRecord, JobService
from app.projects.models import Repository


class ExecutorService:
    def __init__(self, jobs: JobService, antigravity: AntigravityExecutor,
                 selector: ExecutorSelector,
                 codex: CodexExecutor | None = None) -> None:
        self._jobs = jobs
        self._antigravity = antigravity
        self._selector = selector
        self._codex = codex if codex is not None else CodexExecutor()

    async def status(self, repository: Repository) -> dict[str, object]:
        busy = self._jobs.repository_busy(repository)
        codex = ExecutorStatus(ExecutorName.CODEX, True, True, busy, None,
            QuotaState.UNKNOWN, None, None, None, None, None)
        antigravity = await self._antigravity.probe(busy=busy)
        return {"executors": [codex.public_dict(), antigravity.public_dict()]}

    async def start(self, repository: Repository, request: ExecutorRequest,
                    request_id: str) -> JobRecord:
        busy = self._jobs.repository_busy(repository)
        antigravity = await self._antigravity.probe(busy=busy)
        selection_status = antigravity
        if (antigravity.busy and request.idempotency_key is not None
                and self._jobs.execution_by_idempotency(repository, request.idempotency_key) is not None):
            selection_status = ExecutorStatus(
                antigravity.executor, antigravity.available, antigravity.authenticated,
                False, antigravity.model, antigravity.quota_state,
                antigravity.remaining_fraction, antigravity.reset_time,
                antigravity.last_error, antigravity.last_success_at, antigravity.version)
        selection = self._selector.select(request, selection_status)
        if selection.executor is ExecutorName.CODEX:
            codex_status = ExecutorStatus(ExecutorName.CODEX, True, True, busy, None,
                QuotaState.UNKNOWN, None, None, None, None, None)
            launch = self._codex.launch(repository, request, codex_status)
        else:
            launch = self._antigravity.launch(repository, request, selection_status)
        return await self._jobs.start_execution(repository, launch.executable, launch.arguments,
            request_id, timeout_seconds=request.timeout_seconds,
            output_limit_bytes=request.output_limit_bytes, stdin=launch.stdin,
            idempotency_key=request.idempotency_key, executor=launch.executor.value,
            executor_model=launch.model, executor_quota_state=launch.quota_state.value,
            environment_keys=launch.environment_keys, require_repository_idle=True)
