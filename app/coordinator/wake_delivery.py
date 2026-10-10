from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import suppress

from app.api.errors import BridgeError, ErrorCode
from app.coordinator.routes import RouteRegistry
from app.coordinator.service import CoordinatorService
from app.coordinator.wake_transport import (
    WakeDeliveryRequest,
    WakeTarget,
    WakeTransport,
)

logger = logging.getLogger(__name__)


class CoordinatorWakeDeliveryService:
    """Service that continuously and sequentially delivers coordinator wakes via pluggable direct transports."""

    def __init__(
        self,
        coordinator: CoordinatorService,
        route_registry: RouteRegistry,
        *,
        transport: WakeTransport | None = None,
        enabled: bool = False,
        poll_interval_seconds: float = 5.0,
        probe_timeout_seconds: float = 65.0,
    ) -> None:
        self._coordinator = coordinator
        self._route_registry = route_registry
        self._transport = transport
        self._enabled = bool(enabled)
        self._poll_interval_seconds = max(1.0, min(float(poll_interval_seconds), 300.0))
        self._probe_timeout_seconds = max(1.0, min(float(probe_timeout_seconds), 90.0))
        self._auth_reprobe_after: dict[str, float] = {}
        self._last_status_log: dict[str, tuple[tuple, float]] = {}
        self._task: asyncio.Task | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def transport(self) -> WakeTransport | None:
        return self._transport

    @property
    def poll_interval_seconds(self) -> float:
        return self._poll_interval_seconds

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def build_continuation_prompt(self, continuation_id: str, raw_message: str) -> str:
        collapsed = " ".join(raw_message.split()).strip()
        prefix = (
            f"DBRIDGE_CONTINUE {continuation_id}. "
            "Call coordinator_ack for this continuation_id, process any batched messages it returns, "
            "inspect the durable Bridge job/result state, and continue the current bounded task."
        )
        if collapsed:
            bounded_reason = collapsed[: CoordinatorService.MAX_VISIBLE_CONTINUATION_REASON_CHARS]
            return f"{prefix} {bounded_reason}"
        return prefix

    async def start(self) -> None:
        if not self._enabled:
            return
        if self._task is not None and not self._task.done():
            return
        if self._transport is None:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "Coordinator wake delivery service requires a transport when enabled",
            )
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _loop(self) -> None:
        logger.warning("wake_loop_started transport=%s interval=%s", self._transport.name if self._transport else "none", self._poll_interval_seconds)
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Error during coordinator wake delivery cycle: %s", exc)
            await asyncio.sleep(self._poll_interval_seconds)

    async def complete_rollover_bootstrap(self, route_id: str, token: str) -> dict:
        """Validate, deliver and complete under the same fence as route mutations."""
        async with self._route_registry.route_lock(route_id):
            record = self._route_registry.rollover_for_completion(route_id, token)
            if record.get("bootstrap_sent") is True:
                return {"state": "complete", "rollover": record, "duplicate": True}
            if record.get("bootstrap_delivery_state") in {"sending", "uncertain", "owner_input_required"}:
                return {"state": "bootstrap_waiting", "error": "previous bootstrap requires reconciliation"}
            if self._transport is None:
                return {"state": "bootstrap_waiting", "error": "wake transport unavailable"}
            route = self._route_registry.resolve(route_id)
            target = WakeTarget(
                route_id=route_id,
                channel_id=str(route["channel_id"]),
                conversation_id=str(route["conversation_id"]),
                route_url=str(route["url"]),
            )
            probe = await self._transport.probe(target)
            if not probe.ready or probe.owner_input_required:
                return {"state": "bootstrap_waiting", "error": probe.detail}
            operation_id = f"rollover-bootstrap-{route_id}-g{route['generation']}"
            message = (
                f"Automatic physical-chat rollover completed for logical route {route_id} "
                f"generation {route['generation']}. Before other work, call "
                f"coordinator_route_context_get with route_id={route_id} and use its canonical "
                "Route Context as the authoritative checkpoint. Then continue NEXT ORDER OF WORK."
            )
            # Persist before sending: a lost response or process exit must not cause a resend.
            self._route_registry.record_rollover_bootstrap_delivery(route_id, token, "sending")
            try:
                delivered = await self._transport.deliver(WakeDeliveryRequest(
                    target=target, continuation_id=operation_id,
                    prompt=message, delivery_key=operation_id,
                ))
            except Exception:  # noqa: BLE001 - a lost transport response is an uncertain delivery
                return {"state": "bootstrap_waiting", "error": "bootstrap delivery requires reconciliation"}
            if delivered.disposition != "delivered":
                self._route_registry.record_rollover_bootstrap_delivery(route_id, token, delivered.disposition)
                return {"state": "bootstrap_waiting", "error": delivered.detail}
            completed = self._route_registry.complete_rollover(route_id, token)
            return {"state": "complete", "rollover": completed, "duplicate": False}

    async def run_once(self) -> None:
        if not self._enabled or self._transport is None:
            return

        routes = self._route_registry.list_routes()
        for route in routes:
            route_id = route.get("route_id")
            channel_id = route.get("channel_id")
            conversation_id = route.get("conversation_id")
            route_url = route.get("url")

            if (
                not isinstance(route_id, str)
                or not route_id.strip()
                or not isinstance(channel_id, str)
                or not channel_id.strip()
                or not isinstance(conversation_id, str)
                or not conversation_id.strip()
                or not isinstance(route_url, str)
                or not route_url.strip()
            ):
                continue

            async with self._route_registry.route_lock(route_id):
                current = self._route_registry.resolve(route_id)
                if (
                    current is None
                    or not self._route_registry.is_bound(current)
                    or int(current.get("generation", -1)) != int(route.get("generation", 0))
                    or current.get("channel_id") != channel_id
                ):
                    continue
                channel_id = channel_id.strip()
                status = await self._coordinator.status(channel_id, delivery_mode="direct")
                continuation_id = status.get("continuation_id")
                if isinstance(continuation_id, str):
                    signature = (
                        continuation_id, status.get("state"), status.get("ready"),
                        status.get("x_listener_active"), status.get("delivery_attempts"),
                    )
                    previous, last_logged = self._last_status_log.get(route_id, (None, 0.0))
                    if signature != previous or time.monotonic() - last_logged >= 120.0:
                        logger.warning("wake_status %s", json.dumps({
                            "route": route_id, "continuation": continuation_id,
                            "state": status.get("state"), "ready": status.get("ready"),
                            "x_listener_active": status.get("x_listener_active"),
                            "delivery_attempts": status.get("delivery_attempts"),
                        }))
                        self._last_status_log[route_id] = (signature, time.monotonic())
                if not isinstance(continuation_id, str) or not continuation_id.strip():
                    continue
                auth_recovery = (
                    status.get("state") == "owner_input_required"
                    and status.get("last_transport_name") == self._transport.name
                    and str(status.get("last_transport_detail") or "").startswith((
                        "auth_preflight:", "Probe failed", "Probe process",
                        "Target ChatGPT page requires login",
                    ))
                )
                if not status.get("ready") and not auth_recovery:
                    continue
                if auth_recovery and time.monotonic() < self._auth_reprobe_after.get(route_id, 0.0):
                    continue

                target = WakeTarget(
                    route_id=route_id.strip(),
                    channel_id=channel_id,
                    conversation_id=conversation_id.strip(),
                    route_url=route_url.strip(),
                )

                # Never claim on probe failure. Record classified pre-claim
                # failures so that zero delivery attempts is not mistaken for
                # proof that no probe has run.
                started = time.monotonic()
                if auth_recovery:
                    # Owner sign-in may happen later. Recheck read-only at a
                    # bounded cadence; never replay an uncertain post-send turn.
                    self._auth_reprobe_after[route_id] = started + 60.0
                logger.warning("wake_probe %s", json.dumps({
                    "event": "start", "route": route_id,
                    "continuation": continuation_id, "transport": self._transport.name,
                }))
                try:
                    probe_result = await asyncio.wait_for(
                        self._transport.probe(target),
                        timeout=self._probe_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    logger.warning("wake_probe %s", json.dumps({
                        "event": "finish", "route": route_id,
                        "continuation": continuation_id,
                        "disposition": "timeout",
                        "duration_ms": round((time.monotonic() - started) * 1000),
                    }))
                    continue
                except Exception as exc:
                    logger.warning("wake_probe %s", json.dumps({
                        "event": "finish", "route": route_id,
                        "continuation": continuation_id, "disposition": "unknown",
                        "error_type": type(exc).__name__,
                        "duration_ms": round((time.monotonic() - started) * 1000),
                    }))
                    continue
                disposition = probe_result.disposition or (
                    "ready" if probe_result.ready else
                    "authentication_required" if probe_result.owner_input_required else
                    "unknown"
                )
                logger.warning("wake_probe %s", json.dumps({
                    "event": "finish", "route": route_id,
                    "continuation": continuation_id, "disposition": disposition,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }))
                if auth_recovery:
                    if probe_result.ready and not probe_result.owner_input_required:
                        recovery = await self._coordinator.clear_preclaim_auth_block(
                            channel_id, continuation_id, self._transport.name,
                        )
                        logger.warning("wake_auth_recovery %s", json.dumps({
                            "route": route_id, "continuation": continuation_id,
                            "released": recovery.get("released", False),
                        }))
                    continue

                if not probe_result.ready and not probe_result.owner_input_required:
                    continue

                if probe_result.owner_input_required:
                    logger.warning(
                        "Coordinator direct wake probe blocked route=%s channel=%s continuation=%s transport=%s detail=%s",
                        target.route_id,
                        channel_id,
                        continuation_id.strip(),
                        self._transport.name,
                        probe_result.detail,
                    )
                    await self._coordinator.mark_preclaim_auth_required(
                        channel_id,
                        continuation_id,
                        self._transport.name,
                        detail=probe_result.detail,
                    )
                    self._auth_reprobe_after[route_id] = time.monotonic() + 60.0
                    return

                claim_result = await self._coordinator.claim(channel_id, delivery_mode="direct")
                if not claim_result.get("claimed"):
                    continue

                claim_id = str(claim_result["claim_id"])
                continuation_id = str(claim_result.get("continuation_id") or "")
                raw_message = str(claim_result.get("message") or "")
                prompt = self.build_continuation_prompt(continuation_id, raw_message)

                request = WakeDeliveryRequest(
                    target=target,
                    continuation_id=continuation_id,
                    prompt=prompt,
                    delivery_key=continuation_id,
                )

                try:
                    delivery_result = await self._transport.deliver(request)
                    logger.warning(
                        "Coordinator direct wake delivery result route=%s channel=%s continuation=%s transport=%s disposition=%s model_turn_observed=%s detail=%s receipt=%s",
                        target.route_id,
                        channel_id,
                        continuation_id,
                        self._transport.name,
                        delivery_result.disposition,
                        delivery_result.model_turn_observed,
                        delivery_result.detail,
                        delivery_result.receipt_path,
                    )
                    await self._coordinator.finalize_transport(
                        channel_id,
                        claim_id,
                        self._transport.name,
                        delivery_result.disposition,
                        detail=delivery_result.detail,
                    )
                    if (
                        delivery_result.disposition == "delivered"
                        and delivery_result.model_turn_observed
                    ):
                        observation = await self._coordinator.observe_model_turn(
                            channel_id, continuation_id
                        )
                        logger.warning(
                            "Coordinator direct wake model observation channel=%s continuation=%s observed=%s",
                            channel_id,
                            continuation_id,
                            observation.get("observed", False),
                        )
                except Exception as exc:
                    logger.error(
                        "Unexpected exception during wake delivery for continuation %s: %s",
                        continuation_id,
                        exc,
                    )
                    await self._coordinator.finalize_transport(
                        channel_id,
                        claim_id,
                        self._transport.name,
                        "uncertain",
                        detail=f"Delivery exception: {str(exc)[:500]}",
                    )

                # Single lane: after any successful claim/finalization, stop scanning routes for this cycle.
                return
