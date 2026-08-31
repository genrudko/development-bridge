from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import pytest

from app.coordinator.routes import RouteRegistry
from app.coordinator.service import CoordinatorService
from app.coordinator.wake_delivery import CoordinatorWakeDeliveryService
from app.coordinator.wake_transport import (
    WakeDeliveryDisposition,
    WakeDeliveryRequest,
    WakeDeliveryResult,
    WakeProbeResult,
    WakeTarget,
    WakeTransport,
)


@dataclass
class MockWakeTransport:
    name: str = "mock-transport"
    probe_results: list[WakeProbeResult] = None
    deliver_results: list[WakeDeliveryResult] = None
    probe_calls: list[WakeTarget] = None
    deliver_calls: list[WakeDeliveryRequest] = None
    probe_exception: Exception | None = None
    deliver_exception: Exception | None = None

    def __post_init__(self):
        if self.probe_results is None:
            self.probe_results = []
        if self.deliver_results is None:
            self.deliver_results = []
        if self.probe_calls is None:
            self.probe_calls = []
        if self.deliver_calls is None:
            self.deliver_calls = []

    async def probe(self, target: WakeTarget) -> WakeProbeResult:
        self.probe_calls.append(target)
        if self.probe_exception is not None:
            raise self.probe_exception
        if self.probe_results:
            return self.probe_results.pop(0)
        return WakeProbeResult(ready=True)

    async def deliver(self, request: WakeDeliveryRequest) -> WakeDeliveryResult:
        self.deliver_calls.append(request)
        if self.deliver_exception is not None:
            raise self.deliver_exception
        if self.deliver_results:
            return self.deliver_results.pop(0)
        return WakeDeliveryResult(disposition="delivered")


@pytest.fixture
def coordinator(tmp_path: Path) -> CoordinatorService:
    return CoordinatorService(
        tmp_path / "coordinator-wakes.json",
        browser_preflight_required=True,
    )


@pytest.fixture
def route_registry(tmp_path: Path) -> RouteRegistry:
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "main",
        "https://chatgpt.com/g-p-test-proj/c/67890-uuid",
        "coordinator",
        "Main Route",
    )
    return registry


@pytest.mark.asyncio
async def test_disabled_service_start_creates_no_task_and_makes_no_calls(
    coordinator: CoordinatorService,
    route_registry: RouteRegistry,
):
    transport = MockWakeTransport()
    service = CoordinatorWakeDeliveryService(
        coordinator,
        route_registry,
        transport=transport,
        enabled=False,
    )
    await service.start()
    assert not service.is_running
    await service.run_once()
    assert len(transport.probe_calls) == 0
    assert len(transport.deliver_calls) == 0
    await service.stop()


@pytest.mark.asyncio
async def test_exact_route_mapping_passes_route_url_and_conversation_id(
    coordinator: CoordinatorService,
    route_registry: RouteRegistry,
):
    await coordinator.arm_resilient("Job done", channel_id="coordinator")
    transport = MockWakeTransport()
    service = CoordinatorWakeDeliveryService(
        coordinator,
        route_registry,
        transport=transport,
        enabled=True,
    )

    await service.run_once()

    assert len(transport.probe_calls) == 1
    assert transport.probe_calls[0].route_id == "main"
    assert transport.probe_calls[0].channel_id == "coordinator"
    assert transport.probe_calls[0].conversation_id == "67890-uuid"
    assert transport.probe_calls[0].route_url == "https://chatgpt.com/g-p-test-proj/c/67890-uuid"

    assert len(transport.deliver_calls) == 1
    assert transport.deliver_calls[0].target == transport.probe_calls[0]
    assert transport.deliver_calls[0].continuation_id.startswith("cont_")
    assert transport.deliver_calls[0].delivery_key == transport.deliver_calls[0].continuation_id
    assert "DBRIDGE_CONTINUE" in transport.deliver_calls[0].prompt


@pytest.mark.asyncio
async def test_transient_busy_probe_consumes_no_claim_or_attempt(
    coordinator: CoordinatorService,
    route_registry: RouteRegistry,
):
    await coordinator.arm_resilient("Job done", channel_id="coordinator")
    transport = MockWakeTransport(
        probe_results=[WakeProbeResult(ready=False, owner_input_required=False, detail="ChatGPT busy")]
    )
    service = CoordinatorWakeDeliveryService(
        coordinator,
        route_registry,
        transport=transport,
        enabled=True,
    )

    await service.run_once()

    assert len(transport.probe_calls) == 1
    assert len(transport.deliver_calls) == 0

    status = await coordinator.status("coordinator", delivery_mode="direct")
    assert status["ready"] is True
    assert status["delivery_attempts"] == 0
    assert status["state"] == "pending"


@pytest.mark.asyncio
async def test_probe_exception_leaves_pending_without_consuming_attempt(
    coordinator: CoordinatorService,
    route_registry: RouteRegistry,
):
    await coordinator.arm_resilient("Job done", channel_id="coordinator")
    transport = MockWakeTransport(probe_exception=RuntimeError("CDP connection failed"))
    service = CoordinatorWakeDeliveryService(
        coordinator,
        route_registry,
        transport=transport,
        enabled=True,
    )

    await service.run_once()

    assert len(transport.probe_calls) == 1
    assert len(transport.deliver_calls) == 0

    status = await coordinator.status("coordinator", delivery_mode="direct")
    assert status["ready"] is True
    assert status["delivery_attempts"] == 0


@pytest.mark.asyncio
async def test_owner_input_probe_persists_owner_input_required_and_never_calls_deliver(
    coordinator: CoordinatorService,
    route_registry: RouteRegistry,
):
    await coordinator.arm_resilient("Job done", channel_id="coordinator")
    transport = MockWakeTransport(
        probe_results=[WakeProbeResult(ready=False, owner_input_required=True, detail="Cloudflare challenge")]
    )
    service = CoordinatorWakeDeliveryService(
        coordinator,
        route_registry,
        transport=transport,
        enabled=True,
    )

    await service.run_once()

    assert len(transport.probe_calls) == 1
    assert len(transport.deliver_calls) == 0

    status = await coordinator.status("coordinator", delivery_mode="direct")
    assert status["ready"] is False
    assert status["state"] == "owner_input_required"
    assert status["owner_input_required"] is True
    assert status["last_transport_name"] == "mock-transport"
    assert status["last_transport_disposition"] == "owner_input_required"
    assert status["last_transport_detail"] == "Cloudflare challenge"


@pytest.mark.asyncio
async def test_delivered_result_maps_to_waiting_model_ack_and_transport_delivered(
    coordinator: CoordinatorService,
    route_registry: RouteRegistry,
):
    await coordinator.arm_resilient("Job done", channel_id="coordinator")
    transport = MockWakeTransport(
        deliver_results=[WakeDeliveryResult(disposition="delivered", detail="Turn sent")]
    )
    service = CoordinatorWakeDeliveryService(
        coordinator,
        route_registry,
        transport=transport,
        enabled=True,
    )

    await service.run_once()

    assert len(transport.deliver_calls) == 1
    status = await coordinator.status("coordinator", delivery_mode="direct")
    assert status["transport_delivered"] is True
    assert status["state"] == "waiting_model_ack"
    assert status["last_transport_disposition"] == "delivered"


@pytest.mark.asyncio
async def test_not_submitted_maps_to_released_retryable_state(
    coordinator: CoordinatorService,
    route_registry: RouteRegistry,
    monkeypatch: pytest.MonkeyPatch,
):
    clock = [1000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    await coordinator.arm_resilient(
        "Job done",
        channel_id="coordinator",
        retry_delays_seconds=(10.0, 20.0),
    )
    transport = MockWakeTransport(
        deliver_results=[WakeDeliveryResult(disposition="not_submitted", detail="Network reset before send")]
    )
    service = CoordinatorWakeDeliveryService(
        coordinator,
        route_registry,
        transport=transport,
        enabled=True,
    )

    await service.run_once()

    assert len(transport.deliver_calls) == 1
    status = await coordinator.status("coordinator", delivery_mode="direct")
    assert status["transport_delivered"] is False
    assert status["delivery_attempts"] == 1
    assert status["last_transport_disposition"] == "not_submitted"
    assert status["ready"] is False

    # After lease expires + retry delay passes, the wake is eligible for retry
    clock[0] = 1035.0
    status_retry = await coordinator.status("coordinator", delivery_mode="direct")
    assert status_retry["ready"] is True



@pytest.mark.asyncio
async def test_uncertain_maps_to_durable_blocked_state_and_no_resend(
    coordinator: CoordinatorService,
    route_registry: RouteRegistry,
):
    await coordinator.arm_resilient("Job done", channel_id="coordinator")
    transport = MockWakeTransport(
        deliver_results=[WakeDeliveryResult(disposition="uncertain", detail="Timeout during submit")]
    )
    service = CoordinatorWakeDeliveryService(
        coordinator,
        route_registry,
        transport=transport,
        enabled=True,
    )

    await service.run_once()
    assert len(transport.deliver_calls) == 1

    status = await coordinator.status("coordinator", delivery_mode="direct")
    assert status["ready"] is False
    assert status["state"] == "transport_uncertain"
    assert status["last_transport_disposition"] == "uncertain"

    # Second run_once must not deliver again
    await service.run_once()
    assert len(transport.deliver_calls) == 1


@pytest.mark.asyncio
async def test_unexpected_deliver_exception_maps_to_uncertain_and_no_resend(
    coordinator: CoordinatorService,
    route_registry: RouteRegistry,
):
    await coordinator.arm_resilient("Job done", channel_id="coordinator")
    transport = MockWakeTransport(deliver_exception=RuntimeError("Subprocess crashed unexpectedly"))
    service = CoordinatorWakeDeliveryService(
        coordinator,
        route_registry,
        transport=transport,
        enabled=True,
    )

    await service.run_once()
    assert len(transport.deliver_calls) == 1

    status = await coordinator.status("coordinator", delivery_mode="direct")
    assert status["ready"] is False
    assert status["state"] == "transport_uncertain"
    assert status["last_transport_disposition"] == "uncertain"
    assert "Subprocess crashed" in status["last_transport_detail"]

    # Second cycle must NOT resend
    await service.run_once()
    assert len(transport.deliver_calls) == 1


@pytest.mark.asyncio
async def test_strictly_single_lane_one_delivery_per_cycle(
    coordinator: CoordinatorService,
    route_registry: RouteRegistry,
    monkeypatch: pytest.MonkeyPatch,
):
    clock = [1000.0]
    monkeypatch.setattr("app.coordinator.service.time.time", lambda: clock[0])
    route_registry.bootstrap(
        "second",
        "https://chatgpt.com/g-p-second-proj/c/11111-uuid",
        "channel-two",
        "Second Route",
    )
    await coordinator.arm_resilient("Job 1", channel_id="coordinator")
    await coordinator.arm_resilient("Job 2", channel_id="channel-two")

    transport = MockWakeTransport()
    service = CoordinatorWakeDeliveryService(
        coordinator,
        route_registry,
        transport=transport,
        enabled=True,
    )

    # In one cycle, only one delivery is attempted
    await service.run_once()
    assert len(transport.deliver_calls) == 1

    # In the second cycle, after web cooldown passes, the second route is attempted
    clock[0] = 1035.0
    await service.run_once()
    assert len(transport.deliver_calls) == 2



def test_prompt_formatting_and_bounded_reason(
    coordinator: CoordinatorService,
    route_registry: RouteRegistry,
):
    service = CoordinatorWakeDeliveryService(
        coordinator,
        route_registry,
        enabled=True,
    )
    prompt = service.build_continuation_prompt(
        "cont_test123",
        "  Task completed successfully. \n\n Extra whitespace \t here.  " + "A" * 1000,
    )
    assert prompt.startswith(
        "DBRIDGE_CONTINUE cont_test123. Call coordinator_ack for this continuation_id, "
        "process any batched messages it returns, inspect the durable Bridge job/result state, "
        "and continue the current bounded task."
    )
    prefix = (
        "DBRIDGE_CONTINUE cont_test123. Call coordinator_ack for this continuation_id, "
        "process any batched messages it returns, inspect the durable Bridge job/result state, "
        "and continue the current bounded task."
    )
    reason = prompt[len(prefix) :].strip()
    assert len(reason) <= 500
    assert "\n" not in reason
    assert "\t" not in reason


@pytest.mark.asyncio
async def test_start_and_stop_lifecycle_is_idempotent(
    coordinator: CoordinatorService,
    route_registry: RouteRegistry,
):
    transport = MockWakeTransport()
    service = CoordinatorWakeDeliveryService(
        coordinator,
        route_registry,
        transport=transport,
        enabled=True,
        poll_interval_seconds=0.1,
    )

    await service.start()
    assert service.is_running
    task = service._task

    # Repeated start is idempotent
    await service.start()
    assert service._task is task

    # Stop cancels and cleans up
    await service.stop()
    assert not service.is_running
    assert service._task is None

    # Repeated stop is idempotent
    await service.stop()
    assert not service.is_running


@pytest.mark.asyncio
async def test_skips_malformed_routes_before_claim(
    coordinator: CoordinatorService,
    tmp_path: Path,
):
    # Setup registry with missing fields
    reg_path = tmp_path / "routes.json"
    reg_path.write_text(
        '{"version": 1, "default_route": "bad", "routes": {"bad": {"route_id": "bad", "url": "https://chatgpt.com/c/123"}}}',
        encoding="utf-8",
    )
    route_registry = RouteRegistry(reg_path)
    transport = MockWakeTransport()
    service = CoordinatorWakeDeliveryService(
        coordinator,
        route_registry,
        transport=transport,
        enabled=True,
    )
    await service.run_once()
    assert len(transport.probe_calls) == 0
    assert len(transport.deliver_calls) == 0


def test_container_disabled_default_has_none_wake_delivery():
    from app.container import build_container
    from app.settings import BridgeSettings

    container = build_container(BridgeSettings())
    assert container.coordinator_wake_delivery is None


def test_container_enabled_constructs_wake_delivery_service(tmp_path: Path):
    from app.container import build_container
    from app.settings import BridgeSettings

    settings = BridgeSettings.model_validate({
        "coordinator_wake_delivery": {
            "enabled": True,
            "review_gpt": {
                "node_executable": "/usr/bin/node",
                "cli_path": "/opt/review-gpt/dist/cli.js",
                "config_path": "/opt/review-gpt/config.json",
                "browser_endpoint": "http://127.0.0.1:9222",
                "receipt_directory": tmp_path / "receipts",
            },
        }
    })
    container = build_container(settings)
    assert container.coordinator_wake_delivery is not None
    assert container.coordinator_wake_delivery.enabled is True
    assert container.coordinator_wake_delivery.transport is not None
    assert container.coordinator_wake_delivery.transport.name == "review-gpt"


@pytest.mark.asyncio
async def test_runtime_lifespan_starts_and_stops_wake_delivery(
    coordinator: CoordinatorService,
    route_registry: RouteRegistry,
):
    from app.container import ApplicationContainer
    from app.runtime import create_server
    from app.settings import BridgeSettings

    transport = MockWakeTransport()
    wake_service = CoordinatorWakeDeliveryService(
        coordinator,
        route_registry,
        transport=transport,
        enabled=True,
        poll_interval_seconds=0.1,
    )

    # Build container with mock wake delivery
    from app.container import build_container
    container = build_container(
        BridgeSettings(),
        review_gpt_transport=transport,
    )
    # inject the wake delivery service
    container = ApplicationContainer(
        settings=container.settings,
        projects=container.projects,
        managed_repositories=container.managed_repositories,
        capability_policy=container.capability_policy,
        audit=container.audit,
        git=container.git,
        git_write=container.git_write,
        git_workspace=container.git_workspace,
        files=container.files,
        changes=container.changes,
        tasks=container.tasks,
        jobs=container.jobs,
        executors=container.executors,
        job_artifact_exports=container.job_artifact_exports,
        github=container.github,
        github_artifact_exports=container.github_artifact_exports,
        oauth=container.oauth,
        knowledge=container.knowledge,
        telegram_knowledge=container.telegram_knowledge,
        telegram_supervisor=container.telegram_supervisor,
        knowledge_attachments=container.knowledge_attachments,
        knowledge_attachment_exports=container.knowledge_attachment_exports,
        chatgpt_share=container.chatgpt_share,
        coordinator=coordinator,
        route_registry=route_registry,
        commands=container.commands,
        bridge_restart=container.bridge_restart,
        desktop_nodes=container.desktop_nodes,
        coordinator_wake_delivery=wake_service,
    )

    server = create_server(container)
    assert not wake_service.is_running
    async with server.lifespan(server):
        assert wake_service.is_running
    assert not wake_service.is_running


