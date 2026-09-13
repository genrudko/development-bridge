from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

T = TypeVar("T")


class CallKind(str, Enum):
    MUTATION = "mutation"
    IDEMPOTENT_READ = "idempotent_read"
    NON_IDEMPOTENT_READ = "non_idempotent_read"


class TransportOutcome(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


class TransportFailure(ConnectionError):
    """The transport failed during or after an attempted dispatch."""


@dataclass(frozen=True, slots=True)
class TransportResult(Generic[T]):
    outcome: TransportOutcome
    value: T | None = None
    error: str | None = None
    attempts: int = 0
    reconnects: int = 0


async def dispatch_with_replay_policy(
    kind: CallKind,
    dispatch: Callable[[], Awaitable[T]],
    reconnect: Callable[[], Awaitable[None]],
) -> TransportResult[T]:
    """Dispatch once, replaying only an explicitly idempotent read once."""
    try:
        return TransportResult(
            outcome=TransportOutcome.SUCCESS,
            value=await dispatch(),
            attempts=1,
        )
    except TransportFailure as exc:
        if kind is CallKind.MUTATION:
            return TransportResult(
                outcome=TransportOutcome.UNCERTAIN,
                error=str(exc),
                attempts=1,
            )
        if kind is not CallKind.IDEMPOTENT_READ:
            return TransportResult(
                outcome=TransportOutcome.FAILED,
                error=str(exc),
                attempts=1,
            )

    try:
        await reconnect()
        value = await dispatch()
    except TransportFailure as exc:
        return TransportResult(
            outcome=TransportOutcome.FAILED,
            error=str(exc),
            attempts=2,
            reconnects=1,
        )
    return TransportResult(
        outcome=TransportOutcome.SUCCESS,
        value=value,
        attempts=2,
        reconnects=1,
    )
