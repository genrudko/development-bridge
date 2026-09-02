from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from app.api.errors import BridgeError, ErrorCode

_ROUTE_RE = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
_ALLOWED_STATUSES = {"planning", "working", "waiting", "blocked", "completed"}
_TEXT_LIMITS = {
    "title": 160,
    "phase": 160,
    "current": 300,
    "next": 300,
    "detail": 500,
}
_PATH_LOCKS_GUARD = RLock()
_PATH_LOCKS: dict[Path, RLock] = {}


def _path_lock(path: Path) -> RLock:
    canonical = path.resolve()
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(canonical, RLock())


class RouteProgressStore:
    """Small durable work-progress checkpoints keyed by logical route."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        self._lock = _path_lock(self.path)

    @staticmethod
    def _route_id(value: str) -> str:
        route_id = str(value).strip().lower()
        if not _ROUTE_RE.fullmatch(route_id):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "route_id is invalid")
        return route_id

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"version": 1, "progress": {}}
        except (OSError, json.JSONDecodeError) as exc:
            raise BridgeError(ErrorCode.INTERNAL_ERROR, f"route progress store is unreadable: {exc}") from exc
        if data.get("version") != 1 or not isinstance(data.get("progress"), dict):
            raise BridgeError(ErrorCode.INTERNAL_ERROR, "route progress store format is invalid")
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def get(self, route_id: str) -> dict[str, Any] | None:
        route_id = self._route_id(route_id)
        with self._lock:
            item = self._load()["progress"].get(route_id)
            return {**item, "route_id": route_id} if isinstance(item, dict) else None

    def update(self, route_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        route_id = self._route_id(route_id)
        with self._lock:
            data = self._load()
            item = self._build_update(data["progress"].get(route_id), changes)
            data["progress"][route_id] = item
            self._save(data)
            return {**item, "route_id": route_id}

    @staticmethod
    def _build_update(previous: Any, changes: dict[str, Any]) -> dict[str, Any]:
        item = dict(previous) if isinstance(previous, dict) else {}

        operation_id = changes.get("operation_id")
        if operation_id is not None:
            operation_id = str(operation_id).strip()
            if not operation_id or operation_id != item.get("operation_id"):
                raise BridgeError(
                    ErrorCode.INVALID_ARGUMENT,
                    "operation_id does not match the current progress operation",
                )

        for field, limit in _TEXT_LIMITS.items():
            if field not in changes:
                continue
            value = str(changes[field]).strip()
            if not value or len(value) > limit:
                raise BridgeError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"{field} must contain 1 to {limit} characters",
                )
            item[field] = value

        if "status" in changes:
            status = str(changes["status"]).strip().lower()
            if status not in _ALLOWED_STATUSES:
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "progress status is invalid")
            item["status"] = status
        elif "status" not in item:
            item["status"] = "working"

        if "total" in changes:
            total = int(changes["total"])
            if total < 1 or total > 1000:
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "total must be between 1 and 1000")
            item["total"] = total
        if "completed" in changes:
            completed = int(changes["completed"])
            if completed < 0:
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "completed must be non-negative")
            item["completed"] = completed

        if not item.get("title") or "total" not in item:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "initial progress update requires title and total",
            )

        item.setdefault("operation_id", uuid4().hex)

        item.setdefault("completed", 0)
        if item["completed"] > item["total"]:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "completed cannot exceed total")
        if item["status"] == "completed" and "completed" not in changes:
            item["completed"] = item["total"]

        item["percent"] = round((item["completed"] / item["total"]) * 100)
        item["revision"] = int(item.get("revision", 0)) + 1
        item["updated_at"] = datetime.now(UTC).isoformat()
        return item

    def start(self, route_id: str, values: dict[str, Any]) -> dict[str, Any]:
        route_id = self._route_id(route_id)
        changes = dict(values)
        with self._lock:
            data = self._load()
            item = self._build_update(None, changes)
            data["progress"][route_id] = item
            self._save(data)
            return {**item, "route_id": route_id}

    def clear(self, route_id: str) -> dict[str, Any]:
        route_id = self._route_id(route_id)
        with self._lock:
            data = self._load()
            existed = data["progress"].pop(route_id, None) is not None
            if existed:
                self._save(data)
            return {"route_id": route_id, "cleared": existed}
