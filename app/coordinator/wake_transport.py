from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

WakeDeliveryDisposition = Literal[
    "delivered",
    "not_submitted",
    "uncertain",
    "owner_input_required",
]


@dataclass(frozen=True, slots=True)
class WakeTarget:
    route_id: str
    channel_id: str
    conversation_id: str
    route_url: str
    allow_project_change: bool = False


@dataclass(frozen=True, slots=True)
class WakeProbeResult:
    ready: bool
    owner_input_required: bool = False
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class WakeDiscoveryResult:
    found: bool
    route_url: str | None = None
    conversation_id: str | None = None
    owner_input_required: bool = False
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class WakeDeliveryRequest:
    target: WakeTarget
    continuation_id: str
    prompt: str
    delivery_key: str


@dataclass(frozen=True, slots=True)
class WakeDeliveryResult:
    disposition: WakeDeliveryDisposition
    detail: str | None = None
    receipt_path: Path | None = None
    model_turn_observed: bool = False


@runtime_checkable
class WakeTransport(Protocol):
    name: str

    async def probe(self, target: WakeTarget) -> WakeProbeResult:
        ...

    async def deliver(self, request: WakeDeliveryRequest) -> WakeDeliveryResult:
        ...

    async def discover_current_chat(self, marker: str, target: WakeTarget) -> WakeDiscoveryResult:
        ...
