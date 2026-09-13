import asyncio
import time
from threading import Event, Thread

import pytest

from app.blender_hub.operator import (
    OperatorBroker,
    OperatorNotification,
    OperatorPrompt,
    _PendingPrompt,
)


def _pending_on_inactive_loop(
    broker: OperatorBroker, operation_id: str, *, close: bool
):
    loop = asyncio.new_event_loop()
    prompt = OperatorPrompt(operation_id, "Continue?")
    future = loop.create_future()
    pending = _PendingPrompt(prompt=prompt, loop=loop, future=future)
    broker._pending[operation_id] = pending
    if close:
        loop.close()
    return loop, future


def _invoke_transition(broker: OperatorBroker, action: str, operation_id: str) -> bool:
    if action == "answer":
        return broker.submit_answer(operation_id, "yes")
    return broker.cancel(operation_id)


@pytest.mark.parametrize("action", ["answer", "cancel"])
def test_cross_thread_transition_rejects_closed_loop_and_cleans_pending(action):
    broker = OperatorBroker()
    _, future = _pending_on_inactive_loop(broker, f"op_closed_{action}", close=True)

    assert _invoke_transition(broker, action, f"op_closed_{action}") is False
    assert broker.pending_prompts() == ()
    assert not future.done()


@pytest.mark.parametrize("action", ["answer", "cancel"])
def test_cross_thread_transition_rejects_stopped_loop_promptly(action):
    broker = OperatorBroker(transition_ack_timeout=0.01)
    loop, future = _pending_on_inactive_loop(
        broker, f"op_stopped_{action}", close=False
    )
    started = time.monotonic()
    try:
        assert _invoke_transition(broker, action, f"op_stopped_{action}") is False
        assert time.monotonic() - started < 0.25
        assert broker.pending_prompts() == ()
        assert not future.done()
    finally:
        loop.close()


@pytest.mark.parametrize("action", ["answer", "cancel"])
def test_cross_thread_transition_handles_scheduling_runtime_error(action, monkeypatch):
    broker = OperatorBroker()
    loop, future = _pending_on_inactive_loop(
        broker, f"op_schedule_error_{action}", close=False
    )
    real_is_running = loop.is_running
    monkeypatch.setattr(loop, "is_running", lambda: True)

    def reject_schedule(callback) -> None:
        raise RuntimeError("loop closed during scheduling")

    monkeypatch.setattr(loop, "call_soon_threadsafe", reject_schedule)
    try:
        assert _invoke_transition(broker, action, f"op_schedule_error_{action}") is False
        assert broker.pending_prompts() == ()
        assert not future.done()
    finally:
        monkeypatch.setattr(loop, "is_running", real_is_running)
        loop.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["answer", "cancel"])
async def test_expired_cross_thread_transition_callback_cannot_mutate_future(
    monkeypatch, action
):
    broker = OperatorBroker(transition_ack_timeout=0.01)
    operation_id = f"op_late_{action}"
    call = asyncio.create_task(broker.ask(OperatorPrompt(operation_id, "Continue?")))
    await asyncio.sleep(0)
    loop = asyncio.get_running_loop()
    scheduled = []
    callback_scheduled = Event()

    def capture(callback) -> None:
        scheduled.append(callback)
        callback_scheduled.set()

    monkeypatch.setattr(loop, "call_soon_threadsafe", capture)
    results: list[bool] = []
    thread = Thread(
        target=lambda: results.append(_invoke_transition(broker, action, operation_id))
    )
    thread.start()
    assert callback_scheduled.wait(timeout=1)
    thread.join(timeout=1)
    assert not thread.is_alive()
    assert results == [False]
    assert broker.pending_prompts() == ()
    assert not call.done()

    scheduled.pop()()
    assert not call.done()

    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call


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

    assert await call == "apply"
    thread.join(timeout=1)
    assert not thread.is_alive()
    assert submitted == [True]
    assert broker.pending_prompts() == ()
    assert broker.submit_answer("op_mesh_1", "late") is False


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["answer", "cancel"])
async def test_healthy_cross_thread_transition_reports_true_only_after_winning(action):
    broker = OperatorBroker()
    operation_id = f"op_healthy_{action}"
    call = asyncio.create_task(broker.ask(OperatorPrompt(operation_id, "Continue?")))
    await asyncio.sleep(0)
    results: list[bool] = []
    thread = Thread(
        target=lambda: results.append(_invoke_transition(broker, action, operation_id))
    )
    thread.start()
    if action == "answer":
        assert await call == "yes"
    else:
        with pytest.raises(asyncio.CancelledError):
            await call
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert results == [True]
    assert broker.pending_prompts() == ()


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


@pytest.mark.asyncio
async def test_operation_id_stays_reserved_until_queued_answer_wins(monkeypatch):
    broker = OperatorBroker()
    prompt = OperatorPrompt("op_reuse", "Continue?")
    call = asyncio.create_task(broker.ask(prompt))
    await asyncio.sleep(0)
    loop = asyncio.get_running_loop()
    scheduled = []
    callback_scheduled = Event()
    real_call_soon_threadsafe = loop.call_soon_threadsafe

    def capture(callback) -> None:
        scheduled.append(callback)
        callback_scheduled.set()

    monkeypatch.setattr(loop, "call_soon_threadsafe", capture)
    submitted: list[bool] = []
    finished = Event()

    def submit() -> None:
        submitted.append(broker.submit_answer("op_reuse", "yes"))
        finished.set()

    thread = Thread(target=submit)
    thread.start()
    assert callback_scheduled.wait(timeout=1)
    assert not finished.is_set()
    assert broker.pending_prompts() == (prompt,)
    with pytest.raises(ValueError, match="operation already pending"):
        await broker.ask(OperatorPrompt("op_reuse", "Replacement?"))

    monkeypatch.setattr(loop, "call_soon_threadsafe", real_call_soon_threadsafe)
    scheduled.pop()()
    thread.join(timeout=1)
    assert not thread.is_alive()
    assert submitted == [True]
    assert await call == "yes"
    assert broker.pending_prompts() == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["answer", "cancel"])
async def test_cross_thread_transition_reports_false_when_task_cancellation_wins(
    monkeypatch, action
):
    broker = OperatorBroker()
    call = asyncio.create_task(broker.ask(OperatorPrompt("op_race", "Continue?")))
    await asyncio.sleep(0)
    loop = asyncio.get_running_loop()
    scheduled = []
    callback_scheduled = Event()
    real_call_soon_threadsafe = loop.call_soon_threadsafe

    def capture(callback) -> None:
        scheduled.append(callback)
        callback_scheduled.set()

    monkeypatch.setattr(loop, "call_soon_threadsafe", capture)
    submitted: list[bool] = []
    thread = Thread(
        target=lambda: submitted.append(
            _invoke_transition(broker, action, "op_race")
        )
    )
    thread.start()
    assert callback_scheduled.wait(timeout=1)

    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call
    monkeypatch.setattr(loop, "call_soon_threadsafe", real_call_soon_threadsafe)
    scheduled.pop()()
    thread.join(timeout=1)

    assert submitted == [False]
    assert broker.pending_prompts() == ()


@pytest.mark.asyncio
async def test_same_loop_answer_completes_without_deadlock():
    broker = OperatorBroker()
    call = asyncio.create_task(broker.ask(OperatorPrompt("op_loop", "Continue?")))
    await asyncio.sleep(0)

    assert broker.submit_answer("op_loop", "yes") is True
    assert await call == "yes"


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
