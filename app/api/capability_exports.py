from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, Generic, TypeVar


MAX_CAPABILITY_EXPORT_TOKENS = 4096
Subject = TypeVar("Subject")


@dataclass(frozen=True, slots=True)
class CapabilityExportGrant(Generic[Subject]):
    subject: Subject
    expires_at: datetime
    expires_monotonic: float


class CapabilityExportRegistry(Generic[Subject]):
    """Bounded process-local registry for opaque, expiring capability tokens."""

    def __init__(
        self,
        ttl_seconds: int,
        *,
        capacity: int = MAX_CAPABILITY_EXPORT_TOKENS,
        monotonic: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if ttl_seconds <= 0 or capacity <= 0:
            raise ValueError("Export token TTL and capacity must be positive")
        self.ttl_seconds = ttl_seconds
        self.capacity = capacity
        self._monotonic = monotonic
        self._utcnow = utcnow
        self._grants: dict[str, CapabilityExportGrant[Subject]] = {}
        self._lock = threading.Lock()

    def issue(self, subject: Subject) -> tuple[str, CapabilityExportGrant[Subject]]:
        with self._lock:
            now = self._monotonic()
            self._cleanup(now)
            if len(self._grants) >= self.capacity:
                oldest = min(
                    self._grants,
                    key=lambda token: self._grants[token].expires_monotonic,
                )
                del self._grants[oldest]
            token = secrets.token_urlsafe(32)
            while token in self._grants:
                token = secrets.token_urlsafe(32)
            grant = CapabilityExportGrant(
                subject,
                self._utcnow() + timedelta(seconds=self.ttl_seconds),
                now + self.ttl_seconds,
            )
            self._grants[token] = grant
            return token, grant

    def lookup(self, token: str) -> CapabilityExportGrant[Subject] | None:
        with self._lock:
            now = self._monotonic()
            self._cleanup(now)
            return self._grants.get(token)

    def _cleanup(self, now: float) -> None:
        expired = [
            token
            for token, grant in self._grants.items()
            if grant.expires_monotonic <= now
        ]
        for token in expired:
            del self._grants[token]
