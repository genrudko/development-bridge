import pytest
from app.coordinator.service import CoordinatorService


@pytest.mark.asyncio
async def test_coordinator_operator_snapshot_idle():
    coordinator = CoordinatorService()
    snapshot = await coordinator.operator_snapshot("test-channel")
    assert snapshot["channel_id"] == "test-channel"
    assert snapshot["state"] == "idle"
    assert snapshot["continuation_id"] is None
    assert snapshot["transport_delivered"] is False
    assert snapshot["owner_input_required"] is False
    assert snapshot["batch_size"] == 0
    assert snapshot["queued_events"] == 0


@pytest.mark.asyncio
async def test_coordinator_operator_snapshot_pending_and_read_only():
    coordinator = CoordinatorService()
    armed = await coordinator.arm_resilient("test message", channel_id="ops-channel")
    continuation_id = armed["continuation_id"]

    snapshot = await coordinator.operator_snapshot("ops-channel")
    assert snapshot["channel_id"] == "ops-channel"
    assert snapshot["continuation_id"] == continuation_id
    assert snapshot["state"] in {"pending", "web_cooldown"}
    assert snapshot["delivery_attempts"] == 0
    assert snapshot["max_delivery_attempts"] == 3
    assert snapshot["transport_delivered"] is False
    assert snapshot["owner_input_required"] is False
    assert snapshot["batch_size"] == 1
    assert snapshot["queued_events"] == 0

    # Ensure it did not claim, ACK, or mutate
    snapshot2 = await coordinator.operator_snapshot("ops-channel")
    assert snapshot2 == snapshot


@pytest.mark.asyncio
async def test_coordinator_operator_snapshot_with_transport_info():
    coordinator = CoordinatorService()
    await coordinator.arm_resilient("msg", channel_id="chan")
    claimed = await coordinator.claim("chan", delivery_mode="direct")
    claim_id = claimed["claim_id"]

    await coordinator.finalize_transport(
        "chan",
        claim_id,
        "review-gpt",
        "owner_input_required",
        detail="Login required on ChatGPT",
    )

    snapshot = await coordinator.operator_snapshot("chan")
    assert snapshot["state"] == "owner_input_required"
    assert snapshot["last_transport_name"] == "review-gpt"
    assert snapshot["last_transport_disposition"] == "owner_input_required"
    assert snapshot["last_transport_detail"] == "Login required on ChatGPT"
    assert snapshot["owner_input_required"] is True
