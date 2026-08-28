from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections import deque
from dataclasses import dataclass, field
from secrets import token_urlsafe
from typing import Any

from app.api.errors import BridgeError, ErrorCode
from app.desktop_nodes.journal import OperationJournal
from app.settings import DesktopNodeSettings


@dataclass(slots=True)
class PendingCommand:
    command_id: str
    tool_name: str
    arguments: dict[str, Any]
    future: asyncio.Future[dict[str, Any]]
    operation_id: str
    mutation: bool
    claimed: bool = False


@dataclass(slots=True)
class NodeState:
    node_id: str
    last_seen: float
    last_seen_wall: float
    tools: list[dict[str, Any]] = field(default_factory=list)
    fusion_available: bool = False
    queue: deque[PendingCommand] = field(default_factory=deque)
    commands: dict[str, PendingCommand] = field(default_factory=dict)


class DesktopNodeService:
    """Process-local, race-safe command relay for outbound desktop agents."""

    _NODE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    _OPERATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
    _MAX_TOOL_NAME_LENGTH = 200
    _MAX_JOURNAL_METADATA_BYTES = 8192
    _MUTATING_TOOLS = {"fusion_mcp_execute", "fusion_mcp_update"}
    _TERMINAL_OPERATION_STATES = {"succeeded", "failed", "late_succeeded", "late_failed"}

    def __init__(self, settings: DesktopNodeSettings) -> None:
        self.settings = settings
        self._nodes: dict[str, NodeState] = {}
        self._condition = asyncio.Condition()
        self._journal = OperationJournal(
            settings.journal_path,
            settings.journal_history_limit,
            settings.journal_max_bytes,
        )
        self._recover_incomplete_operations()

    def _recover_incomplete_operations(self) -> None:
        for operation in self._journal.incomplete():
            if operation.get("status") == "queued":
                status = "orphaned"
                reason = "bridge_restarted_before_claim"
            else:
                status = "uncertain" if operation.get("mutation") else "interrupted"
                reason = "bridge_restarted_after_claim"
            self._journal.update(
                operation["operation_id"],
                status=status,
                completed_at=time.time(),
                recovery_reason=reason,
            )

    def _now(self) -> float:
        return time.monotonic()

    def _configured(self) -> None:
        if self.settings.token is None:
            raise BridgeError(ErrorCode.DESKTOP_NODE_NOT_CONFIGURED, "Desktop node relay is not configured")

    def _node(self, node_id: str) -> NodeState:
        self._validate_node_id(node_id)
        node = self._nodes.get(node_id)
        if node is None:
            raise BridgeError(ErrorCode.DESKTOP_NODE_NOT_FOUND, "Desktop node is not registered", details={"node_id": node_id})
        return node

    def _online(self, node: NodeState) -> bool:
        return self._now() - node.last_seen <= self.settings.offline_after_seconds

    @staticmethod
    def _json_size(value: Any) -> int:
        try:
            return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode())
        except (TypeError, ValueError) as exc:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Value must be JSON-safe") from exc

    @staticmethod
    def _json_hash(value: Any) -> str:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def _validate_node_id(cls, node_id: str) -> None:
        if not isinstance(node_id, str) or cls._NODE_ID.fullmatch(node_id) is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Desktop node id is invalid")

    @classmethod
    def _validate_operation_id(cls, operation_id: Any, label: str) -> str:
        if not isinstance(operation_id, str) or cls._OPERATION_ID.fullmatch(operation_id) is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"{label} is invalid")
        return operation_id

    def _validate_tools(self, tools: Any) -> None:
        if not isinstance(tools, list):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Tool metadata must be a list")
        for tool in tools:
            if not isinstance(tool, dict):
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Each tool must be a JSON-safe object")
            name = tool.get("name")
            if not isinstance(name, str) or not name.strip() or len(name) > self._MAX_TOOL_NAME_LENGTH:
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Tool name must be a non-empty bounded string")
        if self._json_size(tools) > self.settings.max_request_bytes:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Tool metadata is too large")

    def _operation_metadata(self, tool_name: str, metadata: Any) -> dict[str, Any]:
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion operation journal metadata must be an object")
        if self._json_size(metadata) > self._MAX_JOURNAL_METADATA_BYTES:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion operation journal metadata is too large")
        allowed = {"operation_id", "summary", "mutation", "parent_operation_id", "checkpoint"}
        if set(metadata) - allowed:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion operation journal metadata contains unknown fields")
        operation_id = metadata.get("operation_id") or f"op_{token_urlsafe(12)}"
        operation_id = self._validate_operation_id(operation_id, "Fusion operation id")
        summary = metadata.get("summary")
        if summary is not None and (not isinstance(summary, str) or not summary.strip() or len(summary) > 300):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion operation summary must be a non-empty bounded string")
        mutation = metadata.get("mutation", tool_name in self._MUTATING_TOOLS)
        if not isinstance(mutation, bool):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion operation mutation flag must be boolean")
        parent = metadata.get("parent_operation_id")
        if parent is not None:
            parent = self._validate_operation_id(parent, "Parent Fusion operation id")
        checkpoint = metadata.get("checkpoint")
        if checkpoint is not None and not isinstance(checkpoint, dict):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion checkpoint metadata must be an object")
        return {
            "operation_id": operation_id,
            "summary": summary,
            "mutation": mutation,
            "parent_operation_id": parent,
            "checkpoint": checkpoint,
        }

    @staticmethod
    def _touch(node: NodeState) -> None:
        node.last_seen = time.monotonic()
        node.last_seen_wall = time.time()

    async def register(self, node_id: str, tools: list[dict[str, Any]], fusion_available: bool) -> dict[str, Any]:
        self._configured()
        self._validate_node_id(node_id)
        self._validate_tools(tools)
        async with self._condition:
            node = self._nodes.get(node_id)
            if node is None:
                node = NodeState(node_id=node_id, last_seen=self._now(), last_seen_wall=time.time())
                self._nodes[node_id] = node
            self._touch(node)
            node.tools = tools
            node.fusion_available = fusion_available
            self._condition.notify_all()
        return self.status(node_id)

    async def heartbeat(self, node_id: str, tools: list[dict[str, Any]] | None = None, fusion_available: bool | None = None) -> dict[str, Any]:
        self._configured()
        self._validate_node_id(node_id)
        if tools is not None:
            self._validate_tools(tools)
        async with self._condition:
            node = self._node(node_id)
            self._touch(node)
            if tools is not None:
                node.tools = tools
            if fusion_available is not None:
                node.fusion_available = fusion_available
            self._condition.notify_all()
        return self.status(node_id)

    def status(self, node_id: str) -> dict[str, Any]:
        self._configured()
        node = self._node(node_id)
        recent = self._journal.recent(node_id, 10)
        return {
            "node_id": node.node_id,
            "last_seen": node.last_seen_wall,
            "age_seconds": max(0.0, self._now() - node.last_seen),
            "online": self._online(node),
            "fusion_available": node.fusion_available,
            "tool_count": len(node.tools),
            "pending_commands": len(node.commands),
            "claimed_commands": sum(command.claimed for command in node.commands.values()),
            "last_operation": recent[-1] if recent else None,
            "recent_operations": recent,
            "uncertain_operations": self._journal.uncertain(node_id, 20),
        }

    def tools(self, node_id: str) -> dict[str, Any]:
        node = self._node(node_id)
        return {**self.status(node_id), "tools": node.tools}

    async def call(self, node_id: str, tool_name: str, arguments: dict[str, Any], journal: dict[str, Any] | None = None) -> dict[str, Any]:
        self._configured()
        if self._json_size(arguments) > self.settings.max_arguments_bytes:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion tool arguments are too large")
        operation = self._operation_metadata(tool_name, journal)
        loop = asyncio.get_running_loop()
        async with self._condition:
            node = self._node(node_id)
            if not self._online(node) or not node.fusion_available:
                raise BridgeError(ErrorCode.DESKTOP_NODE_OFFLINE, "Desktop node or Fusion is offline", retryable=True)
            discovered = {item.get("name") for item in node.tools}
            if tool_name not in discovered:
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion tool is not discovered", details={"tool_name": tool_name})
            if len(node.commands) >= self.settings.max_pending_commands:
                raise BridgeError(ErrorCode.DESKTOP_NODE_BUSY, "Desktop node command queue is full", retryable=True)
            command = PendingCommand(
                token_urlsafe(18),
                tool_name,
                arguments,
                loop.create_future(),
                operation["operation_id"],
                operation["mutation"],
            )
            snapshot = {
                **operation,
                "command_id": command.command_id,
                "node_id": node_id,
                "tool_name": tool_name,
                "arguments_sha256": self._json_hash(arguments),
                "status": "queued",
                "created_at": time.time(),
                "claimed_at": None,
                "completed_at": None,
                "result_sha256": None,
            }
            try:
                self._journal.create(snapshot)
            except ValueError as exc:
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion operation id already exists") from exc
            node.queue.append(command)
            node.commands[command.command_id] = command
            self._condition.notify_all()
        try:
            return await asyncio.wait_for(asyncio.shield(command.future), self.settings.call_timeout_seconds)
        except asyncio.CancelledError:
            status = "uncertain" if command.claimed and command.mutation else "cancelled"
            await self._remove_command(node, command, status)
            raise
        except TimeoutError as exc:
            status = "uncertain" if command.claimed and command.mutation else "timed_out"
            await self._remove_command(node, command, status)
            raise BridgeError(
                ErrorCode.DESKTOP_NODE_TIMEOUT,
                "Fusion command timed out",
                retryable=not command.mutation,
                details={"operation_id": command.operation_id, "status": status},
            ) from exc

    async def _remove_command(self, node: NodeState, command: PendingCommand, status: str) -> None:
        async with self._condition:
            node.commands.pop(command.command_id, None)
            try:
                node.queue.remove(command)
            except ValueError:
                pass
            self._journal.update(command.operation_id, status=status, completed_at=time.time())
            if not command.future.done():
                command.future.cancel()
            self._condition.notify_all()

    async def claim(self, node_id: str, wait_seconds: float) -> dict[str, Any] | None:
        self._configured()
        deadline = self._now() + min(max(wait_seconds, 0), self.settings.claim_timeout_seconds)
        async with self._condition:
            node = self._node(node_id)
            self._touch(node)
            while True:
                while node.queue:
                    command = node.queue.popleft()
                    if command.command_id in node.commands:
                        command.claimed = True
                        self._journal.update(command.operation_id, status="claimed", claimed_at=time.time())
                        return {
                            "command_id": command.command_id,
                            "tool_name": command.tool_name,
                            "arguments": command.arguments,
                            "operation_id": command.operation_id,
                        }
                remaining = deadline - self._now()
                if remaining <= 0:
                    return None
                try:
                    await asyncio.wait_for(self._condition.wait(), remaining)
                except TimeoutError:
                    return None

    async def submit_result(self, node_id: str, command_id: str, result: dict[str, Any]) -> None:
        self._configured()
        self._validate_node_id(node_id)
        if not isinstance(result, dict):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion command result must be a JSON-safe object")
        if self._json_size(result) > self.settings.max_result_bytes:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion command result is too large")
        result_hash = self._json_hash(result)
        result_failed = bool(result.get("isError", False))
        async with self._condition:
            node = self._node(node_id)
            self._touch(node)
            command = node.commands.pop(command_id, None)
            if command is None:
                archived = self._journal.by_command(command_id)
                if (
                    archived is not None
                    and archived.get("node_id") == node_id
                    and archived.get("status") not in self._TERMINAL_OPERATION_STATES
                ):
                    self._journal.update(
                        archived["operation_id"],
                        status="late_failed" if result_failed else "late_succeeded",
                        completed_at=time.time(),
                        result_sha256=result_hash,
                    )
                    self._condition.notify_all()
                    return
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Command is unknown or no longer pending")
            if not command.claimed:
                node.commands[command_id] = command
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Command is unknown or no longer pending")
            self._journal.update(
                command.operation_id,
                status="failed" if result_failed else "succeeded",
                completed_at=time.time(),
                result_sha256=result_hash,
            )
            if not command.future.done():
                command.future.set_result(result)
            self._condition.notify_all()
