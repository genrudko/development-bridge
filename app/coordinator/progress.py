from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

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


class RouteProgressStore:
    """Small durable work-progress checkpoints keyed by logical route."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        self._lock = RLock()

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
            previous = data["progress"].get(route_id)
            item = dict(previous) if isinstance(previous, dict) else {}

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

            item.setdefault("completed", 0)
            if item["completed"] > item["total"]:
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "completed cannot exceed total")
            if item["status"] == "completed" and "completed" not in changes:
                item["completed"] = item["total"]

            item["percent"] = round((item["completed"] / item["total"]) * 100)
            item["revision"] = int(item.get("revision", 0)) + 1
            item["updated_at"] = datetime.now(UTC).isoformat()
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
