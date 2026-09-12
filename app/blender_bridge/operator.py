from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from uuid import uuid4

from .models import OperatorAnswer, OperatorPrompt


PromptPublisher = Callable[[OperatorPrompt], Awaitable[None]]


class OperatorBroker:
    def __init__(self, publish: PromptPublisher) -> None:
        self._publish = publish
        self._pending: dict[str, asyncio.Future[OperatorAnswer]] = {}

    async def ask(
        self,
        *,
        question: str,
        choices: tuple[str, ...] = (),
        operation_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> OperatorAnswer:
        prompt = OperatorPrompt(
            prompt_id=f"ask_{uuid4().hex}",
            question=question,
            choices=choices,
            operation_id=operation_id,
        )
        loop = asyncio.get_running_loop()
        future: asyncio.Future[OperatorAnswer] = loop.create_future()
        self._pending[prompt.prompt_id] = future
        try:
            await self._publish(prompt)
            if timeout_seconds is None:
                return await future
            return await asyncio.wait_for(future, timeout=timeout_seconds)
        finally:
            self._pending.pop(prompt.prompt_id, None)

    def answer(self, prompt_id: str, value: str) -> bool:
        future = self._pending.get(prompt_id)
        if future is None or future.done():
            return False
        future.set_result(OperatorAnswer(prompt_id=prompt_id, value=value))
        return True

    def pending_prompt_ids(self) -> tuple[str, ...]:
        return tuple(self._pending)
