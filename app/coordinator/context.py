from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from app.api.errors import BridgeError, ErrorCode


MAX_CONTEXT_CHARS = 16000


def default_route_context_path(route_registry_path: Path) -> Path:
    return route_registry_path.expanduser().parent / "route-contexts.json"


class RouteContextStore:
    """Durable compact coordinator checkpoints keyed by logical route."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"version": 1, "contexts": {}}
        except (OSError, json.JSONDecodeError) as exc:
            raise BridgeError(ErrorCode.INTERNAL_ERROR, f"route context store is unreadable: {exc}") from exc
        if data.get("version") != 1 or not isinstance(data.get("contexts"), dict):
            raise BridgeError(ErrorCode.INTERNAL_ERROR, "route context store format is invalid")
        return data

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def get(self, route_id: str) -> dict | None:
        data = self._load()
        item = data["contexts"].get(route_id)
        return {**item, "route_id": route_id} if item else None

    def update(self, route_id: str, content: str, *, expected_revision: int | None = None) -> dict:
        content = str(content).strip()
        if not content or len(content) > MAX_CONTEXT_CHARS:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                f"route context must contain 1 to {MAX_CONTEXT_CHARS} characters",
            )
        data = self._load()
        previous = data["contexts"].get(route_id)
        current_revision = int((previous or {}).get("revision", 0))
        if expected_revision is not None and expected_revision != current_revision:
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                "route context revision changed",
                retryable=True,
                details={"route_id": route_id, "current_revision": current_revision},
            )
        item = {
            "revision": current_revision + 1,
            "updated_at": datetime.now(UTC).isoformat(),
            "content": content,
        }
        data["contexts"][route_id] = item
        self._save(data)
        return {**item, "route_id": route_id}

    def bootstrap(self, route: dict) -> dict:
        context = self.get(route["route_id"])
        if context is None:
            return {
                "route": route,
                "context": None,
                "bootstrap_message": (
                    f"Logical route {route['route_id']} is active, but no canonical Route Context exists yet. "
                    "Create/update it after restoring the topic state."
                ),
            }
        return {
            "route": route,
            "context": context,
            "bootstrap_message": (
                f"Resume logical route {route['route_id']} using this canonical Route Context as the working checkpoint. "
                "Treat it as authoritative over stale transcript details unless live repository/runtime evidence supersedes it.\n\n"
                + context["content"]
            ),
        }
