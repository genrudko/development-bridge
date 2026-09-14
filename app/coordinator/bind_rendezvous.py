from __future__ import annotations

import asyncio
import inspect
import json
import math
import os
import re
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_urlsafe
from typing import Any

from app.api.errors import BridgeError, ErrorCode
from app.coordinator.review_gpt_transport import RendezvousResolution
from app.coordinator.route_control import RouteControlService
from app.coordinator.routes import RouteRegistry


DEFAULT_TTL_SECONDS = 30 * 60
RETRY_DELAYS = (5, 15, 30, 60, 120)
LIVE_STATES = frozenset({"pending", "owner_input_required"})
TERMINAL_STATES = frozenset({"bound", "failed"})
_RECORD_KEYS = frozenset(
    {
        "route_id",
        "expected_generation",
        "nonce",
        "created_at",
        "expires_at",
        "attempt_count",
        "state",
        "next_attempt_at",
        "terminal_error_code",
        "allow_project_change",
        "resulting_generation",
    }
)
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{22,}$")

Resolver = Callable[[str], Awaitable[RendezvousResolution]]
Clock = Callable[[], float]
Sleeper = Callable[[float], Awaitable[None]]


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()


class BindRendezvousService:
    """Durably resolve a safe nonce marker into an existing guarded route bind."""

    def __init__(
        self,
        route_registry: RouteRegistry,
        route_control: RouteControlService,
        *,
        resolver: Resolver | Any,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock: Clock = time.time,
        sleep: Sleeper = asyncio.sleep,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self.route_registry = route_registry
        self.route_control = route_control
        self.path = route_registry.path.parent / "bind-rendezvous.json"
        self._resolver = resolver
        self._ttl_seconds = float(ttl_seconds)
        self._clock = clock
        self._sleep = sleep
        self._poll_interval_seconds = max(0.001, float(poll_interval_seconds))
        self._task: asyncio.Task | None = None
        self._records = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            raise BridgeError(ErrorCode.INTERNAL_ERROR, "bind rendezvous state is unreadable") from exc
        try:
            if not isinstance(payload, dict) or set(payload) != {"version", "records"}:
                raise ValueError
            if type(payload["version"]) is not int or payload["version"] != 1 or not isinstance(payload["records"], dict):
                raise ValueError
            records: dict[str, dict[str, Any]] = {}
            for route_key, raw in payload["records"].items():
                if not isinstance(route_key, str) or not isinstance(raw, dict):
                    raise ValueError
                if not set(raw).issubset(_RECORD_KEYS) or set(raw) < {
                    "route_id", "expected_generation", "nonce", "created_at", "expires_at",
                    "attempt_count", "state", "next_attempt_at", "terminal_error_code",
                    "allow_project_change",
                }:
                    raise ValueError
                if raw["route_id"] != route_key or self.route_registry.validate_route_id(route_key) != route_key:
                    raise ValueError
                if type(raw["expected_generation"]) is not int or raw["expected_generation"] < 0:
                    raise ValueError
                if type(raw["attempt_count"]) is not int or raw["attempt_count"] < 0:
                    raise ValueError
                if type(raw["allow_project_change"]) is not bool:
                    raise ValueError
                if raw["state"] not in LIVE_STATES | TERMINAL_STATES:
                    raise ValueError
                if not isinstance(raw["nonce"], str) or not _NONCE_RE.fullmatch(raw["nonce"]):
                    raise ValueError
                if not all(type(raw[key]) in (int, float) for key in ("created_at", "expires_at")):
                    raise ValueError
                if not all(math.isfinite(float(raw[key])) for key in ("created_at", "expires_at")):
                    raise ValueError
                if raw["expires_at"] <= raw["created_at"]:
                    raise ValueError
                if raw["next_attempt_at"] is not None and type(raw["next_attempt_at"]) not in (int, float):
                    raise ValueError
                if raw["next_attempt_at"] is not None and not math.isfinite(float(raw["next_attempt_at"])):
                    raise ValueError
                if raw["terminal_error_code"] is not None and not isinstance(raw["terminal_error_code"], str):
                    raise ValueError
                if "resulting_generation" in raw and type(raw["resulting_generation"]) is not int:
                    raise ValueError
                records[route_key] = dict(raw)
            return records
        except (BridgeError, TypeError, ValueError, KeyError) as exc:
            raise BridgeError(ErrorCode.INTERNAL_ERROR, "bind rendezvous state format is invalid") from exc

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.tmp")
        payload = {"version": 1, "records": self._records}
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as exc:
            with suppress(OSError):
                tmp.unlink()
            raise BridgeError(ErrorCode.INTERNAL_ERROR, "bind rendezvous state could not be saved") from exc

    def prepare(self, route_id: str, allow_project_change: bool = False) -> dict:
        route_id = self.route_registry.validate_route_id(route_id)
        route = self.route_registry.resolve(route_id)
        if route is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")
        now = self._clock()
        existing = self._records.get(route_id)
        if (
            existing
            and existing["state"] in LIVE_STATES
            and existing["expected_generation"] != int(route.get("generation", 0))
        ):
            self._terminal(existing, "RENDEZVOUS_GENERATION_CHANGED")
        if existing and existing["state"] in LIVE_STATES and now < existing["expires_at"]:
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                f"bind rendezvous already pending for route: {route_id}",
                retryable=True,
            )
        if existing and existing["state"] in LIVE_STATES:
            existing.update(
                state="failed", next_attempt_at=None,
                terminal_error_code="RENDEZVOUS_EXPIRED",
            )
            self._save()
        nonce = token_urlsafe(24)
        record = {
            "route_id": route_id,
            "expected_generation": int(route.get("generation", 0)),
            "nonce": nonce,
            "created_at": now,
            "expires_at": now + self._ttl_seconds,
            "attempt_count": 0,
            "state": "pending",
            "next_attempt_at": now,
            "terminal_error_code": None,
            "allow_project_change": bool(allow_project_change),
        }
        self._records[route_id] = record
        self._save()
        return self._prepare_view(record)

    def status(self, route_id: str) -> dict:
        route_id = self.route_registry.validate_route_id(route_id)
        record = self._records.get(route_id)
        if record is None:
            return {"route_id": route_id, "state": "none"}
        return self._status_view(record)

    @staticmethod
    def _prepare_view(record: dict[str, Any]) -> dict:
        return {
            "route_id": record["route_id"],
            "state": record["state"],
            "generation": record["expected_generation"],
            "marker": f"DBRIDGE_BIND bnd_{record['nonce']}",
            "expires_at": _iso(record["expires_at"]),
        }

    @staticmethod
    def _status_view(record: dict[str, Any]) -> dict:
        result = {
            "route_id": record["route_id"],
            "state": record["state"],
            "generation": record["expected_generation"],
            "attempt_count": record["attempt_count"],
            "expires_at": _iso(record["expires_at"]),
            "expires_at_epoch": record["expires_at"],
            "terminal_error_code": record["terminal_error_code"],
            "next_attempt_at": (
                _iso(record["next_attempt_at"]) if record["next_attempt_at"] is not None else None
            ),
            "next_attempt_at_epoch": record["next_attempt_at"],
        }
        if "resulting_generation" in record:
            result["resulting_generation"] = record["resulting_generation"]
        return result

    async def start(self) -> None:
        if self._task is None or self._task.done():
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
                await self.run_due_once()
                await self._sleep(self._poll_interval_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Records remain due and retryable; never log resolver exception details.
                await self._sleep(self._poll_interval_seconds)

    async def run_due_once(self) -> None:
        now = self._clock()
        for route_id in list(self._records):
            record = self._records.get(route_id)
            if record is None or record["state"] not in LIVE_STATES:
                continue
            if now >= record["expires_at"]:
                self._terminal(record, "RENDEZVOUS_EXPIRED")
                continue
            if record["next_attempt_at"] is not None and now >= record["next_attempt_at"]:
                await self._attempt(record)

    async def _resolve(self, marker: str) -> RendezvousResolution:
        resolver = self._resolver
        callback = resolver if callable(resolver) else resolver.resolve_bind_marker
        result = callback(marker)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, RendezvousResolution):
            raise TypeError("resolver returned invalid result")
        return result

    async def _attempt(self, record: dict[str, Any]) -> None:
        marker = f"DBRIDGE_BIND bnd_{record['nonce']}"
        try:
            resolution = await self._resolve(marker)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._retry(record, "pending")
            return
        if self._clock() >= record["expires_at"]:
            self._terminal(record, "RENDEZVOUS_EXPIRED")
            return
        if resolution.status == "ambiguous":
            self._terminal(record, "RENDEZVOUS_AMBIGUOUS")
        elif resolution.status == "unique" and resolution.candidate_url:
            await self._bind_unique(record, resolution.candidate_url)
        elif resolution.status == "owner_input_required":
            self._retry(record, "owner_input_required")
        else:
            self._retry(record, "pending")

    def _retry(self, record: dict[str, Any], state: str) -> None:
        record["attempt_count"] += 1
        delay = RETRY_DELAYS[min(record["attempt_count"] - 1, len(RETRY_DELAYS) - 1)]
        record["state"] = state
        record["next_attempt_at"] = self._clock() + delay
        record["terminal_error_code"] = None
        self._save()

    def _terminal(self, record: dict[str, Any], error_code: str) -> None:
        record["state"] = "failed"
        record["next_attempt_at"] = None
        record["terminal_error_code"] = error_code
        self._save()

    async def _bind_unique(self, record: dict[str, Any], candidate_url: str) -> None:
        operation_id: str | None = None
        route_id = record["route_id"]
        async with self.route_registry.route_lock(route_id):
            route = self.route_registry.resolve(route_id)
            if route is None:
                self._terminal(record, "RENDEZVOUS_ROUTE_DELETED")
                return
            if int(route.get("generation", 0)) != record["expected_generation"]:
                self._terminal(record, "RENDEZVOUS_GENERATION_CHANGED")
                return
            try:
                prepared = self.route_control.prepare_bind(
                    route_id,
                    session_id=None,
                    allow_project_change=record["allow_project_change"],
                    bootstrap_if_missing=False,
                )
                operation_id = str(prepared["operation_id"])
                self.route_control.accept_bind_return(
                    operation_id, candidate_url, retain_return_target=False
                )
                committed = self.route_control.commit_bind(operation_id)
            except Exception as exc:
                if operation_id is not None:
                    with suppress(Exception):
                        self.route_registry.discard_current_bind(route_id, operation_id)
                message = str(exc).lower() if isinstance(exc, BridgeError) else ""
                code = (
                    "RENDEZVOUS_PROJECT_POLICY"
                    if "project" in message
                    else "RENDEZVOUS_BIND_FAILED"
                )
                self._terminal(record, code)
                return
            record["state"] = "bound"
            record["next_attempt_at"] = None
            record["terminal_error_code"] = None
            record["resulting_generation"] = int(committed["generation"])
            self._save()
