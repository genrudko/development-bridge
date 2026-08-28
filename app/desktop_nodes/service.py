from __future__ import annotations

import asyncio
import json
import re
import time
from collections import deque
from dataclasses import dataclass, field
from secrets import token_urlsafe
from typing import Any

from app.api.errors import BridgeError, ErrorCode
from app.settings import DesktopNodeSettings


@dataclass(slots=True)
class PendingCommand:
    command_id: str
    tool_name: str
    arguments: dict[str, Any]
    future: asyncio.Future[dict[str, Any]]
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
    _MAX_TOOL_NAME_LENGTH = 200

    def __init__(self, settings: DesktopNodeSettings) -> None:
        self.settings = settings
        self._nodes: dict[str, NodeState] = {}
        self._condition = asyncio.Condition()

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

    @classmethod
    def _validate_node_id(cls, node_id: str) -> None:
        if not isinstance(node_id, str) or cls._NODE_ID.fullmatch(node_id) is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Desktop node id is invalid")

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
        return {"node_id": node.node_id, "last_seen": node.last_seen_wall, "age_seconds": max(0.0, self._now() - node.last_seen), "online": self._online(node), "fusion_available": node.fusion_available, "tool_count": len(node.tools), "pending_commands": len(node.commands), "claimed_commands": sum(command.claimed for command in node.commands.values())}

    def tools(self, node_id: str) -> dict[str, Any]:
        node = self._node(node_id)
        return {**self.status(node_id), "tools": node.tools}

    async def call(self, node_id: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self._configured()
        if self._json_size(arguments) > self.settings.max_arguments_bytes:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion tool arguments are too large")
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
            command = PendingCommand(token_urlsafe(18), tool_name, arguments, loop.create_future())
            node.queue.append(command)
            node.commands[command.command_id] = command
            self._condition.notify_all()
        try:
            return await asyncio.wait_for(asyncio.shield(command.future), self.settings.call_timeout_seconds)
        except asyncio.CancelledError:
            await self._remove_command(node, command)
            raise
        except TimeoutError as exc:
            await self._remove_command(node, command)
            raise BridgeError(ErrorCode.DESKTOP_NODE_TIMEOUT, "Fusion command timed out", retryable=True) from exc

    async def _remove_command(self, node: NodeState, command: PendingCommand) -> None:
        async with self._condition:
            node.commands.pop(command.command_id, None)
            try:
                node.queue.remove(command)
            except ValueError:
                pass
            if not command.future.done():
                command.future.cancel()

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
                        return {"command_id": command.command_id, "tool_name": command.tool_name, "arguments": command.arguments}
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
        async with self._condition:
            node = self._node(node_id)
            self._touch(node)
            command = node.commands.pop(command_id, None)
            if command is None or not command.claimed:
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Command is unknown or no longer pending")
            if not command.future.done():
                command.future.set_result(result)
            self._condition.notify_all()
