from __future__ import annotations

from typing import TYPE_CHECKING

from app.api.errors import BridgeError, ErrorCode
from app.coordinator.chatgpt_target import parse_chatgpt_target
from app.coordinator.route_control_diagnostics import RouteControlTraceStore
from app.coordinator.routes import RouteRegistry
if TYPE_CHECKING:
    from app.coordinator.service import CoordinatorService

    from app.jobs.service import JobService


class RouteControlService:
    def __init__(
        self,
        route_registry: RouteRegistry,
        trace_store: RouteControlTraceStore,
        *,
        coordinator: CoordinatorService | None = None,
        jobs: JobService | None = None,
        public_base_url: str | None = None,
        endpoint_prefix: str = "/x/route-control",
    ) -> None:
        self.route_registry = route_registry
        self.trace_store = trace_store
        self.coordinator = coordinator
        self.jobs = jobs
        self.public_base_url = public_base_url.rstrip("/") if public_base_url else None
        self.endpoint_prefix = endpoint_prefix.rstrip("/")


    def _find_route_id_for_token(self, token: str) -> str | None:
        data = self.route_registry.snapshot()
        current_binds = data.get("current_binds") or {}
        for route_id, pending in current_binds.items():
            if isinstance(pending, dict) and pending.get("token") == token:
                return route_id
        return None

    def prepare_bind(
        self,
        route_id: str,
        *,
        session_id: str | None = None,
        allow_project_change: bool = False,
    ) -> dict:
        route_id = self.route_registry.validate_route_id(route_id)
        route = self.route_registry.resolve(route_id)
        if route is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")

        pending = self.route_registry.prepare_current_bind(
            route_id,
            session_id=session_id,
            allow_project_change=allow_project_change,
        )
        token = pending["token"]

        diag_id = self.trace_store.start("bind", route_id=route_id, operation_id=token)

        base = self.public_base_url.rstrip("/") if self.public_base_url else ""
        operation_url = f"{base}{self.endpoint_prefix}/bind/{token}"

        return {
            "route_id": route_id,
            "state": "bind_pending",
            "generation": int(route.get("generation", 0)),
            "channel_id": route.get("channel_id") or f"telegram-{route_id}-g{int(route.get('generation', 0))}",
            "operation_id": token,
            "diagnostic_id": diag_id,
            "operation_url": operation_url,
        }

    def accept_bind_return(self, operation_id: str, redirect_url: str | None) -> dict:
        diag_id = self.trace_store.find_by_operation_id(operation_id)
        if diag_id is not None:
            existing_trace = self.trace_store.sanitized(diag_id)
            if existing_trace and existing_trace.get("status") in ("ok", "failed"):
                if existing_trace.get("status") == "ok":
                    raise BridgeError(ErrorCode.POLICY_VIOLATION, "current-chat bind operation already completed")
                err = existing_trace.get("error_code") or "OPERATION_FAILED"
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"current-chat bind operation already failed: {err}")
        else:
            diag_id = self.trace_store.start("bind", operation_id=operation_id)

        if not redirect_url or not str(redirect_url).strip():
            self.trace_store.stage(
                diag_id,
                "return_received",
                "failed",
                error_code="RETURN_TARGET_MISSING",
            )
            self.trace_store.finish(diag_id, status="failed", error_code="RETURN_TARGET_MISSING")
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "return target is missing")

        self.trace_store.stage(
            diag_id,
            "return_received",
            "ok",
            details={"raw_redirect_url": redirect_url},
        )

        try:
            parse_chatgpt_target(redirect_url)
        except BridgeError as exc:
            self.trace_store.stage(
                diag_id,
                "target_parse",
                "failed",
                error_code="TARGET_PARSE_FAILED",
                details={"error": str(exc)},
            )
            self.trace_store.finish(diag_id, status="failed", error_code="TARGET_PARSE_FAILED")
            raise

        self.trace_store.stage(diag_id, "target_parse", "ok")

        route_id = self._find_route_id_for_token(operation_id)
        if route_id is None:
            self.trace_store.stage(
                diag_id,
                "token_check",
                "failed",
                error_code="TOKEN_INVALID",
            )
            self.trace_store.finish(diag_id, status="failed", error_code="TOKEN_INVALID")
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "current-chat bind token is invalid or stale")

        self.trace_store.stage(diag_id, "token_check", "ok")

        try:
            self.route_registry.record_current_bind_candidate(route_id, operation_id, redirect_url)
        except BridgeError as exc:
            msg = str(exc)
            if "different project" in msg:
                err_code = "PROJECT_MISMATCH"
                self.trace_store.stage(diag_id, "project_policy", "failed", error_code=err_code)
            elif "active route changed" in msg:
                err_code = "GENERATION_CHANGED"
                self.trace_store.stage(diag_id, "generation_guard", "failed", error_code=err_code)
            elif "already recorded" in msg:
                err_code = "TOKEN_REPLAYED"
                self.trace_store.stage(diag_id, "candidate_store", "failed", error_code=err_code)
            elif "invalid or stale" in msg:
                err_code = "TOKEN_EXPIRED"
                self.trace_store.stage(diag_id, "token_check", "failed", error_code=err_code)
            else:
                err_code = "REGISTRY_WRITE_FAILED"
                self.trace_store.stage(diag_id, "candidate_store", "failed", error_code=err_code)
            self.trace_store.finish(diag_id, status="failed", error_code=err_code)
            raise

        self.trace_store.stage(diag_id, "project_policy", "ok")
        self.trace_store.stage(diag_id, "generation_guard", "ok")
        self.trace_store.stage(diag_id, "candidate_store", "ok")

        return {
            "operation_id": operation_id,
            "route_id": route_id,
            "state": "candidate",
            "diagnostic_id": diag_id,
        }

    def commit_bind(self, operation_id: str) -> dict:
        diag_id = self.trace_store.find_by_operation_id(operation_id)
        if diag_id:
            existing_trace = self.trace_store.sanitized(diag_id)
            if existing_trace and existing_trace.get("status") in ("ok", "failed"):
                if existing_trace.get("status") == "ok":
                    raise BridgeError(ErrorCode.POLICY_VIOLATION, "current-chat bind operation already completed")
                err = existing_trace.get("error_code") or "OPERATION_FAILED"
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"current-chat bind operation already failed: {err}")

        route_id = self._find_route_id_for_token(operation_id)
        if route_id is None:
            if diag_id:
                self.trace_store.stage(
                    diag_id,
                    "registry_commit",
                    "failed",
                    error_code="TOKEN_EXPIRED",
                )
                self.trace_store.finish(diag_id, status="failed", error_code="TOKEN_EXPIRED")
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "current-chat bind token is invalid or stale")

        try:
            res = self.route_registry.complete_current_bind(route_id, operation_id)
        except BridgeError as exc:
            msg = str(exc)
            if "candidate is not ready" in msg or "not ready" in msg:
                err_code = "CANDIDATE_NOT_READY"
                if diag_id:
                    self.trace_store.stage(diag_id, "registry_commit", "failed", error_code=err_code)
            elif "different project" in msg:
                err_code = "PROJECT_MISMATCH"
                if diag_id:
                    self.trace_store.stage(diag_id, "project_policy", "failed", error_code=err_code)
            elif "active route changed" in msg:
                err_code = "GENERATION_CHANGED"
                if diag_id:
                    self.trace_store.stage(diag_id, "generation_guard", "failed", error_code=err_code)
            elif "invalid or stale" in msg:
                err_code = "TOKEN_EXPIRED"
                if diag_id:
                    self.trace_store.stage(diag_id, "registry_commit", "failed", error_code=err_code)
            else:
                err_code = "REGISTRY_WRITE_FAILED"
                if diag_id:
                    self.trace_store.stage(diag_id, "registry_commit", "failed", error_code=err_code)
            if diag_id:
                self.trace_store.finish(diag_id, status="failed", error_code=err_code)
            raise

        if diag_id:
            self.trace_store.stage(diag_id, "registry_commit", "ok")
            self.trace_store.finish(diag_id, status="ok")

        changed = res.get("changed", True)
        return {
            "route_id": route_id,
            "state": "bound" if changed else "already_bound",
            "generation": res["generation"],
            "channel_id": res["channel_id"],
            "changed": changed,
            "diagnostic_id": diag_id,
        }

    def safe_status(self, route_id: str) -> dict:
        route_id = self.route_registry.validate_route_id(route_id)
        route = self.route_registry.resolve(route_id)
        if route is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")

        pending = self.route_registry.pending_current_bind(route_id)
        if pending is not None:
            state = "bind_pending"
        elif self.route_registry.is_bound(route):
            state = "bound"
        else:
            state = "unbound"

        last_diag = self.trace_store.latest_diagnostic_id_for_route(route_id)
        last_op = None
        if last_diag:
            st = self.trace_store.sanitized(last_diag)
            if st:
                last_op = {
                    "diagnostic_id": last_diag,
                    "operation_type": st.get("operation_type"),
                    "status": st.get("status"),
                    "error_code": st.get("error_code"),
                }

        return {
            "route_id": route_id,
            "title": route.get("title") or route_id,
            "state": state,
            "generation": int(route.get("generation", 0)),
            "channel_id": route.get("channel_id") or f"telegram-{route_id}-g{int(route.get('generation', 0))}",
            "pending_coordinator_wakes": "not_checked",
            "pending_durable_waiters": "not_checked",
            "target_probe": "not_checked",
            "last_operation": last_op,
        }

    def resolve_return_target(self, diagnostic_id: str) -> str | None:
        return self.trace_store.get_return_target(diagnostic_id)

    async def cancel_wakes(
        self,
        route_id: str,
        *,
        operation_id: str | None = None,
    ) -> dict:
        route_id = self.route_registry.validate_route_id(route_id)
        route = self.route_registry.resolve(route_id)
        if route is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")

        diag_id = (
            self.trace_store.find_by_operation_id(operation_id)
            if operation_id
            else None
        )
        if diag_id is None:
            diag_id = self.trace_store.start("cancel_wakes", route_id=route_id, operation_id=operation_id)

        generation = int(route.get("generation", 0))
        channel_id = route.get("channel_id") or f"telegram-{route_id}-g{generation}"

        coord_cancelled = 0
        if self.coordinator is not None:
            try:
                coord_res = await self.coordinator.cancel_pending(channel_id)
                coord_cancelled = 1 if coord_res.get("cancelled") else 0
            except BridgeError:
                self.trace_store.stage(
                    diag_id, "wake_cancel", "failed", error_code="WAKE_CANCEL_FAILED"
                )
                self.trace_store.finish(diag_id, status="failed", error_code="WAKE_CANCEL_FAILED")
                raise

        waiters_cancelled = 0
        if self.jobs is not None:
            try:
                job_res = await self.jobs.cancel_durable_waiters(
                    handler_name="coordinator",
                    payload_match={"route_id": route_id, "generation": generation},
                )
                waiters_cancelled = int(job_res.get("cancelled_count", 0))
            except BridgeError:
                self.trace_store.stage(
                    diag_id, "wake_cancel", "failed", error_code="WAKE_CANCEL_FAILED"
                )
                self.trace_store.finish(diag_id, status="failed", error_code="WAKE_CANCEL_FAILED")
                raise

        self.trace_store.stage(diag_id, "wake_cancel", "ok")
        self.trace_store.finish(diag_id, status="ok")

        return {
            "route_id": route_id,
            "state": "wakes_cancelled",
            "generation": generation,
            "channel_id": channel_id,
            "cancelled_coordinator_wakes": coord_cancelled,
            "cancelled_durable_waiters": waiters_cancelled,
            "diagnostic_id": diag_id,
        }

    async def unbind(
        self,
        route_id: str,
        *,
        expected_generation: int | None = None,
        operation_id: str | None = None,
    ) -> dict:
        route_id = self.route_registry.validate_route_id(route_id)
        route = self.route_registry.resolve(route_id)
        if route is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")

        generation = int(route.get("generation", 0))
        if expected_generation is not None and int(expected_generation) != generation:
            raise BridgeError(ErrorCode.POLICY_VIOLATION, "route generation changed before unbind")

        diag_id = (
            self.trace_store.find_by_operation_id(operation_id)
            if operation_id
            else None
        )
        if diag_id is None:
            diag_id = self.trace_store.start("unbind", route_id=route_id, operation_id=operation_id)

        channel_id = route.get("channel_id") or f"telegram-{route_id}-g{generation}"

        # 1. Guard against coordinator wake-producing state
        if self.coordinator is not None:
            coord_status = await self.coordinator.status(channel_id)
            if coord_status.get("state") != "idle":
                self.trace_store.stage(
                    diag_id, "wake_cancel", "failed", error_code="PENDING_WAKES"
                )
                self.trace_store.finish(diag_id, status="failed", error_code="PENDING_WAKES")
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    "Cannot unbind route with active or pending coordinator wakes; cancel wakes first",
                    details={"route_id": route_id, "error_code": "PENDING_WAKES"},
                )

        # 2. Guard against durable waiter wake-producing state
        if self.jobs is not None and self.jobs.store is not None:
            waiters = [
                w
                for w in self.jobs.store.terminal_waiters()
                if w.get("handler_name") == "coordinator"
                and isinstance(w.get("payload"), dict)
                and w["payload"].get("route_id") == route_id
                and int(w["payload"].get("generation", -1)) == generation
            ]
            if waiters:
                self.trace_store.stage(
                    diag_id, "wake_cancel", "failed", error_code="PENDING_WAKES"
                )
                self.trace_store.finish(diag_id, status="failed", error_code="PENDING_WAKES")
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    "Cannot unbind route with active durable waiters; cancel wakes first",
                    details={"route_id": route_id, "error_code": "PENDING_WAKES"},
                )

        self.trace_store.stage(diag_id, "wake_cancel", "ok")

        try:
            res = self.route_registry.unbind(route_id, expected_generation=generation)
        except BridgeError:
            self.trace_store.stage(
                diag_id, "registry_commit", "failed", error_code="REGISTRY_WRITE_FAILED"
            )
            self.trace_store.finish(diag_id, status="failed", error_code="REGISTRY_WRITE_FAILED")
            raise

        self.trace_store.stage(diag_id, "registry_commit", "ok")
        self.trace_store.finish(diag_id, status="ok")

        return {
            "route_id": route_id,
            "state": "unbound",
            "generation": res["generation"],
            "channel_id": res["channel_id"],
            "diagnostic_id": diag_id,
        }

    async def unbind_and_cancel(
        self,
        route_id: str,
        *,
        expected_generation: int | None = None,
        operation_id: str | None = None,
    ) -> dict:
        route_id = self.route_registry.validate_route_id(route_id)
        route = self.route_registry.resolve(route_id)
        if route is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")

        generation = int(route.get("generation", 0))
        if expected_generation is not None and int(expected_generation) != generation:
            raise BridgeError(ErrorCode.POLICY_VIOLATION, "route generation changed before unbind")

        diag_id = (
            self.trace_store.find_by_operation_id(operation_id)
            if operation_id
            else None
        )
        if diag_id is None:
            diag_id = self.trace_store.start("unbind_and_cancel", route_id=route_id, operation_id=operation_id)

        channel_id = route.get("channel_id") or f"telegram-{route_id}-g{generation}"

        # 1. Cancel coordinator pending state
        coord_cancelled = 0
        if self.coordinator is not None:
            try:
                coord_res = await self.coordinator.cancel_pending(channel_id)
                coord_cancelled = 1 if coord_res.get("cancelled") else 0
            except BridgeError:
                self.trace_store.stage(
                    diag_id, "wake_cancel", "failed", error_code="WAKE_CANCEL_FAILED"
                )
                self.trace_store.finish(diag_id, status="failed", error_code="WAKE_CANCEL_FAILED")
                raise

        # 2. Cancel durable waiters
        waiters_cancelled = 0
        if self.jobs is not None:
            try:
                job_res = await self.jobs.cancel_durable_waiters(
                    handler_name="coordinator",
                    payload_match={"route_id": route_id, "generation": generation},
                )
                waiters_cancelled = int(job_res.get("cancelled_count", 0))
            except BridgeError:
                self.trace_store.stage(
                    diag_id, "wake_cancel", "failed", error_code="WAKE_CANCEL_FAILED"
                )
                self.trace_store.finish(diag_id, status="failed", error_code="WAKE_CANCEL_FAILED")
                raise

        # 3. Verify zero wake-producing state
        if self.coordinator is not None:
            coord_status = await self.coordinator.status(channel_id)
            if coord_status.get("state") != "idle":
                self.trace_store.stage(
                    diag_id, "wake_cancel", "failed", error_code="WAKE_CANCEL_FAILED"
                )
                self.trace_store.finish(diag_id, status="failed", error_code="WAKE_CANCEL_FAILED")
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    "Coordinator wake state is still active after cancellation attempt",
                    details={"route_id": route_id, "error_code": "WAKE_CANCEL_FAILED"},
                )

        if self.jobs is not None and self.jobs.store is not None:
            remaining_waiters = [
                w
                for w in self.jobs.store.terminal_waiters()
                if w.get("handler_name") == "coordinator"
                and isinstance(w.get("payload"), dict)
                and w["payload"].get("route_id") == route_id
                and int(w["payload"].get("generation", -1)) == generation
            ]
            if remaining_waiters:
                self.trace_store.stage(
                    diag_id, "wake_cancel", "failed", error_code="WAKE_CANCEL_FAILED"
                )
                self.trace_store.finish(diag_id, status="failed", error_code="WAKE_CANCEL_FAILED")
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    "Durable waiters still active after cancellation attempt",
                    details={"route_id": route_id, "error_code": "WAKE_CANCEL_FAILED"},
                )

        self.trace_store.stage(diag_id, "wake_cancel", "ok")

        # 4. Perform registry unbind
        try:
            res = self.route_registry.unbind(route_id, expected_generation=generation)
        except BridgeError:
            self.trace_store.stage(
                diag_id, "registry_commit", "failed", error_code="REGISTRY_WRITE_FAILED"
            )
            self.trace_store.finish(diag_id, status="failed", error_code="REGISTRY_WRITE_FAILED")
            raise

        self.trace_store.stage(diag_id, "registry_commit", "ok")
        self.trace_store.finish(diag_id, status="ok")

        return {
            "route_id": route_id,
            "state": "unbound",
            "generation": res["generation"],
            "channel_id": res["channel_id"],
            "cancelled_coordinator_wakes": coord_cancelled,
            "cancelled_durable_waiters": waiters_cancelled,
            "diagnostic_id": diag_id,
        }
