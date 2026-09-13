import asyncio
from threading import Thread

import pytest

from app.blender_hub.operator import OperatorBroker, OperatorNotification, OperatorPrompt


@pytest.mark.asyncio
async def test_ask_exposes_structured_prompt_until_thread_submits_answer():
    broker = OperatorBroker()
    prompt = OperatorPrompt(
        operation_id="op_mesh_1",
        question="Apply modifiers?",
        choices=("apply", "cancel"),
        context={"object": "Cube"},
    )
    call = asyncio.create_task(broker.ask(prompt, timeout=1))
    await asyncio.sleep(0)

    assert broker.pending_prompts() == (prompt,)
    submitted: list[bool] = []
    thread = Thread(target=lambda: submitted.append(broker.submit_answer("op_mesh_1", "apply")))
    thread.start()
    thread.join()

    assert await call == "apply"
    assert submitted == [True]
    assert broker.pending_prompts() == ()
    assert broker.submit_answer("op_mesh_1", "late") is False


@pytest.mark.asyncio
async def test_timeout_removes_prompt_and_rejects_stale_answer():
    broker = OperatorBroker()
    prompt = OperatorPrompt("op_timeout", "Continue?")

    with pytest.raises(TimeoutError):
        await broker.ask(prompt, timeout=0.01)

    assert broker.pending_prompts() == ()
    assert broker.submit_answer("op_timeout", True) is False


@pytest.mark.asyncio
async def test_task_cancellation_removes_prompt_and_rejects_stale_answer():
    broker = OperatorBroker()
    prompt = OperatorPrompt("op_cancel", "Continue?")
    call = asyncio.create_task(broker.ask(prompt))
    await asyncio.sleep(0)

    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call

    assert broker.pending_prompts() == ()
    assert broker.submit_answer("op_cancel", True) is False


@pytest.mark.asyncio
async def test_explicit_cancel_unblocks_same_ask_with_cancellation():
    broker = OperatorBroker()
    call = asyncio.create_task(
        broker.ask(OperatorPrompt("op_explicit", "Continue?"), timeout=1)
    )
    await asyncio.sleep(0)

    assert broker.cancel("op_explicit") is True
    with pytest.raises(asyncio.CancelledError):
        await call
    assert broker.cancel("op_explicit") is False


def test_notify_records_structured_notification_without_waiting():
    broker = OperatorBroker()
    notification = OperatorNotification(
        operation_id="op_done",
        message="Export complete",
        context={"path": "part.stl"},
    )

    result = broker.notify(notification)

    assert result is None
    assert broker.notifications() == (notification,)
