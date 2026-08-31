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
    transport_delivered: bool = False
    transport_delivered_at: float | None = None
    last_transport_name: str | None = None
    last_transport_disposition: str | None = None
    last_transport_detail: str | None = None
    owner_input_required: bool = False
    browser_preflight_authorized_at: float | None = None
    queued_messages: list[str] = field(default_factory=list)
    queued_escalation_messages: list[str] = field(default_factory=list)


class CoordinatorService:
    "Durable coordinator wake state shared by MCP tools and the X HTTP routes."

    DEFAULT_CHANNEL = "coordinator"
    DEFAULT_DELAY_SECONDS = 12.0
    DEFAULT_MODEL_ACK_RETRY_DELAYS_SECONDS = (30.0, 60.0)
    DEFAULT_ESCALATION_DELAY_SECONDS = 60.0
    JOB_WAKE_DEBOUNCE_SECONDS = 5.0
    MAX_BATCH_DEBOUNCE_WINDOW_SECONDS = 15.0
    MIN_WEB_TURN_INTERVAL_SECONDS = 30.0
    MAX_CHANNELS = 64
    MAX_MESSAGE_CHARS = 4000
    MAX_BATCH_MESSAGE_CHARS = 32000
    MAX_BATCH_EVENTS = 128
    MAX_ESCALATION_MESSAGE_CHARS = 3500
    MAX_TRANSPORT_NAME_CHARS = 128
    MAX_TRANSPORT_DETAIL_CHARS = 1000
    DELIVERY_MODES = frozenset(("x", "direct"))
    TRANSPORT_DISPOSITIONS = frozenset(
        ("delivered", "not_submitted", "uncertain", "owner_input_required")
    )
    BATCH_SEPARATOR = "\n--- bridge-batch ---\n"
    MIN_DELAY_SECONDS = 0.0
    MAX_DELAY_SECONDS = 300.0
    LEASE_SECONDS = 20.0
    BROWSER_PREFLIGHT_TTL_SECONDS = 15.0
    MAX_UNDELIVERED_AGE_SECONDS = 1800.0
    SESSION_BINDING_TTL_SECONDS = 86_400.0
    MAX_SESSION_BINDINGS = 256

    def __init__(
        self,
        state_path: Path | None = None,
        *,
        browser_preflight_required: bool = False,
    ) -> None:
        self._state_path = state_path.expanduser() if state_path is not None else None
        self._browser_preflight_required = bool(browser_preflight_required)
        self._pending: dict[str, PendingWake] = {}
        self._cooldown_until: dict[str, float] = {}
        self._global_cooldown_until = 0.0
        self._session_bindings: dict[str, dict[str, object]] = {}
        self._delivery_leases: dict[str, dict[str, object]] = {}
        self._lock = asyncio.Lock()
        self._load_state()

    def _load_state(self) -> None:
        if self._state_path is None:
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return
        try:
            global_until = float(data.get("global_cooldown_until", 0.0))
            if global_until > time.time():
                self._global_cooldown_until = global_until
        except (TypeError, ValueError):
            pass
        for channel_id, value in list((data.get("cooldown_until") or {}).items())[: self.MAX_CHANNELS]:
            try:
                channel = self.validate_channel(channel_id)
                until = float(value)
                if until > time.time():
                    self._cooldown_until[channel] = until
            except (BridgeError, TypeError, ValueError):
                continue
        for channel_id, item in list((data.get("pending") or {}).items())[: self.MAX_CHANNELS]:
            try:
                channel = self.validate_channel(channel_id)
                if not isinstance(item["message"], str) or not 1 <= len(item["message"]) <= self.MAX_BATCH_MESSAGE_CHARS:
                    raise ValueError("persisted wake message is invalid")
                payload = dict(item)
                payload["retry_delays_seconds"] = [
                    float(value) for value in payload.get("retry_delays_seconds", [])
                ]
                payload["queued_messages"] = [str(value) for value in payload.get("queued_messages", [])]
                payload["queued_escalation_messages"] = [str(value) for value in payload.get("queued_escalation_messages", [])]
                self._pending[channel] = PendingWake(**payload)
            except (BridgeError, TypeError, ValueError, KeyError):
                continue
        for channel_id, item in list((data.get("delivery_leases") or {}).items())[: self.MAX_CHANNELS]:
            try:
                channel = self.validate_channel(channel_id)
                if not isinstance(item, dict):
                    raise ValueError("persisted delivery lease is invalid")
                lease_id = str(item["lease_id"])
                if not 10 <= len(lease_id) <= 128:
                    raise ValueError("persisted delivery lease token is invalid")
                payload = dict(item)
                payload["lease_id"] = lease_id
                self._delivery_leases[channel] = payload
            except (BridgeError, TypeError, ValueError, KeyError):
                continue

    def _save_state(self) -> None:
        if self._state_path is None:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._state_path.with_suffix(".tmp")
        now = time.time()
        self._cooldown_until = {key: value for key, value in self._cooldown_until.items() if value > now}
        if self._global_cooldown_until <= now:
            self._global_cooldown_until = 0.0
        data = {
            "version": 1,
            "pending": {key: asdict(value) for key, value in self._pending.items()},
            "cooldown_until": self._cooldown_until,
            "global_cooldown_until": self._global_cooldown_until,
            "delivery_leases": self._delivery_leases,
        }
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self._state_path)

    @staticmethod
    def validate_session_id(session_id: str) -> str:
        if not isinstance(session_id, str) or not 1 <= len(session_id) <= 256:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "session_id is invalid")
        return session_id

    def _prune_session_bindings(self) -> None:
        now = time.time()
        self._session_bindings = {
            key: value
            for key, value in self._session_bindings.items()
            if float(value.get("bound_at", 0.0)) + self.SESSION_BINDING_TTL_SECONDS > now
        }
        if len(self._session_bindings) <= self.MAX_SESSION_BINDINGS:
            return
        ordered = sorted(
            self._session_bindings.items(),
            key=lambda item: float(item[1].get("bound_at", 0.0)),
            reverse=True,
        )
        self._session_bindings = dict(ordered[: self.MAX_SESSION_BINDINGS])

    def bind_session(
        self,
        session_id: str,
        channel_id: str,
        *,
        route_id: str | None = None,
        generation: int | None = None,
        route_state: str | None = None,
    ) -> dict[str, object]:
        session = self.validate_session_id(session_id)
        channel = self.validate_channel(channel_id)
        self._prune_session_bindings()
        item: dict[str, object] = {
            "session_id": session,
            "channel_id": channel,
            "bound_at": time.time(),
        }
        if route_id is not None:
            item["route_id"] = str(route_id)
        if generation is not None:
            item["generation"] = int(generation)
        if route_state is not None:
            item["route_state"] = str(route_state)
        self._session_bindings[session] = item
        self._prune_session_bindings()
        return dict(item)

    def session_binding(self, session_id: str | None) -> dict[str, object] | None:
        if session_id is None:
            return None
        session = self.validate_session_id(session_id)
        self._prune_session_bindings()
        item = self._session_bindings.get(session)
        return dict(item) if item is not None else None

    def issue_delivery_lease(
        self,
        channel_id: str,
        *,
        session_id: str | None = None,
        route_id: str | None = None,
        generation: int | None = None,
    ) -> dict[str, object]:
        channel = self.validate_channel(channel_id)
        session = self.validate_session_id(session_id) if session_id is not None else None
        current = self._delivery_leases.get(channel)
        if current is not None and session is not None and current.get("session_id") == session:
            item = dict(current)
        else:
            item = {"lease_id": token_urlsafe(24), "issued_at": time.time()}
        if session is not None:
            item["session_id"] = session
        if route_id is not None:
            item["route_id"] = str(route_id)
        if generation is not None:
            item["generation"] = int(generation)
        item["refreshed_at"] = time.time()
        self._delivery_leases[channel] = item
        self._save_state()
        return {"channel_id": channel, **item}

    def delivery_lease(self, channel_id: str) -> dict[str, object] | None:
        channel = self.validate_channel(channel_id)
        item = self._delivery_leases.get(channel)
        return {"channel_id": channel, **item} if item is not None else None

    def _delivery_lease_matches(self, channel_id: str, delivery_lease: str | None) -> bool:
        item = self._delivery_leases.get(channel_id)
        if item is None or delivery_lease is None:
            # Cached/legacy coordinator widgets may miss the tool-result event that carries
            # the current lease. The physical channel already identifies the exact chat, so
            # allow an omitted lease while still rejecting any explicitly stale lease.
            return True
        return isinstance(delivery_lease, str) and delivery_lease == item.get("lease_id")

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
    def _validate_delivery_mode(cls, delivery_mode: str) -> str:
        if delivery_mode not in cls.DELIVERY_MODES:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "delivery_mode is invalid")
        return delivery_mode

    @classmethod
    def _validate_transport_name(cls, transport_name: str) -> str:
        if (
            not isinstance(transport_name, str)
            or not 1 <= len(transport_name) <= cls.MAX_TRANSPORT_NAME_CHARS
        ):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "transport_name is invalid")
        return transport_name

    @classmethod
    def _bounded_transport_detail(cls, detail: str | None) -> str | None:
        if detail is None:
            return None
        if not isinstance(detail, str):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "detail is invalid")
        return detail[: cls.MAX_TRANSPORT_DETAIL_CHARS]

    @staticmethod
    def _automatic_delivery_blocked(wake: PendingWake) -> bool:
        return wake.last_transport_disposition in {"uncertain", "owner_input_required"}

    @classmethod
    def _validate_delay(cls, value: float, field_name: str) -> float:
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not cls.MIN_DELAY_SECONDS <= value <= cls.MAX_DELAY_SECONDS
        ):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"{field_name} is invalid")
        return float(value)

    def _web_turn_cooldown_until(self, channel_id: str) -> float:
        return max(
            self._global_cooldown_until,
            self._cooldown_until.get(channel_id, 0.0),
        )

    def _other_claim_until(self, channel_id: str, now: float) -> float:
        until = 0.0
        for other_channel, wake in self._pending.items():
            if other_channel != channel_id and self._lease_active(wake, now):
                until = max(until, wake.lease_expires_at or 0.0)
        return until

    def _browser_preflight_authorized(self, wake: PendingWake, now: float) -> bool:
        if not self._browser_preflight_required or not wake.model_ack_required:
            return True
        authorized_at = wake.browser_preflight_authorized_at
        return (
            authorized_at is not None
            and authorized_at + self.BROWSER_PREFLIGHT_TTL_SECONDS > now
        )

    def _undelivered_expired(self, wake: PendingWake, now: float) -> bool:
        return (
            wake.continuation_id is not None
            and not wake.transport_delivered
            and not wake.model_acknowledged
            and wake.created_at + self.MAX_UNDELIVERED_AGE_SECONDS <= now
        )

    def _web_backoff_until(self, now: float) -> float:
        if self._state_path is None:
            return 0.0
        path = self._state_path.parent / "web-backoff.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            until = float(payload.get("until", 0.0))
        except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, ValueError):
            return 0.0
        return until if until > now else 0.0

    @classmethod
    def _batch_parts(cls, message: str) -> list[str]:
        return message.split(cls.BATCH_SEPARATOR)

    @classmethod
    def _bounded_escalation(cls, parts: Sequence[str | None]) -> str | None:
        values = [value.strip() for value in parts if value and value.strip()]
        if not values:
            return None
        combined = "\n\n--- additional terminal group ---\n".join(values)
        if len(combined) <= cls.MAX_ESCALATION_MESSAGE_CHARS:
            return combined
        suffix = "\n… additional terminal groups omitted; inspect Bridge state."
        return combined[: cls.MAX_ESCALATION_MESSAGE_CHARS - len(suffix)] + suffix

    def _coalesce_resilient_locked(self, channel_id: str, wake: PendingWake, message: str, escalation_message: str | None, debounce_seconds: float) -> dict:
        current = self._batch_parts(wake.message)
        if message in current or message in wake.queued_messages:
            return {"channel_id": channel_id, "state": "pending", "coalesced": True, "deduplicated": True, "continuation_id": wake.continuation_id, "model_ack_required": True, "max_delivery_attempts": wake.max_delivery_attempts, "batch_size": len(current), "queued_events": len(wake.queued_messages)}
        if len(current) + len(wake.queued_messages) >= self.MAX_BATCH_EVENTS:
            raise BridgeError(ErrorCode.POLICY_VIOLATION, "Coordinator batch capacity is full", retryable=True, details={"channel_id": channel_id})
        combined = self.BATCH_SEPARATOR.join([*current, message])
        merge_current = wake.delivery_attempts == 0 and wake.claim_id is None and not wake.model_acknowledged and len(combined) <= self.MAX_BATCH_MESSAGE_CHARS
        if merge_current:
            wake.message = combined
            wake.browser_preflight_authorized_at = None
            wake.escalation_message = self._bounded_escalation((wake.escalation_message, escalation_message))
            if debounce_seconds > 0:
                now = time.time()
                quiet_until = min(
                    wake.created_at + self.MAX_BATCH_DEBOUNCE_WINDOW_SECONDS,
                    now + debounce_seconds,
                )
                wake.available_at = max(
                    wake.available_at,
                    quiet_until,
                    self._web_turn_cooldown_until(channel_id),
                )
        else:
            wake.queued_messages.append(message)
            wake.queued_escalation_messages.append(escalation_message or "")
        return {"channel_id": channel_id, "state": "pending", "coalesced": True, "deduplicated": False, "continuation_id": wake.continuation_id, "model_ack_required": True, "max_delivery_attempts": wake.max_delivery_attempts, "batch_size": len(self._batch_parts(wake.message)), "queued_events": len(wake.queued_messages)}

    def _promote_queued_locked(self, channel_id: str, wake: PendingWake, now: float) -> str | None:
        if not wake.queued_messages:
            del self._pending[channel_id]
            return None
        active_messages: list[str] = []
        active_escalations: list[str] = []
        remaining_messages: list[str] = []
        remaining_escalations: list[str] = []
        for message, escalation in zip(wake.queued_messages, wake.queued_escalation_messages, strict=False):
            candidate = self.BATCH_SEPARATOR.join([*active_messages, message])
            if active_messages and len(candidate) > self.MAX_BATCH_MESSAGE_CHARS:
                remaining_messages.append(message); remaining_escalations.append(escalation)
            else:
                active_messages.append(message); active_escalations.append(escalation)
        continuation_id = f"cont_{token_urlsafe(18)}"
        self._pending[channel_id] = PendingWake(message=self.BATCH_SEPARATOR.join(active_messages), available_at=max(now + self.JOB_WAKE_DEBOUNCE_SECONDS, self._web_turn_cooldown_until(channel_id)), created_at=now, continuation_id=continuation_id, model_ack_required=True, max_delivery_attempts=wake.max_delivery_attempts, retry_delays_seconds=list(wake.retry_delays_seconds), escalation_delay_seconds=wake.escalation_delay_seconds, escalation_message=self._bounded_escalation(active_escalations), queued_messages=remaining_messages, queued_escalation_messages=remaining_escalations)
        return continuation_id

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
            if (
                existing is not None
                and conflict == "coalesce"
                and model_ack_required
                and existing.model_ack_required
            ):
                data = self._coalesce_resilient_locked(
                    channel_id, existing, message, escalation_message, delay_seconds
                )
                self._save_state()
                return data
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
                available_at=max(now + delay_seconds, self._web_turn_cooldown_until(channel_id)),
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

    async def status(
        self, channel_id: str = DEFAULT_CHANNEL, *, delivery_lease: str | None = None,
        delivery_mode: str = "x",
    ) -> dict:
        channel_id = self.validate_channel(channel_id)
        delivery_mode = self._validate_delivery_mode(delivery_mode)
        if not self._delivery_lease_matches(channel_id, delivery_lease):
            return {
                "channel_id": channel_id,
                "state": "standby",
                "ready": False,
                "delivery_lease_required": True,
            }
        now = time.time()
        async with self._lock:
            wake = self._pending.get(channel_id)
            if wake is None:
                return {"channel_id": channel_id, "state": "idle", "ready": False}
            if wake.model_acknowledged and not self._lease_active(wake, now):
                self._promote_queued_locked(channel_id, wake, now)
                self._save_state()
                wake = self._pending.get(channel_id)
                if wake is None:
                    return {"channel_id": channel_id, "state": "idle", "ready": False}
            claimed = self._lease_active(wake, now)
            exhausted = wake.model_ack_required and wake.delivery_attempts >= wake.max_delivery_attempts
            expired_undelivered = self._undelivered_expired(wake, now)
            web_backoff_until = self._web_backoff_until(now)
            web_cooldown_until = self._web_turn_cooldown_until(channel_id)
            other_claim_until = self._other_claim_until(channel_id, now)
            web_blocked = not wake.transport_delivered and web_backoff_until > now
            cooldown_blocked = not wake.transport_delivered and max(web_cooldown_until, other_claim_until) > now
            browser_preflight_authorized = self._browser_preflight_authorized(wake, now)
            browser_preflight_blocked = (
                delivery_mode == "x"
                and not wake.transport_delivered
                and not claimed
                and not exhausted
                and not expired_undelivered
                and not web_blocked
                and not cooldown_blocked
                and now >= wake.available_at
                and not browser_preflight_authorized
            )
            ready = (
                not claimed
                and not self._automatic_delivery_blocked(wake)
                and not exhausted
                and not expired_undelivered
                and not wake.transport_delivered
                and not web_blocked
                and not cooldown_blocked
                and not browser_preflight_blocked
                and now >= wake.available_at
            )
            if claimed:
                state = "claimed"
            elif wake.last_transport_disposition == "uncertain":
                state = "transport_uncertain"
            elif wake.owner_input_required:
                state = "owner_input_required"
            elif expired_undelivered:
                state = "escalation_due"
            elif wake.transport_delivered:
                state = ("escalation_due" if (wake.escalation_at or float("inf")) <= now else "waiting_model_ack")
            elif exhausted:
                state = (
                    "escalation_due"
                    if (wake.escalation_at or float("inf")) <= now
                    else "waiting_model_ack"
                )
            elif web_blocked:
                state = "web_backoff"
            elif cooldown_blocked:
                state = "web_cooldown"
            elif browser_preflight_blocked:
                state = "browser_preflight"
            elif wake.model_ack_required and wake.delivery_attempts > 0 and not ready:
                state = "waiting_model_ack"
            else:
                state = "pending"
            data = {
                "channel_id": channel_id,
                "state": state,
                "ready": ready,
                "retry_after_seconds": max(0.0, max(wake.available_at, web_backoff_until, web_cooldown_until, other_claim_until) - now) if not exhausted and not expired_undelivered else 0.0,
                "web_backoff_seconds": max(0.0, web_backoff_until - now),
                "web_turn_cooldown_seconds": max(0.0, max(web_cooldown_until, other_claim_until) - now),
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
                        "batch_size": len(self._batch_parts(wake.message)),
                        "queued_events": len(wake.queued_messages),
                        "transport_delivered": wake.transport_delivered,
                        "transport_delivered_at": wake.transport_delivered_at,
                        "model_acknowledged": wake.model_acknowledged,
                        "browser_preflight_required": self._browser_preflight_required,
                        "browser_preflight_authorized": browser_preflight_authorized,
                        "browser_preflight_ttl_seconds": self.BROWSER_PREFLIGHT_TTL_SECONDS,
                    }
                )
            if wake.last_transport_name is not None:
                data.update(
                    {
                        "last_transport_name": wake.last_transport_name,
                        "last_transport_disposition": wake.last_transport_disposition,
                        "last_transport_detail": wake.last_transport_detail,
                        "owner_input_required": wake.owner_input_required,
                    }
                )
            return data

    async def claim(
        self, channel_id: str = DEFAULT_CHANNEL, *, delivery_lease: str | None = None,
        delivery_mode: str = "x",
    ) -> dict:
        channel_id = self.validate_channel(channel_id)
        delivery_mode = self._validate_delivery_mode(delivery_mode)
        if not self._delivery_lease_matches(channel_id, delivery_lease):
            return {
                "channel_id": channel_id,
                "claimed": False,
                "state": "standby",
                "delivery_lease_required": True,
            }
        now = time.time()
        async with self._lock:
            wake = self._pending.get(channel_id)
            if (
                wake is None
                or now < wake.available_at
                or self._web_backoff_until(now) > now
                or self._web_turn_cooldown_until(channel_id) > now
                or self._other_claim_until(channel_id, now) > now
                or self._lease_active(wake, now)
                or wake.transport_delivered
                or wake.model_acknowledged
                or self._automatic_delivery_blocked(wake)
                or self._undelivered_expired(wake, now)
                or (
                    delivery_mode == "x"
                    and not self._browser_preflight_authorized(wake, now)
                )
                or (wake.model_ack_required and wake.delivery_attempts >= wake.max_delivery_attempts)
            ):
                return {"channel_id": channel_id, "claimed": False}
            wake.claim_id = token_urlsafe(18)
            wake.lease_expires_at = now + self.LEASE_SECONDS
            wake.browser_preflight_authorized_at = None
            if wake.model_ack_required:
                wake.delivery_attempts += 1
                if wake.delivery_attempts < wake.max_delivery_attempts:
                    wake.available_at = wake.lease_expires_at + wake.retry_delays_seconds[wake.delivery_attempts - 1]
                else:
                    wake.available_at = wake.lease_expires_at
                    wake.escalation_at = wake.lease_expires_at + wake.escalation_delay_seconds
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
                        "delivery_attempt": wake.delivery_attempts,
                        "max_delivery_attempts": wake.max_delivery_attempts,
                        "model_ack_required": True,
                        "batch_size": len(self._batch_parts(wake.message)),
                        "queued_events": len(wake.queued_messages),
                    }
                )
            return data

    async def finalize_transport(
        self,
        channel_id: str,
        claim_id: str,
        transport_name: str,
        disposition: str,
        *,
        detail: str | None = None,
    ) -> dict:
        """Finalize one claimed continuation after a direct transport attempt."""
        channel_id = self.validate_channel(channel_id)
        transport_name = self._validate_transport_name(transport_name)
        if disposition not in self.TRANSPORT_DISPOSITIONS:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "disposition is invalid")
        bounded_detail = self._bounded_transport_detail(detail)
        now = time.time()
        async with self._lock:
            wake = self._pending.get(channel_id)
            if wake is None or wake.claim_id != claim_id or wake.continuation_id is None:
                return {"channel_id": channel_id, "finalized": False}

            wake.last_transport_name = transport_name
            wake.last_transport_disposition = disposition
            wake.last_transport_detail = bounded_detail
            wake.owner_input_required = disposition == "owner_input_required"
            wake.claim_id = None
            wake.lease_expires_at = None

            if disposition == "delivered":
                cooldown_until = now + self.MIN_WEB_TURN_INTERVAL_SECONDS
                self._global_cooldown_until = max(self._global_cooldown_until, cooldown_until)
                self._cooldown_until[channel_id] = max(
                    self._cooldown_until.get(channel_id, 0.0), cooldown_until
                )
                wake.transport_delivered = True
                wake.transport_delivered_at = now
                if wake.model_acknowledged:
                    continuation_id = wake.continuation_id
                    next_continuation_id = self._promote_queued_locked(channel_id, wake, now)
                    self._save_state()
                    return {
                        "channel_id": channel_id,
                        "continuation_id": continuation_id,
                        "finalized": True,
                        "transport_name": transport_name,
                        "disposition": disposition,
                        "transport_delivered": True,
                        "model_acknowledged": True,
                        "owner_input_required": False,
                        "followup_pending": next_continuation_id is not None,
                        "next_continuation_id": next_continuation_id,
                    }
                wake.available_at = now
                wake.escalation_at = now + wake.escalation_delay_seconds
            elif disposition in {"uncertain", "owner_input_required"}:
                wake.escalation_at = now

            self._save_state()
            return {
                "channel_id": channel_id,
                "continuation_id": wake.continuation_id,
                "finalized": True,
                "transport_name": transport_name,
                "disposition": disposition,
                "transport_delivered": wake.transport_delivered,
                "owner_input_required": wake.owner_input_required,
            }

    async def authorize_browser_preflight(
        self, channel_id: str, continuation_id: str
    ) -> dict:
        """Authorize one fresh Browser Host delivery attempt for a resilient continuation."""
        channel_id = self.validate_channel(channel_id)
        continuation_id = self.validate_continuation_id(continuation_id)
        now = time.time()
        async with self._lock:
            wake = self._pending.get(channel_id)
            if (
                wake is None
                or wake.continuation_id != continuation_id
                or not wake.model_ack_required
                or wake.transport_delivered
                or wake.model_acknowledged
                or self._automatic_delivery_blocked(wake)
                or self._undelivered_expired(wake, now)
                or self._lease_active(wake, now)
            ):
                return {
                    "channel_id": channel_id,
                    "continuation_id": continuation_id,
                    "authorized": False,
                }
            wake.browser_preflight_authorized_at = now
            self._save_state()
            return {
                "channel_id": channel_id,
                "continuation_id": continuation_id,
                "authorized": True,
                "expires_after_seconds": self.BROWSER_PREFLIGHT_TTL_SECONDS,
            }

    async def ack(
        self, channel_id: str, claim_id: str, *, delivery_lease: str | None = None
    ) -> dict:
        "Acknowledge one iframe transport delivery attempt."
        channel_id = self.validate_channel(channel_id)
        if not self._delivery_lease_matches(channel_id, delivery_lease):
            return {
                "channel_id": channel_id,
                "acknowledged": False,
                "state": "standby",
                "delivery_lease_required": True,
            }
        now = time.time()
        async with self._lock:
            wake = self._pending.get(channel_id)
            if wake is None or wake.claim_id != claim_id:
                return {"channel_id": channel_id, "acknowledged": False}
            cooldown_until = now + self.MIN_WEB_TURN_INTERVAL_SECONDS
            self._global_cooldown_until = max(self._global_cooldown_until, cooldown_until)
            self._cooldown_until[channel_id] = max(
                self._cooldown_until.get(channel_id, 0.0),
                cooldown_until,
            )
            if not wake.model_ack_required or wake.model_acknowledged:
                continuation_id = wake.continuation_id
                next_continuation_id = None
                if wake.model_ack_required and wake.model_acknowledged:
                    next_continuation_id = self._promote_queued_locked(channel_id, wake, now)
                else:
                    del self._pending[channel_id]
                self._save_state()
                data = {"channel_id": channel_id, "acknowledged": True}
                if continuation_id is not None:
                    data.update({
                        "continuation_id": continuation_id,
                        "model_acknowledged": True,
                        "followup_pending": next_continuation_id is not None,
                        "next_continuation_id": next_continuation_id,
                    })
                return data

            wake.claim_id = None
            wake.lease_expires_at = None
            wake.transport_delivered = True
            wake.transport_delivered_at = now
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
                "transport_delivered": True,
                "next_retry_seconds": None,
                "escalation_after_seconds": wake.escalation_delay_seconds,
                "web_turn_cooldown_seconds": self.MIN_WEB_TURN_INTERVAL_SECONDS,
            }

    async def observe_model_turn(self, channel_id: str, continuation_id: str) -> dict:
        """Resolve a delivered continuation after Browser Host observes its model turn."""
        channel_id = self.validate_channel(channel_id)
        continuation_id = self.validate_continuation_id(continuation_id)
        now = time.time()
        async with self._lock:
            wake = self._pending.get(channel_id)
            if (
                wake is None
                or wake.continuation_id != continuation_id
                or not wake.transport_delivered
                or wake.model_acknowledged
            ):
                return {
                    "channel_id": channel_id,
                    "continuation_id": continuation_id,
                    "observed": False,
                }
            attempts = wake.delivery_attempts
            queued_events = len(wake.queued_messages)
            cooldown_until = now + self.MIN_WEB_TURN_INTERVAL_SECONDS
            self._global_cooldown_until = max(self._global_cooldown_until, cooldown_until)
            self._cooldown_until[channel_id] = max(
                self._cooldown_until.get(channel_id, 0.0), cooldown_until
            )
            next_continuation_id = self._promote_queued_locked(channel_id, wake, now)
            self._save_state()
            return {
                "channel_id": channel_id,
                "continuation_id": continuation_id,
                "observed": True,
                "delivery_attempts": attempts,
                "queued_events": queued_events,
                "followup_pending": next_continuation_id is not None,
                "next_continuation_id": next_continuation_id,
            }

    async def model_ack(self, continuation_id: str) -> dict:
        continuation_id = self.validate_continuation_id(continuation_id)
        now = time.time()
        async with self._lock:
            for channel_id, wake in list(self._pending.items()):
                if wake.continuation_id != continuation_id:
                    continue
                attempts = wake.delivery_attempts
                batched_messages = list(wake.queued_messages)
                wake.queued_messages.clear()
                wake.queued_escalation_messages.clear()
                if wake.claim_id is not None and self._lease_active(wake, now):
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
                    "batched_messages": batched_messages,
                    "batched_count": len(batched_messages),
                }
            return {"continuation_id": continuation_id, "acknowledged": False}

    async def arm_job_continuation(self, jobs, reason: str, *, channel_id: str, message: str | None = None) -> dict:
        channel_id = self.validate_channel(channel_id)
        job_ids = ",".join(job.job_id for job in jobs)
        suffix = f"; message={message}" if message else ""
        job_states = ", ".join(f"{job.job_id}={job.status.value}" for job in jobs)
        escalation = ("⚠️ Coordinator continuation did not complete through X.\n" f"Channel: {channel_id}\n" f"Jobs: {job_states}\n" f"Reason: {reason}\n" "Please check ChatGPT / Browser Host and continue the work manually.")
        return await self.arm_resilient(f"jobs={job_ids}; reason={reason}{suffix}", channel_id=channel_id, delay_seconds=self.JOB_WAKE_DEBOUNCE_SECONDS, conflict="coalesce", escalation_message=escalation[: self.MAX_ESCALATION_MESSAGE_CHARS])

    async def escalations_due(self) -> list[dict]:
        now = time.time()
        async with self._lock:
            due = []
            for channel_id, wake in self._pending.items():
                if wake.continuation_id is None or wake.model_acknowledged:
                    continue
                stale_undelivered = self._undelivered_expired(wake, now)
                blocked_disposition = (
                    wake.last_transport_disposition
                    if self._automatic_delivery_blocked(wake)
                    else None
                )
                normal_due = (
                    wake.escalation_at is not None
                    and wake.escalation_at <= now
                    and (wake.transport_delivered or wake.delivery_attempts >= wake.max_delivery_attempts)
                )
                if not stale_undelivered and not normal_due and blocked_disposition is None:
                    continue
                if stale_undelivered:
                    escalation_message = (
                        "⚠️ Coordinator continuation expired before X delivery.\n"
                        f"Channel: {channel_id}\n"
                        f"Pending: {wake.message[:700]}\n"
                        "Please check ChatGPT / Browser Host and continue the work manually."
                    )
                elif blocked_disposition is not None:
                    escalation_message = (
                        f"Coordinator transport {blocked_disposition}: "
                        f"{wake.last_transport_detail or 'no detail'}"
                    )
                else:
                    escalation_message = self._bounded_escalation(
                        (wake.escalation_message, *wake.queued_escalation_messages)
                    )
                due.append(
                    {
                        "continuation_id": wake.continuation_id,
                        "channel_id": channel_id,
                        "delivery_attempts": wake.delivery_attempts,
                        "max_delivery_attempts": wake.max_delivery_attempts,
                        "escalation_message": escalation_message[: self.MAX_ESCALATION_MESSAGE_CHARS],
                        "queued_events": len(wake.queued_messages),
                        "reason": (
                            "undelivered_timeout"
                            if stale_undelivered
                            else f"transport_{blocked_disposition}"
                            if blocked_disposition == "uncertain"
                            else blocked_disposition
                            if blocked_disposition is not None
                            else "delivery_exhausted"
                        ),
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
