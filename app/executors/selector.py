from app.api.errors import BridgeError, ErrorCode
from app.executors.models import ExecutorName, ExecutorRequest, ExecutorSelection, ExecutorStatus, QuotaState, TaskKind


class ExecutorSelector:
    def select(self, request: ExecutorRequest, antigravity: ExecutorStatus) -> ExecutorSelection:
        if request.executor is ExecutorName.CODEX:
            return ExecutorSelection(ExecutorName.CODEX, "explicit_override")
        if request.executor is ExecutorName.ANTIGRAVITY:
            self._validate_antigravity(antigravity)
            suffix = {QuotaState.LOW: "_low_quota", QuotaState.UNKNOWN: "_unknown_quota"}.get(
                antigravity.quota_state, "")
            return ExecutorSelection(ExecutorName.ANTIGRAVITY, "explicit_override" + suffix)
        if request.task_kind not in {TaskKind.IMPLEMENTATION, TaskKind.REVIEW}:
            return ExecutorSelection(ExecutorName.CODEX, "automatic_unsuitable")
        if not antigravity.available:
            reason = "automatic_unavailable"
        elif not antigravity.authenticated:
            reason = "automatic_auth_required"
        elif antigravity.busy:
            reason = "automatic_busy"
        elif antigravity.quota_state is QuotaState.EXHAUSTED:
            reason = "automatic_quota_exhausted"
        elif antigravity.quota_state is QuotaState.LOW:
            reason = "automatic_low_quota"
        elif antigravity.quota_state is QuotaState.UNKNOWN:
            reason = "automatic_quota_unknown"
        else:
            return ExecutorSelection(ExecutorName.ANTIGRAVITY, "automatic_suitable")
        return ExecutorSelection(ExecutorName.CODEX, reason)

    @staticmethod
    def _validate_antigravity(status: ExecutorStatus) -> None:
        gates = ((not status.available, "unavailable", "Antigravity executor is unavailable"),
                 (not status.authenticated, "auth_required", "Antigravity authentication is required"),
                 (status.busy, "busy", "Antigravity executor is busy"),
                 (status.quota_state is QuotaState.EXHAUSTED, "quota_exhausted", "Antigravity quota is exhausted"))
        for blocked, reason, message in gates:
            if blocked:
                raise BridgeError(ErrorCode.POLICY_VIOLATION, message, details={"reason": reason})
