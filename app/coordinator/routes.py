from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_urlsafe
from typing import Self

from app.api.errors import BridgeError, ErrorCode
from app.coordinator.chatgpt_target import parse_chatgpt_target

_ROUTE_RE = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
_ROUTE_CHANNEL_RE = re.compile(
    r"^telegram-(?P<route_id>[a-z][a-z0-9-]{0,30})-g(?P<generation>[0-9]+)$"
)

_PROJECT_STABLE_ID_RE = re.compile(r"^(g-p-[0-9a-fA-F]{32})(?:-|$)")
_CURRENT_BIND_TTL_SECONDS = 10 * 60


def project_identity(project_id: str | None) -> str | None:
    if project_id is None:
        return None
    value = str(project_id).strip()
    match = _PROJECT_STABLE_ID_RE.match(value)
    return match.group(1).lower() if match else value


def canonical_chat_url(value: str) -> str:
    return parse_chatgpt_target(value).route_url


def conversation_parts(url: str) -> tuple[str | None, str]:
    target = parse_chatgpt_target(url)
    return target.project_id, target.conversation_id


def default_route_registry_path() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return base / "development-bridge" / "routes.json"


class AsyncRLock:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._owner: asyncio.Task | None = None
        self._count = 0

    def locked(self) -> bool:
        return self._lock.locked()

    async def acquire(self) -> bool:
        current = asyncio.current_task()
        if self._owner is not None and self._owner is current:
            self._count += 1
            return True
        await self._lock.acquire()
        self._owner = current
        self._count = 1
        return True

    def release(self) -> None:
        current = asyncio.current_task()
        if self._owner is not current:
            raise RuntimeError("Cannot release un-acquired lock")
        self._count -= 1
        if self._count == 0:
            self._owner = None
            self._lock.release()

    async def __aenter__(self) -> Self:
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()


class RouteRegistry:
    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or default_route_registry_path()).expanduser()
        self._route_locks: dict[str, AsyncRLock] = {}

    def route_lock(self, route_id: str) -> AsyncRLock:
        route_id = self.validate_route_id(route_id)
        if not hasattr(self, "_route_locks"):
            self._route_locks = {}
        if route_id not in self._route_locks:
            self._route_locks[route_id] = AsyncRLock()
        return self._route_locks[route_id]


    @staticmethod
    def validate_route_id(route_id: str) -> str:
        route_id = str(route_id).strip().lower()
        if not _ROUTE_RE.fullmatch(route_id):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "route_id is invalid")
        return route_id

    @staticmethod
    def is_bound(route: dict | None) -> bool:
        if not isinstance(route, dict):
            return False
        if route.get("binding_state") not in (None, "bound"):
            return False
        return bool(route.get("url") and route.get("conversation_id"))

    @classmethod
    def _normalize_route_record(cls, route: dict) -> dict:
        item = dict(route)
        if "binding_state" not in item:
            item["binding_state"] = "bound" if cls.is_bound(item) else "unbound"
        return item

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
            item = self._normalize_route_record(route)
            item["route_id"] = route_id
            item["default"] = route_id == default_route
            items.append(item)
        return items

    def list_safe_routes(self) -> list[dict]:
        """Project route records onto fields safe for model-visible status."""
        return [
            {
                "route_id": item["route_id"],
                "title": item.get("title") or item["route_id"],
                "binding_state": "bound" if self.is_bound(item) else "unbound",
                "channel_id": item.get("channel_id"),
                "generation": int(item.get("generation", 0)),
                "default": bool(item.get("default", False)),
            }
            for item in self.list_routes()
        ]

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
        if not route:
            return None
        normalized = self._normalize_route_record(route)
        return {**normalized, "route_id": selected}

    def route_for_channel(self, channel_id: str) -> dict | None:
        channel = str(channel_id).strip()
        data = self._load()
        for route_id, route in data["routes"].items():
            if route.get("channel_id") == channel:
                normalized = self._normalize_route_record(route)
                return {**normalized, "route_id": route_id, "route_state": "active"}
        for route_id, pending in (data.get("rollovers") or {}).items():
            if isinstance(pending, dict) and pending.get("channel_id") == channel:
                return {
                    "route_id": route_id,
                    "channel_id": channel,
                    "generation": int(pending.get("target_generation", 0)),
                    "route_state": "pending",
                    "project_id": pending.get("project_id"),
                    "url": pending.get("candidate_url"),
                }
        return None

    def wake_route_for_channel(self, channel_id: str) -> dict | None:
        """Resolve only the current active route; reserve all route-generation aliases."""
        channel = str(channel_id).strip()
        route = self.route_for_channel(channel)
        if route is not None:
            if route.get("route_state") != "active":
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    "A pending route-generation channel cannot be targeted before it is current",
                )
            return route
        if _ROUTE_CHANNEL_RE.fullmatch(channel):
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                "An unregistered route-generation channel cannot be targeted",
            )
        return None

    def mount_route_for_channel(self, channel_id: str) -> dict | None:
        """Resolve an exact registered active or pending channel for MCP App mounting."""
        channel = str(channel_id).strip()
        route = self.route_for_channel(channel)
        if route is not None:
            return route
        if _ROUTE_CHANNEL_RE.fullmatch(channel):
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                "An unregistered route-generation channel cannot be mounted",
            )
        return None

    def require_wakeable_route(
        self,
        route_id: str,
        *,
        expected_generation: int | None = None,
        expected_channel: str | None = None,
    ) -> dict:
        """Return the active bound route only when its source generation is not frozen by rollover."""
        route_id = self.validate_route_id(route_id)
        data = self._load()
        route = data["routes"].get(route_id)
        if route is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")
        normalized = self._normalize_route_record(route)
        if not self.is_bound(normalized):
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                f"Route '{route_id}' is unbound; wake is suppressed",
                details={"route_id": route_id, "error_code": "ROUTE_UNBOUND"},
            )
        generation = int(normalized.get("generation", 0))
        channel_id = str(normalized.get("channel_id") or f"telegram-{route_id}-g{generation}")
        if (
            expected_generation is not None
            and int(expected_generation) != generation
        ) or (expected_channel is not None and str(expected_channel) != channel_id):
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                "Route generation or channel changed before wake",
                retryable=True,
                details={"route_id": route_id, "error_code": "ROUTE_STALE"},
            )
        pending = (data.get("rollovers") or {}).get(route_id)
        if (
            isinstance(pending, dict)
            and int(pending.get("source_generation", -1)) == generation
            and pending.get("state") in {"prepared", "candidate"}
        ):
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                f"Route '{route_id}' rollover is pending; new wakes are suppressed",
                retryable=True,
                details={"route_id": route_id, "error_code": "ROLLOVER_PENDING"},
            )
        return {**normalized, "route_id": route_id}

    def request(self, route_id: str) -> dict:
        route_id = self.validate_route_id(route_id)
        data = self._load()
        if route_id not in data["routes"]:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")
        data["requested_route"] = route_id
        data["requested_at"] = datetime.now(UTC).isoformat()
        self._save(data)
        return {**self._normalize_route_record(data["routes"][route_id]), "route_id": route_id}

    def select_default(self, route_id: str) -> dict:
        route_id = self.validate_route_id(route_id)
        data = self._load()
        if route_id not in data["routes"]:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")
        data["default_route"] = route_id
        data["requested_route"] = route_id
        data["requested_at"] = datetime.now(UTC).isoformat()
        self._save(data)
        return {**self._normalize_route_record(data["routes"][route_id]), "route_id": route_id, "default": True}

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
                "binding_state": "bound",
                "updated_at": datetime.now(UTC).isoformat(),
            }
            if not data.get("default_route"):
                data["default_route"] = route_id
            if not data.get("requested_route"):
                data["requested_route"] = route_id
            self._save(data)
        return {**self._normalize_route_record(data["routes"][route_id]), "route_id": route_id}

    def pending_current_bind(self, route_id: str) -> dict | None:
        route_id = self.validate_route_id(route_id)
        data = self._load()
        pending = (data.get("current_binds") or {}).get(route_id)
        if not isinstance(pending, dict):
            return None
        route = data["routes"].get(route_id)
        if self._current_bind_is_stale(pending, route):
            data.get("current_binds", {}).pop(route_id, None)
            self._save(data)
            return None
        return {**pending, "route_id": route_id}

    def route_id_for_current_bind_token(self, token: str) -> str | None:
        data = self._load()
        for route_id, pending in list((data.get("current_binds") or {}).items()):
            if not isinstance(pending, dict) or pending.get("token") != token:
                continue
            if self._current_bind_is_stale(pending, data["routes"].get(route_id)):
                data.get("current_binds", {}).pop(route_id, None)
                self._save(data)
                return None
            return route_id
        return None

    @staticmethod
    def _current_bind_is_stale(pending: dict, route: dict | None) -> bool:
        if not isinstance(route, dict):
            return True
        try:
            created_at = datetime.fromisoformat(str(pending.get("created_at") or ""))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            expired = (
                datetime.now(UTC) - created_at.astimezone(UTC)
            ).total_seconds() > _CURRENT_BIND_TTL_SECONDS
        except (TypeError, ValueError):
            expired = True
        if expired:
            return True
        try:
            return int(pending.get("source_generation", -1)) != int(
                route.get("generation", 0)
            )
        except (TypeError, ValueError):
            return True

    def prepare_current_bind(self, route_id: str, *, session_id: str | None, allow_project_change: bool = False) -> dict:
        route_id = self.validate_route_id(route_id)
        data = self._load()
        route = data["routes"].get(route_id)
        if route is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")
        binds = data.setdefault("current_binds", {})
        existing = binds.get(route_id)
        if isinstance(existing, dict):
            try:
                created_at = datetime.fromisoformat(str(existing.get("created_at") or ""))
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=UTC)
                stale = (datetime.now(UTC) - created_at.astimezone(UTC)).total_seconds() > _CURRENT_BIND_TTL_SECONDS
            except (TypeError, ValueError):
                stale = True
            if stale or int(existing.get("source_generation", -1)) != int(route.get("generation", 0)):
                del binds[route_id]
                existing = None
            elif (
                int(existing.get("source_generation", -1)) == int(route.get("generation", 0))
                and existing.get("session_id") == session_id
                and bool(existing.get("allow_project_change", False)) is bool(allow_project_change)
                and existing.get("state") in {"prepared", "candidate"}
            ):
                return {**existing, "route_id": route_id}
            else:
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    f"current-chat bind already pending for route: {route_id}",
                    retryable=True,
                )
        token = f"bind_{token_urlsafe(24)}"
        marker = "DBRIDGE_ROUTE_BIND_" + token.removeprefix("bind_")
        channel_id = route.get("channel_id") or f"telegram-{route_id}-g{int(route.get('generation', 0))}"
        pending = {
            "token": token,
            "marker": marker,
            "state": "prepared",
            "source_generation": int(route.get("generation", 0)),
            "channel_id": channel_id,
            "session_id": session_id,
            "allow_project_change": bool(allow_project_change),
            "created_at": datetime.now(UTC).isoformat(),
        }
        binds[route_id] = pending
        self._save(data)
        return {**pending, "route_id": route_id}

    def record_current_bind_candidate(self, route_id: str, token: str, url: str) -> dict:
        route_id = self.validate_route_id(route_id)
        canonical = canonical_chat_url(url)
        project_id, conversation_id = conversation_parts(canonical)
        data = self._load()
        route = data["routes"].get(route_id)
        pending = (data.get("current_binds") or {}).get(route_id)
        if route is None or not isinstance(pending, dict) or pending.get("token") != token:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "current-chat bind token is invalid or stale")
        try:
            created_at = datetime.fromisoformat(str(pending.get("created_at") or ""))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            stale = (datetime.now(UTC) - created_at.astimezone(UTC)).total_seconds() > _CURRENT_BIND_TTL_SECONDS
        except (TypeError, ValueError):
            stale = True
        if stale:
            data.get("current_binds", {}).pop(route_id, None)
            self._save(data)
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "current-chat bind token is invalid or stale")
        if pending.get("state") != "prepared":
            raise BridgeError(ErrorCode.POLICY_VIOLATION, "current-chat bind candidate already recorded")
        if int(route.get("generation", 0)) != int(pending.get("source_generation", -1)):
            raise BridgeError(ErrorCode.POLICY_VIOLATION, "active route changed during current-chat bind")
        if (
            project_identity(project_id) != project_identity(route.get("project_id"))
            and not bool(pending.get("allow_project_change", False))
        ):
            raise BridgeError(ErrorCode.POLICY_VIOLATION, "current-chat bind candidate belongs to a different project")
        pending.update({
            "state": "candidate",
            "candidate_url": canonical,
            "candidate_conversation_id": conversation_id,
            "candidate_project_id": project_id,
            "candidate_seen_at": datetime.now(UTC).isoformat(),
        })
        self._save(data)
        return {**pending, "route_id": route_id}

    def complete_current_bind(self, route_id: str, token: str, url: str | None = None) -> dict:
        route_id = self.validate_route_id(route_id)
        data = self._load()
        route = data["routes"].get(route_id)
        pending = (data.get("current_binds") or {}).get(route_id)
        if route is None or not isinstance(pending, dict) or pending.get("token") != token:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "current-chat bind token is invalid or stale")
        try:
            created_at = datetime.fromisoformat(str(pending.get("created_at") or ""))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            stale = (datetime.now(UTC) - created_at.astimezone(UTC)).total_seconds() > _CURRENT_BIND_TTL_SECONDS
        except (TypeError, ValueError):
            stale = True
        if stale:
            data.get("current_binds", {}).pop(route_id, None)
            self._save(data)
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "current-chat bind token is invalid or stale")
        if int(route.get("generation", 0)) != int(pending.get("source_generation", -1)):
            raise BridgeError(ErrorCode.POLICY_VIOLATION, "active route changed during current-chat bind")

        if url is not None:
            canonical = canonical_chat_url(url)
            project_id, conversation_id = conversation_parts(canonical)
            if (
                project_identity(project_id) != project_identity(route.get("project_id"))
                and not bool(pending.get("allow_project_change", False))
            ):
                raise BridgeError(ErrorCode.POLICY_VIOLATION, "current-chat bind candidate belongs to a different project")
        else:
            if pending.get("state") != "candidate" or not pending.get("candidate_url"):
                raise BridgeError(ErrorCode.POLICY_VIOLATION, "current-chat bind candidate is not ready")
            canonical = pending["candidate_url"]
            conversation_id = pending["candidate_conversation_id"]
            project_id = pending.get("candidate_project_id")
            if (
                project_identity(project_id) != project_identity(route.get("project_id"))
                and not bool(pending.get("allow_project_change", False))
            ):
                raise BridgeError(ErrorCode.POLICY_VIOLATION, "current-chat bind candidate belongs to a different project")

        is_already_bound = (
            self.is_bound(route)
            and route.get("conversation_id") == conversation_id
            and project_identity(route.get("project_id")) == project_identity(project_id)
        )

        if is_already_bound:
            changed = False
            route["binding_state"] = "bound"
            data["routes"][route_id] = route
        else:
            changed = True
            generation = int(route.get("generation", 0)) + 1
            route = {
                "title": route.get("title") or route_id,
                "url": canonical,
                "project_id": project_id,
                "conversation_id": conversation_id,
                "channel_id": f"telegram-{route_id}-g{generation}",
                "generation": generation,
                "binding_state": "bound",
                "updated_at": datetime.now(UTC).isoformat(),
            }
            data["routes"][route_id] = route
            data["requested_route"] = route_id
            data["requested_at"] = datetime.now(UTC).isoformat()

        del data["current_binds"][route_id]
        self._save(data)
        return {**self._normalize_route_record(route), "route_id": route_id, "changed": changed, "session_id": pending.get("session_id")}

    def unbind(self, route_id: str, *, expected_generation: int) -> dict:
        route_id = self.validate_route_id(route_id)
        data = self._load()
        route = data["routes"].get(route_id)
        if route is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")
        current_gen = int(route.get("generation", 0))
        if current_gen != int(expected_generation):
            raise BridgeError(ErrorCode.POLICY_VIOLATION, "route generation changed before unbind")

        now = datetime.now(UTC).isoformat()
        unbound_generation = current_gen
        unbound_channel = route.get("channel_id") or f"telegram-{route_id}-g{current_gen}"
        rollovers = data.get("rollovers")
        pending = rollovers.get(route_id) if isinstance(rollovers, dict) else None
        if isinstance(pending, dict):
            try:
                reserved_generation = int(pending.get("target_generation", current_gen + 1))
            except (TypeError, ValueError):
                reserved_generation = current_gen + 1
            unbound_generation = max(current_gen + 1, reserved_generation)
            unbound_channel = f"telegram-{route_id}-g{unbound_generation}"
            data.setdefault("last_rollover", {})[route_id] = {
                **pending,
                "state": "aborted",
                "reason": "route unbound",
                "aborted_at": now,
            }
            del rollovers[route_id]

        unbound_route = {
            "title": route.get("title") or route_id,
            "channel_id": unbound_channel,
            "generation": unbound_generation,
            "binding_state": "unbound",
            "updated_at": now,
        }
        data["routes"][route_id] = unbound_route
        data["requested_at"] = now
        if "current_binds" in data and route_id in data["current_binds"]:
            del data["current_binds"][route_id]
        self._save(data)
        return {**unbound_route, "route_id": route_id}

    def pending_rollover(self, route_id: str) -> dict | None:
        route_id = self.validate_route_id(route_id)
        data = self._load()
        pending = (data.get("rollovers") or {}).get(route_id)
        return {**pending, "route_id": route_id} if isinstance(pending, dict) else None

    def prepare_rollover(self, route_id: str) -> dict:
        route_id = self.validate_route_id(route_id)
        data = self._load()
        route = data["routes"].get(route_id)
        if route is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown route: {route_id}")
        if not self.is_bound(route):
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                f"Route '{route_id}' is unbound; rollover cannot be prepared",
                details={"route_id": route_id, "error_code": "ROUTE_UNBOUND"},
            )
        rollovers = data.setdefault("rollovers", {})
        existing = rollovers.get(route_id)
        if isinstance(existing, dict):
            if int(existing.get("source_generation", -1)) == int(route.get("generation", 0)) and existing.get("state") in {"prepared", "candidate"}:
                return {**existing, "route_id": route_id}
            raise BridgeError(ErrorCode.POLICY_VIOLATION, f"rollover already pending for route: {route_id}", retryable=True)
        source_generation = int(route.get("generation", 0))
        target_generation = source_generation + 1
        pending = {
            "token": f"roll_{token_urlsafe(18)}", "state": "prepared",
            "source_generation": source_generation, "target_generation": target_generation,
            "source_url": route["url"], "source_conversation_id": route["conversation_id"],
            "project_id": route.get("project_id"), "channel_id": f"telegram-{route_id}-g{target_generation}",
            "title": route.get("title") or route_id, "created_at": datetime.now(UTC).isoformat(),
        }
        rollovers[route_id] = pending
        self._save(data)
        return {**pending, "route_id": route_id}

    def record_rollover_candidate(self, route_id: str, token: str, url: str) -> dict:
        route_id = self.validate_route_id(route_id)
        canonical = canonical_chat_url(url)
        project_id, conversation_id = conversation_parts(canonical)
        data = self._load()
        route = data["routes"].get(route_id)
        pending = (data.get("rollovers") or {}).get(route_id)
        if route is None or not isinstance(pending, dict) or pending.get("token") != token:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "rollover token is invalid or stale")
        if int(route.get("generation", 0)) != int(pending.get("source_generation", -1)):
            raise BridgeError(ErrorCode.POLICY_VIOLATION, "active route changed during rollover")
        pending_project = pending.get("project_id")
        same_project = (
            project_id == pending_project
            or (
                isinstance(project_id, str)
                and isinstance(pending_project, str)
                and project_id.startswith(pending_project + "-")
            )
        )
        if not same_project:
            raise BridgeError(ErrorCode.POLICY_VIOLATION, "rollover candidate belongs to a different project")
        if conversation_id == pending.get("source_conversation_id"):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "rollover candidate must be a new conversation")
        pending.update({"state": "candidate", "candidate_url": canonical, "candidate_conversation_id": conversation_id, "candidate_seen_at": datetime.now(UTC).isoformat()})
        self._save(data)
        return {**pending, "route_id": route_id}

    def commit_rollover(self, route_id: str, token: str) -> dict:
        route_id = self.validate_route_id(route_id)
        data = self._load()
        route = data["routes"].get(route_id)
        pending = (data.get("rollovers") or {}).get(route_id)
        if route is None or not isinstance(pending, dict) or pending.get("token") != token:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "rollover token is invalid or stale")
        if pending.get("state") != "candidate" or not pending.get("candidate_url"):
            raise BridgeError(ErrorCode.POLICY_VIOLATION, "rollover candidate is not ready")
        if int(route.get("generation", 0)) != int(pending.get("source_generation", -1)):
            raise BridgeError(ErrorCode.POLICY_VIOLATION, "active route changed during rollover")
        committed = {
            "title": pending.get("title") or route.get("title") or route_id, "url": pending["candidate_url"],
            "project_id": pending.get("project_id"), "conversation_id": pending["candidate_conversation_id"],
            "channel_id": pending["channel_id"], "generation": int(pending["target_generation"]),
            "binding_state": "bound",
            "updated_at": datetime.now(UTC).isoformat(),
        }
        data["routes"][route_id] = committed
        if not data.get("default_route"): data["default_route"] = route_id
        data["requested_route"] = route_id
        data["requested_at"] = datetime.now(UTC).isoformat()
        data.setdefault("last_rollover", {})[route_id] = {
            **pending,
            "state": "committed",
            "bootstrap_sent": False,
            "committed_at": datetime.now(UTC).isoformat(),
        }
        del data["rollovers"][route_id]
        self._save(data)
        return {**self._normalize_route_record(committed), "route_id": route_id, "default": data.get("default_route") == route_id}

    def rollover_for_completion(self, route_id: str, token: str) -> dict:
        route_id = self.validate_route_id(route_id)
        data = self._load()
        last = (data.get("last_rollover") or {}).get(route_id)
        route = data["routes"].get(route_id)
        if (
            not isinstance(last, dict)
            or last.get("token") != token
            or last.get("state") not in {"committed", "complete"}
            or route is None
            or not self.is_bound(route)
            or int(route.get("generation", -1)) != int(last.get("target_generation", -2))
            or route.get("channel_id") != last.get("channel_id")
            or route.get("url") != last.get("candidate_url")
            or route.get("conversation_id") != last.get("candidate_conversation_id")
        ):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "committed rollover token is invalid or stale")
        return {**last, "route_id": route_id}

    def record_rollover_bootstrap_delivery(self, route_id: str, token: str, state: str) -> None:
        last = self.rollover_for_completion(route_id, token)
        data = self._load()
        last["bootstrap_delivery_state"] = state
        data.setdefault("last_rollover", {})[route_id] = last
        self._save(data)

    def complete_rollover(self, route_id: str, token: str) -> dict:
        last = self.rollover_for_completion(route_id, token)
        data = self._load()
        last.update({
            "state": "complete",
            "bootstrap_sent": True,
            "bootstrap_sent_at": datetime.now(UTC).isoformat(),
        })
        data.setdefault("last_rollover", {})[route_id] = last
        self._save(data)
        return {**last, "route_id": route_id}

    def abort_rollover(self, route_id: str, token: str, reason: str | None = None) -> dict:
        route_id = self.validate_route_id(route_id)
        data = self._load()
        pending = (data.get("rollovers") or {}).get(route_id)
        if not isinstance(pending, dict) or pending.get("token") != token:
            return {"route_id": route_id, "aborted": False}
        data.setdefault("last_rollover", {})[route_id] = {**pending, "state": "aborted", "reason": (reason or "unspecified")[:500], "aborted_at": datetime.now(UTC).isoformat()}
        del data["rollovers"][route_id]
        self._save(data)
        return {"route_id": route_id, "aborted": True}

    def takeover(self, route_id: str, url: str, title: str | None = None, *, make_default: bool = True) -> dict:
        route_id = self.validate_route_id(route_id)
        canonical = canonical_chat_url(url)
        project_id, conversation_id = conversation_parts(canonical)
        data = self._load()
        if isinstance((data.get("rollovers") or {}).get(route_id), dict):
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                f"rollover already pending for route: {route_id}",
                retryable=True,
            )
        previous = data["routes"].get(route_id)
        if previous is not None and self.is_bound(previous):
            previous_project = previous.get("project_id")
            same_project = project_identity(project_id) == project_identity(previous_project)
            if not same_project:
                raise BridgeError(
                    ErrorCode.POLICY_VIOLATION,
                    "takeover candidate belongs to a different project",
                )
        previous = previous or {}
        generation = int(previous.get("generation", 0)) + 1
        channel_id = f"telegram-{route_id}-g{generation}"
        route = {
            "title": title or previous.get("title") or route_id,
            "url": canonical,
            "project_id": project_id,
            "conversation_id": conversation_id,
            "channel_id": channel_id,
            "generation": generation,
            "binding_state": "bound",
            "updated_at": datetime.now(UTC).isoformat(),
        }
        data["routes"][route_id] = route
        if make_default or not data.get("default_route"):
            data["default_route"] = route_id
        data["requested_route"] = route_id
        data["requested_at"] = datetime.now(UTC).isoformat()
        self._save(data)
        return {**self._normalize_route_record(route), "route_id": route_id, "default": data["default_route"] == route_id}
