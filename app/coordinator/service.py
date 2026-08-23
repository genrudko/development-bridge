from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from secrets import token_urlsafe

from app.api.errors import BridgeError, ErrorCode


@dataclass(slots=True)
class PendingWake:
    message: str
    available_at: float
    created_at: float
    claim_id: str | None = None
    lease_expires_at: float | None = None


class CoordinatorService:
    """Bounded, in-process wake state shared by MCP tools and the X HTTP routes."""

    DEFAULT_CHANNEL = "coordinator"
    DEFAULT_DELAY_SECONDS = 12.0
    MAX_CHANNELS = 64
    MAX_MESSAGE_CHARS = 4000
    MIN_DELAY_SECONDS = 0.0
    MAX_DELAY_SECONDS = 300.0
    LEASE_SECONDS = 20.0

    def __init__(self) -> None:
        self._pending: dict[str, PendingWake] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def validate_channel(channel_id: str) -> str:
        if (
            not isinstance(channel_id, str)
            or not 1 <= len(channel_id) <= 64
            or any(not (char.isalnum() or char in "-_") for char in channel_id)
        ):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "channel_id is invalid")
        return channel_id

    @classmethod
    def validate_message(cls, message: str) -> str:
        if not isinstance(message, str) or not 1 <= len(message) <= cls.MAX_MESSAGE_CHARS:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                f"message must contain 1 to {cls.MAX_MESSAGE_CHARS} characters",
            )
        return message

    async def arm(
        self,
        message: str,
        *,
        channel_id: str = DEFAULT_CHANNEL,
        delay_seconds: float = DEFAULT_DELAY_SECONDS,
        conflict: str = "coalesce",
    ) -> dict:
        channel_id = self.validate_channel(channel_id)
        message = self.validate_message(message)
        if (
            not isinstance(delay_seconds, (int, float))
            or isinstance(delay_seconds, bool)
            or not self.MIN_DELAY_SECONDS <= delay_seconds <= self.MAX_DELAY_SECONDS
        ):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "delay_seconds is invalid")
        if conflict not in {"coalesce", "reject"}:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "conflict is invalid")
        now = time.monotonic()
        async with self._lock:
            existing = self._pending.get(channel_id)
            if existing is not None and self._lease_active(existing, now):
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    "Wake is currently claimed; retry after the lease expires",
                    retryable=True,
                    details={"channel_id": channel_id},
                )
            if existing is not None and conflict == "reject":
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    "A wake is already pending for this channel",
                    retryable=True,
                    details={"channel_id": channel_id},
                )
            if existing is None and len(self._pending) >= self.MAX_CHANNELS:
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    "Coordinator channel capacity is full",
                    retryable=True,
                )
            coalesced = existing is not None
            self._pending[channel_id] = PendingWake(
                message=message,
                available_at=now + float(delay_seconds),
                created_at=now,
            )
            return {
                "channel_id": channel_id,
                "state": "pending",
                "delay_seconds": float(delay_seconds),
                "coalesced": coalesced,
            }

    async def status(self, channel_id: str = DEFAULT_CHANNEL) -> dict:
        channel_id = self.validate_channel(channel_id)
        now = time.monotonic()
        async with self._lock:
            wake = self._pending.get(channel_id)
            if wake is None:
                return {"channel_id": channel_id, "state": "idle", "ready": False}
            claimed = self._lease_active(wake, now)
            return {
                "channel_id": channel_id,
                "state": "claimed" if claimed else "pending",
                "ready": not claimed and now >= wake.available_at,
                "retry_after_seconds": max(0.0, wake.available_at - now),
                "lease_remaining_seconds": (
                    max(0.0, (wake.lease_expires_at or now) - now) if claimed else 0.0
                ),
            }

    async def claim(self, channel_id: str = DEFAULT_CHANNEL) -> dict:
        channel_id = self.validate_channel(channel_id)
        now = time.monotonic()
        async with self._lock:
            wake = self._pending.get(channel_id)
            if wake is None or now < wake.available_at or self._lease_active(wake, now):
                return {"channel_id": channel_id, "claimed": False}
            wake.claim_id = token_urlsafe(18)
            wake.lease_expires_at = now + self.LEASE_SECONDS
            return {
                "channel_id": channel_id,
                "claimed": True,
                "claim_id": wake.claim_id,
                "message": wake.message,
                "lease_seconds": self.LEASE_SECONDS,
            }

    async def ack(self, channel_id: str, claim_id: str) -> dict:
        channel_id = self.validate_channel(channel_id)
        async with self._lock:
            wake = self._pending.get(channel_id)
            if wake is None or wake.claim_id != claim_id:
                return {"channel_id": channel_id, "acknowledged": False}
            del self._pending[channel_id]
            return {"channel_id": channel_id, "acknowledged": True}

    @staticmethod
    def _lease_active(wake: PendingWake, now: float) -> bool:
        return wake.claim_id is not None and (wake.lease_expires_at or 0) > now
