from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
from typing import Any

from app.api.errors import BridgeError, ErrorCode
from app.coordinator.routes import RouteRegistry
from app.coordinator.service import CoordinatorService
from app.coordinator.wake_transport import (
    WakeDeliveryRequest,
    WakeDeliveryResult,
    WakeProbeResult,
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
    ) -> None:
        self._coordinator = coordinator
        self._route_registry = route_registry
        self._transport = transport
        self._enabled = bool(enabled)
        self._poll_interval_seconds = max(1.0, min(float(poll_interval_seconds), 300.0))
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
            bounded_reason = collapsed[:500]
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
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Error during coordinator wake delivery cycle: %s", exc)
            await asyncio.sleep(self._poll_interval_seconds)

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

            channel_id = channel_id.strip()
            status = await self._coordinator.status(channel_id, delivery_mode="direct")
            continuation_id = status.get("continuation_id")
            if (
                not status.get("ready")
                or not isinstance(continuation_id, str)
                or not continuation_id.strip()
            ):
                continue

            target = WakeTarget(
                route_id=route_id.strip(),
                channel_id=channel_id,
                conversation_id=conversation_id.strip(),
                route_url=route_url.strip(),
            )

            try:
                probe_result = await self._transport.probe(target)
            except Exception as exc:
                logger.warning("Probe exception for route %s: %s", route_id, exc)
                continue

            if not probe_result.ready and not probe_result.owner_input_required:
                continue

            if probe_result.owner_input_required:
                claim_result = await self._coordinator.claim(channel_id, delivery_mode="direct")
                if claim_result.get("claimed"):
                    claim_id = str(claim_result["claim_id"])
                    await self._coordinator.finalize_transport(
                        channel_id,
                        claim_id,
                        self._transport.name,
                        "owner_input_required",
                        detail=probe_result.detail,
                    )
                    return
                continue

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
                await self._coordinator.finalize_transport(
                    channel_id,
                    claim_id,
                    self._transport.name,
                    delivery_result.disposition,
                    detail=delivery_result.detail,
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
