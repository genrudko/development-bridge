from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from secrets import token_urlsafe

from app.api.errors import BridgeError, ErrorCode


@dataclass(slots=True)
class PendingWake:
    message: str
    available_at: float
    created_at: float
    claim_id: str | None = None
    lease_expires_at: float | None = None
    continuation_id: str | None = None
    model_ack_required: bool = False
    model_acknowledged: bool = False
    delivery_attempts: int = 0
    max_delivery_attempts: int = 1
    retry_delays_seconds: list[float] = field(default_factory=list)
    escalation_delay_seconds: float = 0.0
    escalation_message: str | None = None
    escalation_at: float | None = None


class CoordinatorService:
    "Durable coordinator wake state shared by MCP tools and the X HTTP routes."

    DEFAULT_CHANNEL = "coordinator"
    DEFAULT_DELAY_SECONDS = 12.0
    DEFAULT_MODEL_ACK_RETRY_DELAYS_SECONDS = (30.0, 60.0)
    DEFAULT_ESCALATION_DELAY_SECONDS = 60.0
    MAX_CHANNELS = 64
    MAX_MESSAGE_CHARS = 4000
    MAX_ESCALATION_MESSAGE_CHARS = 3500
    MIN_DELAY_SECONDS = 0.0
    MAX_DELAY_SECONDS = 300.0
    LEASE_SECONDS = 20.0

    def __init__(self, state_path: Path | None = None) -> None:
        self._state_path = state_path.expanduser() if state_path is not None else None
        self._pending: dict[str, PendingWake] = {}
        self._lock = asyncio.Lock()
        self._load_state()

    def _load_state(self) -> None:
        if self._state_path is None:
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return
        for channel_id, item in list((data.get("pending") or {}).items())[: self.MAX_CHANNELS]:
            try:
                channel = self.validate_channel(channel_id)
                self.validate_message(item["message"])
                payload = dict(item)
                payload["retry_delays_seconds"] = [
                    float(value) for value in payload.get("retry_delays_seconds", [])
                ]
                self._pending[channel] = PendingWake(**payload)
            except (BridgeError, TypeError, ValueError, KeyError):
                continue

    def _save_state(self) -> None:
        if self._state_path is None:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._state_path.with_suffix(".tmp")
        data = {"version": 1, "pending": {key: asdict(value) for key, value in self._pending.items()}}
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self._state_path)

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

    @staticmethod
    def validate_continuation_id(continuation_id: str) -> str:
        if (
            not isinstance(continuation_id, str)
            or not continuation_id.startswith("cont_")
            or not 10 <= len(continuation_id) <= 80
            or any(not (char.isalnum() or char in "-_") for char in continuation_id)
        ):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "continuation_id is invalid")
        return continuation_id

    @classmethod
    def _validate_delay(cls, value: float, field_name: str) -> float:
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not cls.MIN_DELAY_SECONDS <= value <= cls.MAX_DELAY_SECONDS
        ):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"{field_name} is invalid")
        return float(value)

    async def arm(
        self,
        message: str,
        *,
        channel_id: str = DEFAULT_CHANNEL,
        delay_seconds: float = DEFAULT_DELAY_SECONDS,
        conflict: str = "coalesce",
        model_ack_required: bool = False,
        max_delivery_attempts: int = 1,
        retry_delays_seconds: Sequence[float] = (),
        escalation_delay_seconds: float = 0.0,
        escalation_message: str | None = None,
    ) -> dict:
        channel_id = self.validate_channel(channel_id)
        message = self.validate_message(message)
        delay_seconds = self._validate_delay(delay_seconds, "delay_seconds")
        if conflict not in {"coalesce", "reject"}:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "conflict is invalid")
        if not isinstance(model_ack_required, bool):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "model_ack_required is invalid")
        if not isinstance(max_delivery_attempts, int) or isinstance(max_delivery_attempts, bool):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "max_delivery_attempts is invalid")
        if not 1 <= max_delivery_attempts <= 5:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "max_delivery_attempts is invalid")
        retry_delays = [
            self._validate_delay(value, "retry_delays_seconds") for value in retry_delays_seconds
        ]
        if model_ack_required and len(retry_delays) != max_delivery_attempts - 1:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "retry_delays_seconds must contain one delay between each delivery attempt",
            )
        if not model_ack_required and retry_delays:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "retry_delays_seconds requires model_ack_required",
            )
        escalation_delay_seconds = self._validate_delay(
            escalation_delay_seconds, "escalation_delay_seconds"
        )
        if escalation_message is not None:
            escalation_message = str(escalation_message).strip()
            if not 1 <= len(escalation_message) <= self.MAX_ESCALATION_MESSAGE_CHARS:
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "escalation_message is invalid")

        now = time.time()
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
            continuation_id = f"cont_{token_urlsafe(18)}" if model_ack_required else None
            self._pending[channel_id] = PendingWake(
                message=message,
                available_at=now + delay_seconds,
                created_at=now,
                continuation_id=continuation_id,
                model_ack_required=model_ack_required,
                max_delivery_attempts=max_delivery_attempts,
                retry_delays_seconds=retry_delays,
                escalation_delay_seconds=escalation_delay_seconds,
                escalation_message=escalation_message,
            )
            self._save_state()
            data = {
                "channel_id": channel_id,
                "state": "pending",
                "delay_seconds": delay_seconds,
                "coalesced": coalesced,
            }
            if continuation_id is not None:
                data.update(
                    {
                        "continuation_id": continuation_id,
                        "model_ack_required": True,
                        "max_delivery_attempts": max_delivery_attempts,
                    }
                )
            return data

    async def arm_resilient(
        self,
        message: str,
        *,
        channel_id: str = DEFAULT_CHANNEL,
        delay_seconds: float = 0.0,
        conflict: str = "coalesce",
        retry_delays_seconds: Sequence[float] | None = None,
        escalation_delay_seconds: float = DEFAULT_ESCALATION_DELAY_SECONDS,
        escalation_message: str | None = None,
    ) -> dict:
        delays = tuple(
            self.DEFAULT_MODEL_ACK_RETRY_DELAYS_SECONDS
            if retry_delays_seconds is None
            else retry_delays_seconds
        )
        return await self.arm(
            message,
            channel_id=channel_id,
            delay_seconds=delay_seconds,
            conflict=conflict,
            model_ack_required=True,
            max_delivery_attempts=len(delays) + 1,
            retry_delays_seconds=delays,
            escalation_delay_seconds=escalation_delay_seconds,
            escalation_message=escalation_message,
        )

    async def status(self, channel_id: str = DEFAULT_CHANNEL) -> dict:
        channel_id = self.validate_channel(channel_id)
        now = time.time()
        async with self._lock:
            wake = self._pending.get(channel_id)
            if wake is None:
                return {"channel_id": channel_id, "state": "idle", "ready": False}
            claimed = self._lease_active(wake, now)
            exhausted = wake.model_ack_required and wake.delivery_attempts >= wake.max_delivery_attempts
            ready = not claimed and not exhausted and now >= wake.available_at
            if claimed:
                state = "claimed"
            elif exhausted:
                state = (
                    "escalation_due"
                    if (wake.escalation_at or float("inf")) <= now
                    else "waiting_model_ack"
                )
            elif wake.model_ack_required and wake.delivery_attempts > 0 and not ready:
                state = "waiting_model_ack"
            else:
                state = "pending"
            data = {
                "channel_id": channel_id,
                "state": state,
                "ready": ready,
                "retry_after_seconds": max(0.0, wake.available_at - now) if not exhausted else 0.0,
                "lease_remaining_seconds": (
                    max(0.0, (wake.lease_expires_at or now) - now) if claimed else 0.0
                ),
            }
            if wake.continuation_id is not None:
                data.update(
                    {
                        "continuation_id": wake.continuation_id,
                        "delivery_attempts": wake.delivery_attempts,
                        "max_delivery_attempts": wake.max_delivery_attempts,
                    }
                )
            return data

    async def claim(self, channel_id: str = DEFAULT_CHANNEL) -> dict:
        channel_id = self.validate_channel(channel_id)
        now = time.time()
        async with self._lock:
            wake = self._pending.get(channel_id)
            if (
                wake is None
                or now < wake.available_at
                or self._lease_active(wake, now)
                or (wake.model_ack_required and wake.delivery_attempts >= wake.max_delivery_attempts)
            ):
                return {"channel_id": channel_id, "claimed": False}
            wake.claim_id = token_urlsafe(18)
            wake.lease_expires_at = now + self.LEASE_SECONDS
            self._save_state()
            data = {
                "channel_id": channel_id,
                "claimed": True,
                "claim_id": wake.claim_id,
                "message": wake.message,
                "lease_seconds": self.LEASE_SECONDS,
            }
            if wake.continuation_id is not None:
                data.update(
                    {
                        "continuation_id": wake.continuation_id,
                        "delivery_attempt": wake.delivery_attempts + 1,
                        "max_delivery_attempts": wake.max_delivery_attempts,
                        "model_ack_required": True,
                    }
                )
            return data

    async def ack(self, channel_id: str, claim_id: str) -> dict:
        "Acknowledge one iframe transport delivery attempt."
        channel_id = self.validate_channel(channel_id)
        now = time.time()
        async with self._lock:
            wake = self._pending.get(channel_id)
            if wake is None or wake.claim_id != claim_id:
                return {"channel_id": channel_id, "acknowledged": False}
            if not wake.model_ack_required or wake.model_acknowledged:
                continuation_id = wake.continuation_id
                del self._pending[channel_id]
                self._save_state()
                data = {"channel_id": channel_id, "acknowledged": True}
                if continuation_id is not None:
                    data.update({"continuation_id": continuation_id, "model_acknowledged": True})
                return data

            wake.delivery_attempts += 1
            wake.claim_id = None
            wake.lease_expires_at = None
            wake.escalation_at = None
            next_retry_seconds = None
            if wake.delivery_attempts < wake.max_delivery_attempts:
                next_retry_seconds = wake.retry_delays_seconds[wake.delivery_attempts - 1]
                wake.available_at = now + next_retry_seconds
            else:
                wake.available_at = now
                wake.escalation_at = now + wake.escalation_delay_seconds
            self._save_state()
            return {
                "channel_id": channel_id,
                "acknowledged": True,
                "continuation_id": wake.continuation_id,
                "delivery_attempts": wake.delivery_attempts,
                "max_delivery_attempts": wake.max_delivery_attempts,
                "model_ack_required": True,
                "next_retry_seconds": next_retry_seconds,
                "escalation_after_seconds": (
                    wake.escalation_delay_seconds
                    if wake.delivery_attempts >= wake.max_delivery_attempts
                    else None
                ),
            }

    async def model_ack(self, continuation_id: str) -> dict:
        continuation_id = self.validate_continuation_id(continuation_id)
        async with self._lock:
            for channel_id, wake in list(self._pending.items()):
                if wake.continuation_id != continuation_id:
                    continue
                attempts = wake.delivery_attempts
                if wake.claim_id is not None and self._lease_active(wake, time.time()):
                    wake.model_acknowledged = True
                    self._save_state()
                else:
                    del self._pending[channel_id]
                    self._save_state()
                return {
                    "continuation_id": continuation_id,
                    "channel_id": channel_id,
                    "acknowledged": True,
                    "delivery_attempts": attempts,
                }
            return {"continuation_id": continuation_id, "acknowledged": False}

    async def model_ack_channel(self, channel_id: str) -> dict:
        channel_id = self.validate_channel(channel_id)
        async with self._lock:
            wake = self._pending.get(channel_id)
            continuation_id = wake.continuation_id if wake is not None else None
        if continuation_id is None:
            return {"channel_id": channel_id, "acknowledged": False}
        return await self.model_ack(continuation_id)

    async def escalations_due(self) -> list[dict]:
        now = time.time()
        async with self._lock:
            due = []
            for channel_id, wake in self._pending.items():
                if (
                    wake.continuation_id is None
                    or wake.model_acknowledged
                    or wake.delivery_attempts < wake.max_delivery_attempts
                    or wake.escalation_at is None
                    or wake.escalation_at > now
                ):
                    continue
                due.append(
                    {
                        "continuation_id": wake.continuation_id,
                        "channel_id": channel_id,
                        "delivery_attempts": wake.delivery_attempts,
                        "max_delivery_attempts": wake.max_delivery_attempts,
                        "escalation_message": wake.escalation_message,
                    }
                )
            return due

    async def resolve_escalation(self, continuation_id: str) -> dict:
        continuation_id = self.validate_continuation_id(continuation_id)
        async with self._lock:
            for channel_id, wake in list(self._pending.items()):
                if wake.continuation_id != continuation_id:
                    continue
                del self._pending[channel_id]
                self._save_state()
                return {
                    "continuation_id": continuation_id,
                    "channel_id": channel_id,
                    "resolved": True,
                }
            return {"continuation_id": continuation_id, "resolved": False}

    @staticmethod
    def _lease_active(wake: PendingWake, now: float) -> bool:
        return wake.claim_id is not None and (wake.lease_expires_at or 0) > now
