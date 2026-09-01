import time
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.container import ApplicationContainer
from app.jobs.models import JobRecord, JobStatus
from app.ops.service import OperatorDashboardService
from app.settings import BridgeSettings


@pytest.fixture
def container_mock(tmp_path):
    container = MagicMock(spec=ApplicationContainer)
    container.settings = BridgeSettings()

    # projects
    repo = MagicMock()
    repo.project_id = "proj-1"
    repo.id = "repo-1"
    project = MagicMock()
    project.id = "proj-1"
    project.repositories = [repo]
    container.projects.list.return_value = [project]
    container.projects.repositories.get.return_value = repo

    # route_registry
    container.route_registry.path = tmp_path / "routes.json"
    container.route_registry.snapshot.return_value = {"requested_route": "bridge"}
    container.route_registry.resolve.return_value = {
        "route_id": "bridge",
        "channel_id": "coordinator",
        "title": "Development Bridge",
        "generation": 1,
    }

    # coordinator
    container.coordinator.operator_snapshot = AsyncMock(return_value={
        "channel_id": "coordinator",
        "state": "idle",
        "continuation_id": None,
        "delivery_attempts": 0,
        "max_delivery_attempts": 1,
        "transport_delivered": False,
        "transport_delivered_at": None,
        "last_transport_name": None,
        "last_transport_disposition": None,
        "last_transport_detail": None,
        "owner_input_required": False,
        "batch_size": 0,
        "queued_events": 0,
        "retry_after_seconds": 0.0,
        "web_backoff_seconds": 0.0,
        "web_turn_cooldown_seconds": 0.0,
        "lease_remaining_seconds": 0.0,
        "model_acknowledged": False,
    })

    # jobs
    container.jobs.store = MagicMock()
    container.jobs.store.recent.return_value = ()
    container.jobs.store.get_by_id.return_value = None

    return container


@pytest.mark.asyncio
async def test_operator_dashboard_service_snapshot_idle(container_mock):
    service = OperatorDashboardService(container_mock)
    snap = await service.snapshot()

    assert snap["bridge"]["name"] == "development-bridge"
    assert snap["bridge"]["version"] == "1.0.0"
    assert snap["bridge"]["projects_count"] == 1
    assert snap["bridge"]["repositories_count"] == 1
    assert "uptime_seconds" in snap["bridge"]

    assert snap["route"]["route_id"] == "bridge"
    assert snap["route"]["channel_id"] == "coordinator"

    assert snap["jobs"]["recent"] == []
    assert snap["jobs"]["current"] is None
    assert snap["jobs"]["last"] is None

    assert snap["wake"]["state"] == "idle"

    assert "memory" in snap["system"]
    assert "disk" in snap["system"]
    assert "load" in snap["system"]
    assert "process_counts" in snap["system"]


@pytest.mark.asyncio
async def test_operator_dashboard_service_resolves_active_and_last_jobs(container_mock):
    running_job = JobRecord(
        job_id="job_running",
        project_id="proj-1",
        repository_id="repo-1",
        task_id="build",
        request_id="req-1",
        status=JobStatus.RUNNING,
        created_at="2026-09-01T12:00:00Z",
        executor="antigravity",
        executor_model="gemini-3.1-pro",
        executor_quota_state="normal",
    )
    succeeded_job = JobRecord(
        job_id="job_succeeded",
        project_id="proj-1",
        repository_id="repo-1",
        task_id="test",
        request_id="req-0",
        status=JobStatus.SUCCEEDED,
        created_at="2026-09-01T11:00:00Z",
    )

    container_mock.jobs.store.recent.return_value = (running_job, succeeded_job)
    service = OperatorDashboardService(container_mock)
    snap = await service.snapshot()

    assert snap["jobs"]["current"]["job_id"] == "job_running"
    assert snap["jobs"]["last"] is None
    assert snap["executor"]["executor"] == "antigravity"
    assert snap["executor"]["model"] == "gemini-3.1-pro"


@pytest.mark.asyncio
async def test_operator_dashboard_service_terminal_tail(container_mock):
    job = JobRecord(
        job_id="job_123",
        project_id="proj-1",
        repository_id="repo-1",
        task_id="build",
        request_id="req-1",
        status=JobStatus.RUNNING,
        created_at="2026-09-01T12:00:00Z",
        stdout=b"line 1\nline 2\n",
        stderr=b"warning: test\n",
        stdout_truncated=False,
        stderr_truncated=False,
    )
    container_mock.jobs.store.get_by_id.return_value = job

    service = OperatorDashboardService(container_mock)
    tail = await service.terminal_tail("job_123")

    assert tail["job_id"] == "job_123"
    assert tail["status"] == "running"
    assert tail["stdout"] == "line 1\nline 2\n"
    assert tail["stderr"] == "warning: test\n"
    assert tail["stdout_truncated"] is False
    assert tail["stderr_truncated"] is False
