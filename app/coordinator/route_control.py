from __future__ import annotations

from app.api.errors import BridgeError, ErrorCode
from app.coordinator.chatgpt_target import parse_chatgpt_target
from app.coordinator.route_control_diagnostics import RouteControlTraceStore
from app.coordinator.routes import RouteRegistry


class RouteControlService:
    def __init__(
        self,
        route_registry: RouteRegistry,
        trace_store: RouteControlTraceStore,
        *,
        public_base_url: str | None = None,
        endpoint_prefix: str = "/x/route-control",
    ) -> None:
        self.route_registry = route_registry
        self.trace_store = trace_store
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
        self.trace_store.stage(diag_id, "widget_external_open", "ok")

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
        if diag_id is None:
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

        route_id = self._find_route_id_for_token(operation_id)
        if route_id is None:
            if diag_id:
                self.trace_store.stage(
                    diag_id,
                    "registry_commit",
                    "failed",
                    error_code="TOKEN_INVALID",
                )
                self.trace_store.finish(diag_id, status="failed", error_code="TOKEN_INVALID")
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "current-chat bind token is invalid or stale")

        try:
            res = self.route_registry.complete_current_bind(route_id, operation_id)
        except BridgeError as exc:
            msg = str(exc)
            if "candidate is not ready" in msg or "not ready" in msg:
                err_code = "CANDIDATE_EXPIRED"
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
