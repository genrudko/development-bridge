from __future__ import annotations

import asyncio
import queue
import threading
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class InboxPrompt:
    prompt_id: str
    question: str
    choices: tuple[str, ...]
    operation_id: str | None = None


@dataclass(slots=True)
class _PendingPrompt:
    prompt: InboxPrompt
    loop: asyncio.AbstractEventLoop
    future: asyncio.Future[str]


class OperatorInboxBackend:
    """Thread-safe GUI inbox that resolves the same pending async tool request."""

    def __init__(self, *, timeout_seconds: float | None = 285.0) -> None:
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive or None")
        self.timeout_seconds = timeout_seconds
        self._lock = threading.Lock()
        self._queue: queue.Queue[InboxPrompt] = queue.Queue()
        self._pending: dict[str, _PendingPrompt] = {}

    async def ask(self, arguments: dict[str, Any]) -> dict[str, Any]:
        question = arguments.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("operator question must be a non-empty string")
        raw_choices = arguments.get("choices", [])
        if not isinstance(raw_choices, list) or not all(
            isinstance(choice, str) and choice for choice in raw_choices
        ):
            raise ValueError("operator choices must be a list of non-empty strings")
        operation_id = arguments.get("operation_id")
        if operation_id is not None and not isinstance(operation_id, str):
            raise ValueError("operator operation_id must be a string")

        prompt = InboxPrompt(
            prompt_id=f"ask_{uuid4().hex}",
            question=question.strip(),
            choices=tuple(raw_choices),
            operation_id=operation_id,
        )
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        pending = _PendingPrompt(prompt=prompt, loop=loop, future=future)
        with self._lock:
            self._pending[prompt.prompt_id] = pending
        self._queue.put(prompt)

        try:
            if self.timeout_seconds is None:
                value = await future
            else:
                try:
                    value = await asyncio.wait_for(future, timeout=self.timeout_seconds)
                except TimeoutError:
                    return {
                        "status": "timeout",
                        "prompt_id": prompt.prompt_id,
                        "operation_id": prompt.operation_id,
                        "value": None,
                    }
            return {
                "status": "answered",
                "prompt_id": prompt.prompt_id,
                "operation_id": prompt.operation_id,
                "value": value,
            }
        finally:
            with self._lock:
                self._pending.pop(prompt.prompt_id, None)

    @staticmethod
    def _resolve(future: asyncio.Future[str], value: str) -> None:
        if not future.done():
            future.set_result(value)

    def answer(self, prompt_id: str, value: str) -> bool:
        if not isinstance(value, str):
            raise ValueError("operator answer must be a string")
        with self._lock:
            pending = self._pending.pop(prompt_id, None)
        if pending is None or pending.future.done():
            return False
        pending.loop.call_soon_threadsafe(self._resolve, pending.future, value)
        return True

    def next_prompt(self) -> InboxPrompt | None:
        while True:
            try:
                prompt = self._queue.get_nowait()
            except queue.Empty:
                return None
            with self._lock:
                if prompt.prompt_id in self._pending:
                    return prompt

    def pending_prompt_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._pending)
