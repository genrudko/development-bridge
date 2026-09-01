from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.coordinator.progress import RouteProgressStore
from app.executors.antigravity_quota import load_quota_snapshot
from app.jobs.models import JobRecord, JobStatus
from app.ops.git_snapshot import GitSnapshotProvider
from app.ops.metrics import (
    disk_snapshot,
    load_snapshot,
    memory_snapshot,
    process_counts,
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

    async def snapshot(self, route_id: str | None = None) -> dict[str, Any]:
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

        # 2. Route & Progress
        route = None
        if route_id:
            resolved = self._container.route_registry.resolve(route_id)
            if resolved is not None:
                route = resolved
        if route is None:
            snapshot = self._container.route_registry.snapshot()
            req = snapshot.get("requested_route")
            if req:
                route = self._container.route_registry.resolve(str(req))
            if route is None and snapshot.get("default_route"):
                route = self._container.route_registry.resolve(str(snapshot["default_route"]))

        route_dict = None
        progress_dict = None
        channel_id = "coordinator"
        if route is not None:
            route_dict = {
                "route_id": route.get("route_id"),
                "channel_id": route.get("channel_id"),
                "title": route.get("title"),
                "generation": route.get("generation"),
                "state": route.get("state"),
            }
            channel_id = str(route.get("channel_id") or "coordinator")
            try:
                progress_dict = self._progress_store().get(str(route["route_id"]))
            except Exception:
                progress_dict = None

        # 3. Jobs
        recent_records: tuple[JobRecord, ...] = ()
        job_store = getattr(self._container.jobs, "store", None) or getattr(
            self._container.jobs, "_store", None
        )
        if job_store is not None:
            recent_records = job_store.recent(recent_limit)

        recent_dicts = [record.status_dict() for record in recent_records]
        current_job: JobRecord | None = None
        last_job: JobRecord | None = None

        for record in recent_records:
            if record.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                if current_job is None:
                    current_job = record
            else:
                if last_job is None:
                    last_job = record

        # 4. Executor
        focus_job = current_job or (recent_records[0] if recent_records else None)
        executor_dict: dict[str, Any] = {
            "executor": focus_job.executor if focus_job else None,
            "model": focus_job.executor_model if focus_job else None,
            "quota_state": focus_job.executor_quota_state if focus_job else None,
        }
        # Quota cache from antigravity
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

        # 5. Git
        git_dict = None
        git_target = current_job or last_job
        if git_target is not None:
            try:
                repo = self._container.projects.repositories.get(
                    git_target.project_id, git_target.repository_id
                )
                git_dict = await self._git_provider.snapshot(repo)
            except Exception:
                git_dict = None

        # 6. Coordinator wake
        wake_dict = await self._container.coordinator.operator_snapshot(channel_id)

        # 7. System state
        wake_delivery_settings = settings.coordinator_wake_delivery
        system_dict = {
            "memory": memory_snapshot(),
            "disk": disk_snapshot(),
            "load": load_snapshot(),
            "uptime_seconds": uptime_seconds(),
            "process_counts": process_counts(),
            "wake_transport": {
                "enabled": wake_delivery_settings.enabled,
                "primary_transport": wake_delivery_settings.primary_transport,
                "poll_interval_seconds": wake_delivery_settings.poll_interval_seconds,
            },
        }

        return {
            "bridge": bridge_info,
            "route": route_dict,
            "progress": progress_dict,
            "jobs": {
                "recent": recent_dicts,
                "current": current_job.status_dict() if current_job else None,
                "last": last_job.status_dict() if last_job and current_job is None else None,
                "active_count": sum(1 for r in recent_records if r.status in (JobStatus.QUEUED, JobStatus.RUNNING)),
            },
            "executor": executor_dict,
            "git": git_dict,
            "wake": wake_dict,
            "system": system_dict,
        }

    async def terminal_tail(self, job_id: str | None = None) -> dict[str, Any]:
        tail_bytes = self._container.settings.operator_dashboard.terminal_tail_bytes
        store = getattr(self._container.jobs, "store", None)
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
            recent = store.recent(5)
            for r in recent:
                if r.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                    target_id = r.job_id
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
