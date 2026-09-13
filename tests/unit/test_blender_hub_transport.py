import pytest

from app.blender_hub.transport import (
    CallKind,
    TransportFailure,
    TransportOutcome,
    dispatch_with_replay_policy,
)


@pytest.mark.asyncio
async def test_mutating_transport_loss_is_uncertain_and_never_replayed():
    attempts = 0
    reconnects = 0

    async def dispatch():
        nonlocal attempts
        attempts += 1
        raise TransportFailure("connection lost after dispatch")

    async def reconnect():
        nonlocal reconnects
        reconnects += 1

    result = await dispatch_with_replay_policy(CallKind.MUTATION, dispatch, reconnect)

    assert result.outcome is TransportOutcome.UNCERTAIN
    assert result.error == "connection lost after dispatch"
    assert result.attempts == attempts == 1
    assert result.reconnects == reconnects == 0


@pytest.mark.asyncio
async def test_idempotent_read_reconnects_and_retries_at_most_once():
    attempts = 0
    reconnects = 0

    async def dispatch():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TransportFailure("dropped")
        return {"objects": 3}

    async def reconnect():
        nonlocal reconnects
        reconnects += 1

    result = await dispatch_with_replay_policy(
        CallKind.IDEMPOTENT_READ, dispatch, reconnect
    )

    assert result.outcome is TransportOutcome.SUCCESS
    assert result.value == {"objects": 3}
    assert result.attempts == attempts == 2
    assert result.reconnects == reconnects == 1


@pytest.mark.asyncio
async def test_idempotent_read_stops_after_one_failed_retry():
    attempts = 0
    reconnects = 0

    async def dispatch():
        nonlocal attempts
        attempts += 1
        raise TransportFailure(f"drop {attempts}")

    async def reconnect():
        nonlocal reconnects
        reconnects += 1

    result = await dispatch_with_replay_policy(
        CallKind.IDEMPOTENT_READ, dispatch, reconnect
    )

    assert result.outcome is TransportOutcome.FAILED
    assert result.error == "drop 2"
    assert result.attempts == attempts == 2
    assert result.reconnects == reconnects == 1


@pytest.mark.asyncio
async def test_non_idempotent_read_transport_loss_is_not_replayed():
    attempts = 0
    reconnects = 0

    async def dispatch():
        nonlocal attempts
        attempts += 1
        raise TransportFailure("dropped")

    async def reconnect():
        nonlocal reconnects
        reconnects += 1

    result = await dispatch_with_replay_policy(
        CallKind.NON_IDEMPOTENT_READ, dispatch, reconnect
    )

    assert result.outcome is TransportOutcome.FAILED
    assert result.attempts == attempts == 1
    assert result.reconnects == reconnects == 0
