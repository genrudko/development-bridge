from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from app.api.errors import BridgeError, ErrorCode

_ROUTE_RE = re.compile(r"^[a-z][a-z0-9-]{0,30}$")


def canonical_chat_url(value: str) -> str:
    parts = urlsplit(str(value).strip())
    if parts.scheme != "https" or parts.netloc != "chatgpt.com" or "/c/" not in parts.path:
        raise BridgeError(ErrorCode.INVALID_ARGUMENT, "url must point to an https://chatgpt.com conversation")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def conversation_parts(url: str) -> tuple[str | None, str]:
    canonical = canonical_chat_url(url)
    path = urlsplit(canonical).path
    conversation_id = path.rsplit("/c/", 1)[1].split("/", 1)[0]
    project_id = None
    for part in path.split("/"):
        if part.startswith("g-p-"):
            project_id = part
            break
    return project_id, conversation_id


def default_route_registry_path() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return base / "development-bridge" / "routes.json"


class RouteRegistry:
    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or default_route_registry_path()).expanduser()

    @staticmethod
    def validate_route_id(route_id: str) -> str:
        route_id = str(route_id).strip().lower()
        if not _ROUTE_RE.fullmatch(route_id):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "route_id is invalid")
        return route_id

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"version": 1, "default_route": None, "requested_route": None, "routes": {}}
        except (OSError, json.JSONDecodeError) as exc:
            raise BridgeError(ErrorCode.INTERNAL_ERROR, f"route registry is unreadable: {exc}") from exc
        if data.get("version") != 1 or not isinstance(data.get("routes"), dict):
            raise BridgeError(ErrorCode.INTERNAL_ERROR, "route registry format is invalid")
        return data

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def snapshot(self) -> dict:
        return self._load()

    def list_routes(self) -> list[dict]:
        data = self._load()
        default_route = data.get("default_route")
        items = []
        for route_id, route in sorted(data["routes"].items()):
            item = dict(route)
            item["route_id"] = route_id
            item["default"] = route_id == default_route
            items.append(item)
        return items

    def list_discovered_chats(self, limit: int = 20) -> list[dict]:
        path = self.path.parent / "chat-registry.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return []
        chats = list((data.get("chats") or {}).values())
        chats.sort(key=lambda item: str(item.get("last_seen", "")), reverse=True)
        return chats[: max(1, min(int(limit), 50))]

    def resolve(self, route_id: str | None = None) -> dict | None:
        data = self._load()
        selected = self.validate_route_id(route_id) if route_id else data.get("default_route")
        if not selected:
            return None
        route = data["routes"].get(selected)
        return {**route, "route_id": selected} if route else None

    def request(self, route_id: str) -> dict:
        route_id = self.validate_route_id(route_id)
        data = self._load()
        if route_id not in data["routes"]:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")
        data["requested_route"] = route_id
        data["requested_at"] = datetime.now(UTC).isoformat()
        self._save(data)
        return {**data["routes"][route_id], "route_id": route_id}

    def select_default(self, route_id: str) -> dict:
        route_id = self.validate_route_id(route_id)
        data = self._load()
        if route_id not in data["routes"]:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")
        data["default_route"] = route_id
        data["requested_route"] = route_id
        data["requested_at"] = datetime.now(UTC).isoformat()
        self._save(data)
        return {**data["routes"][route_id], "route_id": route_id, "default": True}

    def bootstrap(self, route_id: str, url: str, channel_id: str, title: str | None = None) -> dict:
        route_id = self.validate_route_id(route_id)
        canonical = canonical_chat_url(url)
        project_id, conversation_id = conversation_parts(canonical)
        data = self._load()
        if route_id not in data["routes"]:
            data["routes"][route_id] = {
                "title": title or route_id,
                "url": canonical,
                "project_id": project_id,
                "conversation_id": conversation_id,
                "channel_id": channel_id,
                "generation": 0,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            if not data.get("default_route"):
                data["default_route"] = route_id
            if not data.get("requested_route"):
                data["requested_route"] = route_id
            self._save(data)
        return {**data["routes"][route_id], "route_id": route_id}

    def takeover(self, route_id: str, url: str, title: str | None = None, *, make_default: bool = True) -> dict:
        route_id = self.validate_route_id(route_id)
        canonical = canonical_chat_url(url)
        project_id, conversation_id = conversation_parts(canonical)
        data = self._load()
        previous = data["routes"].get(route_id) or {}
        generation = int(previous.get("generation", 0)) + 1
        channel_id = f"telegram-{route_id}-g{generation}"
        route = {
            "title": title or previous.get("title") or route_id,
            "url": canonical,
            "project_id": project_id,
            "conversation_id": conversation_id,
            "channel_id": channel_id,
            "generation": generation,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        data["routes"][route_id] = route
        if make_default or not data.get("default_route"):
            data["default_route"] = route_id
        data["requested_route"] = route_id
        data["requested_at"] = datetime.now(UTC).isoformat()
        self._save(data)
        return {**route, "route_id": route_id, "default": data["default_route"] == route_id}
