import asyncio
import threading

import pytest

from app.blender_bridge.operator_inbox import OperatorInboxBackend


@pytest.mark.asyncio
async def test_gui_thread_answer_resolves_same_pending_async_request():
    backend = OperatorInboxBackend()
    task = asyncio.create_task(
        backend.ask({
            "question": "Keep variant?",
            "choices": ["A", "B"],
            "operation_id": "op_42",
        })
    )
    await asyncio.sleep(0)

    prompt = backend.next_prompt()
    assert prompt is not None
    assert prompt.question == "Keep variant?"
    assert prompt.choices == ("A", "B")
    assert prompt.operation_id == "op_42"
    assert not task.done()

    answered = []
    thread = threading.Thread(
        target=lambda: answered.append(backend.answer(prompt.prompt_id, "B"))
    )
    thread.start()
    thread.join()

    result = await asyncio.wait_for(task, 1)
    assert answered == [True]
    assert result == {
        "status": "answered",
        "prompt_id": prompt.prompt_id,
        "operation_id": "op_42",
        "value": "B",
    }
    assert backend.answer(prompt.prompt_id, "late") is False


@pytest.mark.asyncio
async def test_cancelled_prompt_is_not_later_presented_to_gui():
    backend = OperatorInboxBackend()
    task = asyncio.create_task(backend.ask({"question": "Pick face"}))
    await asyncio.sleep(0)
    prompt_id = backend.pending_prompt_ids()[0]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert backend.answer(prompt_id, "late") is False
    assert backend.next_prompt() is None


@pytest.mark.asyncio
async def test_operator_inbox_timeout_returns_structured_timeout_and_cleans_pending():
    backend = OperatorInboxBackend(timeout_seconds=0.001)

    result = await backend.ask({"question": "Still there?"})

    assert result["status"] == "timeout"
    assert result["value"] is None
    assert backend.pending_prompt_ids() == ()
    assert backend.next_prompt() is None
