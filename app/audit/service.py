from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from typing import Protocol

from .models import AuditEvent


class AuditSink(Protocol):
    async def emit(self, event: AuditEvent) -> None: ...


class LoggingAuditSink:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("development_bridge.audit")

    async def emit(self, event: AuditEvent) -> None:
        self._logger.info(json.dumps(event.as_dict(), sort_keys=True))


class CompositeAuditSink:
    def __init__(self, sinks: Iterable[AuditSink]) -> None:
        self._sinks = tuple(sinks)

    async def emit(self, event: AuditEvent) -> None:
        for sink in self._sinks:
            await sink.emit(event)

