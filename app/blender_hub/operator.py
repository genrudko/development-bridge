from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import Event, RLock
from typing import Any


@dataclass(frozen=True, slots=True)
class OperatorPrompt:
    operation_id: str
    question: str
    choices: tuple[str, ...] | None = None
    context: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class OperatorNotification:
    operation_id: str
    message: str
    context: Mapping[str, object] | None = None


@dataclass(slots=True)
class _PendingPrompt:
    prompt: OperatorPrompt
    loop: asyncio.AbstractEventLoop
    future: asyncio.Future[Any]


class OperatorBroker:
    """Coordinate same-turn operator prompts across async and UI threads."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._pending: dict[str, _PendingPrompt] = {}
        self._notifications: list[OperatorNotification] = []

    async def ask(self, prompt: OperatorPrompt, *, timeout: float | None = None) -> Any:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        pending = _PendingPrompt(prompt=prompt, loop=loop, future=future)
        with self._lock:
            if prompt.operation_id in self._pending:
                raise ValueError(f"operation already pending: {prompt.operation_id}")
            self._pending[prompt.operation_id] = pending
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            with self._lock:
                if self._pending.get(prompt.operation_id) is pending:
                    self._pending.pop(prompt.operation_id, None)

    def submit_answer(self, operation_id: str, answer: object) -> bool:
        with self._lock:
            pending = self._pending.get(operation_id)
        if pending is None:
            return False

        return self._transition(pending, lambda: pending.future.set_result(answer))

    def cancel(self, operation_id: str) -> bool:
        with self._lock:
            pending = self._pending.get(operation_id)
        if pending is None:
            return False
        return self._transition(pending, pending.future.cancel)

    def _transition(
        self, pending: _PendingPrompt, transition: Callable[[], object]
    ) -> bool:
        result: list[bool] = []
        completed = Event()

        def complete() -> None:
            with self._lock:
                current = self._pending.get(pending.prompt.operation_id)
                if current is not pending or pending.future.done():
                    won = False
                else:
                    transition()
                    won = True
                if self._pending.get(pending.prompt.operation_id) is pending:
                    self._pending.pop(pending.prompt.operation_id, None)
            result.append(won)
            completed.set()

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is pending.loop:
            complete()
        else:
            pending.loop.call_soon_threadsafe(complete)
            completed.wait()
        return result[0]

    def notify(self, notification: OperatorNotification) -> None:
        with self._lock:
            self._notifications.append(notification)

    def pending_prompts(self) -> tuple[OperatorPrompt, ...]:
        with self._lock:
            return tuple(item.prompt for item in self._pending.values())

    def notifications(self) -> tuple[OperatorNotification, ...]:
        with self._lock:
            return tuple(self._notifications)
