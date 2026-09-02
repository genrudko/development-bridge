from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.coordinator.progress import RouteProgressStore
from app.executors.antigravity_quota import load_quota_snapshot
from app.jobs.models import JobRecord, JobStatus
from app.ops.git_snapshot import GitSnapshotProvider
from app.ops.metrics import (
    async_process_counts,
    disk_snapshot,
    load_snapshot,
    memory_snapshot,
    uptime_seconds,
)


class OperatorDashboardService:
    def __init__(
        self,
        container: Any,
        git_provider: GitSnapshotProvider | None = None,
    ) -> None:
        self._container = container
        self._git_provider = git_provider or GitSnapshotProvider()

    def _progress_store(self) -> RouteProgressStore:
        return RouteProgressStore(self._container.route_registry.path.parent / "route-progress.json")

    def _get_job_store(self) -> Any:
        return getattr(self._container.jobs, "store", None) or getattr(
            self._container.jobs, "_store", None
        )

    async def snapshot(
        self,
        route_id: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        settings = self._container.settings
        ops_settings = settings.operator_dashboard
        recent_limit = ops_settings.recent_jobs_limit

        # 1. Bridge state
        projects = self._container.projects.list()
        total_repos = sum(len(p.repositories) for p in projects)
        bridge_info = {
            "name": settings.server.name,
            "version": "1.0.0",
            "api_version": "1.0",
            "uptime_seconds": uptime_seconds(),
            "projects_count": len(projects),
            "repositories_count": total_repos,
            "tool_surface": settings.server.tool_surface,
        }

        # 2. Global routes plus one independent route focus.
        progress_store = self._progress_store()
        routes_dicts: list[dict[str, Any]] = []
        try:
            registered_routes = self._container.route_registry.list_routes()
        except Exception:
            registered_routes = []

        for registered in registered_routes:
            item = {
                "route_id": registered.get("route_id"),
                "channel_id": registered.get("channel_id"),
                "title": registered.get("title"),
                "generation": registered.get("generation"),
                "state": registered.get("state") or registered.get("route_state") or "active",
                "default": bool(registered.get("default")),
            }
            rid = item.get("route_id")
            if rid:
                try:
                    item["progress"] = progress_store.get(str(rid))
                except Exception:
                    item["progress"] = None
            else:
                item["progress"] = None
            routes_dicts.append(item)

        route = None
        if route_id:
            try:
                resolved = self._container.route_registry.resolve(route_id)
                if resolved is not None:
                    route = resolved
            except Exception:
                route = None
        if route is None:
            try:
                registry_snapshot = self._container.route_registry.snapshot()
                requested = registry_snapshot.get("requested_route")
                if requested:
                    route = self._container.route_registry.resolve(str(requested))
                if route is None and registry_snapshot.get("default_route"):
                    route = self._container.route_registry.resolve(
                        str(registry_snapshot["default_route"])
                    )
            except Exception:
                route = None

        route_dict = None
        progress_dict = None
        channel_id = "coordinator"
        if route is not None:
            route_dict = {
                "route_id": route.get("route_id"),
                "channel_id": route.get("channel_id"),
                "title": route.get("title"),
                "generation": route.get("generation"),
                "state": route.get("state") or route.get("route_state") or "active",
            }
            channel_id = str(route.get("channel_id") or "coordinator")
            try:
                progress_dict = progress_store.get(str(route["route_id"]))
            except Exception:
                progress_dict = None

        # 3. Global jobs plus one independent job focus.
        recent_records: tuple[JobRecord, ...] = ()
        job_store = self._get_job_store()
        if job_store is not None:
            recent_records = job_store.recent(recent_limit)

        recent_dicts = [record.status_dict() for record in recent_records]
        active_records = tuple(
            record
            for record in recent_records
            if record.status in (JobStatus.QUEUED, JobStatus.RUNNING)
        )
        active_dicts = [record.status_dict() for record in active_records]

        current_job: JobRecord | None = active_records[0] if active_records else None
        last_job: JobRecord | None = None
        for record in recent_records:
            if record.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
                last_job = record
                break

        focus_job: JobRecord | None = None
        if job_id:
            focus_job = next((record for record in recent_records if record.job_id == job_id), None)
            if focus_job is None and job_store is not None:
                try:
                    focus_job = job_store.get_by_id(job_id)
                except Exception:
                    focus_job = None
        if focus_job is None:
            focus_job = current_job or (recent_records[0] if recent_records else None)

        # 4. Executor focus plus cached Antigravity quota.
        executor_dict: dict[str, Any] = {
            "executor": focus_job.executor if focus_job else None,
            "model": focus_job.executor_model if focus_job else None,
            "quota_state": focus_job.executor_quota_state if focus_job else None,
            "job_id": focus_job.job_id if focus_job else None,
        }
        ag_settings = settings.executors.antigravity
        if ag_settings.enabled and ag_settings.quota_cache_path:
            cache_path = Path(ag_settings.quota_cache_path).expanduser()
            quota_snap = load_quota_snapshot(
                cache_path, max_age_seconds=ag_settings.quota_cache_max_age_seconds
            )
            if quota_snap is not None:
                executor_dict["antigravity_quota"] = {
                    "remaining_fraction": quota_snap.remaining_fraction,
                    "percent": round(quota_snap.remaining_fraction * 100),
                    "bucket": quota_snap.bucket,
                    "model": quota_snap.model,
                    "reset_time": quota_snap.reset_time.isoformat() if quota_snap.reset_time else None,
                }

        # 5. Git follows the independent job focus, not the route focus.
        git_dict = None
        if focus_job is not None:
            try:
                repo = self._container.projects.repositories.get(
                    focus_job.project_id, focus_job.repository_id
                )
                git_dict = await self._git_provider.snapshot(repo)
            except Exception:
                git_dict = None

        # 6. Coordinator wake follows the independent route focus.
        wake_dict = await self._container.coordinator.operator_snapshot(channel_id)

        # 7. System state
        wake_delivery_settings = settings.coordinator_wake_delivery
        procs = await async_process_counts()
        system_dict = {
            "memory": memory_snapshot(),
            "disk": disk_snapshot(),
            "load": load_snapshot(),
            "uptime_seconds": uptime_seconds(),
            "process_counts": procs,
            "wake_transport": {
                "enabled": wake_delivery_settings.enabled,
                "primary_transport": wake_delivery_settings.primary_transport,
                "poll_interval_seconds": wake_delivery_settings.poll_interval_seconds,
            },
        }

        return {
            "bridge": bridge_info,
            "routes": routes_dicts,
            "route": route_dict,
            "progress": progress_dict,
            "jobs": {
                "recent": recent_dicts,
                "active": active_dicts,
                "current": current_job.status_dict() if current_job else None,
                "last": last_job.status_dict() if last_job and current_job is None else None,
                "focused": focus_job.status_dict() if focus_job else None,
                "active_count": len(active_records),
            },
            "executor": executor_dict,
            "git": git_dict,
            "wake": wake_dict,
            "system": system_dict,
        }

    async def terminal_tail(self, job_id: str | None = None) -> dict[str, Any]:
        tail_bytes = self._container.settings.operator_dashboard.terminal_tail_bytes
        recent_limit = self._container.settings.operator_dashboard.recent_jobs_limit
        store = self._get_job_store()
        if store is None:
            return {
                "job_id": None,
                "status": "idle",
                "stdout": "",
                "stderr": "",
                "stdout_truncated": False,
                "stderr_truncated": False,
                "timestamp": time.time(),
            }

        target_id = job_id
        if target_id is None:
            recent = store.recent(recent_limit)
            for record in recent:
                if record.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                    target_id = record.job_id
                    break
            if target_id is None and recent:
                target_id = recent[0].job_id

        if target_id is None:
            return {
                "job_id": None,
                "status": "idle",
                "stdout": "",
                "stderr": "",
                "stdout_truncated": False,
                "stderr_truncated": False,
                "timestamp": time.time(),
            }

        job = store.get_by_id(target_id)
        if job is None:
            return {
                "job_id": target_id,
                "status": "not_found",
                "stdout": "",
                "stderr": "",
                "stdout_truncated": False,
                "stderr_truncated": False,
                "timestamp": time.time(),
            }

        raw_stdout = job.stdout
        raw_stderr = job.stderr
        tail_stdout = raw_stdout[-tail_bytes:]
        tail_stderr = raw_stderr[-tail_bytes:]

        return {
            "job_id": job.job_id,
            "status": job.status.value,
            "stdout": tail_stdout.decode("utf-8", errors="replace"),
            "stderr": tail_stderr.decode("utf-8", errors="replace"),
            "stdout_truncated": job.stdout_truncated or len(raw_stdout) > tail_bytes,
            "stderr_truncated": job.stderr_truncated or len(raw_stderr) > tail_bytes,
            "timestamp": time.time(),
        }
