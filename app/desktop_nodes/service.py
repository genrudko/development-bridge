from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from secrets import token_urlsafe
from typing import Any, ClassVar
from urllib.parse import quote

from app.api.capability_exports import CapabilityExportRegistry
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
    retain_result: bool = False


@dataclass(slots=True)
class NodeState:
    node_id: str
    last_seen: float
    last_seen_wall: float
    tools: list[dict[str, Any]] = field(default_factory=list)
    fusion_available: bool = False
    queue: deque[PendingCommand] = field(default_factory=deque)
    commands: dict[str, PendingCommand] = field(default_factory=dict)
    result_delivery_degraded: bool = False
    result_outbox_count: int = 0
    last_result_delivery: float | None = None
    last_claim: float | None = None


@dataclass(slots=True)
class ResultUpload:
    upload_id: str
    node_id: str
    command_id: str
    size_bytes: int
    sha256: str
    path: Path
    offset: int = 0


class DesktopNodeService:
    """Process-local, race-safe command relay for outbound desktop agents."""

    _NODE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    _OPERATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
    _MAX_TOOL_NAME_LENGTH = 200
    _MAX_JOURNAL_METADATA_BYTES = 8192
    _MUTATING_TOOLS: ClassVar[frozenset[str]] = frozenset({"fusion_mcp_execute", "fusion_mcp_update"})
    _TERMINAL_OPERATION_STATES: ClassVar[frozenset[str]] = frozenset({"succeeded", "failed", "late_succeeded", "late_failed"})

    def __init__(self, settings: DesktopNodeSettings, public_base_url: str | None = None, endpoint: str = "/mcp") -> None:
        self.settings = settings
        self._nodes: dict[str, NodeState] = {}
        self._condition = asyncio.Condition()
        self._uploads: dict[str, ResultUpload] = {}
        self._external_results: dict[str, dict[str, Any]] = {}
        self._external_resources: dict[str, dict[str, Any]] = {}
        self._exports = CapabilityExportRegistry[str](settings.result_artifact_ttl_seconds)
        self._public_base_url = public_base_url.rstrip("/") if public_base_url else None
        self._export_path = endpoint.rstrip("/") + "/desktop-results/exports"
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

    @staticmethod
    def _apply_telemetry(node: NodeState, telemetry: dict[str, Any] | None) -> None:
        if telemetry is None:
            return
        degraded = telemetry.get("result_delivery_degraded")
        outbox = telemetry.get("result_outbox_count")
        if not isinstance(degraded, bool) or not isinstance(outbox, int) or isinstance(outbox, bool) or not 0 <= outbox <= 10000:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Desktop result delivery telemetry is invalid")
        node.result_delivery_degraded = degraded
        node.result_outbox_count = outbox

    async def register(self, node_id: str, tools: list[dict[str, Any]], fusion_available: bool, telemetry: dict[str, Any] | None = None) -> dict[str, Any]:
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
            self._apply_telemetry(node, telemetry)
            self._condition.notify_all()
        return self.status(node_id)

    async def heartbeat(self, node_id: str, tools: list[dict[str, Any]] | None = None, fusion_available: bool | None = None, telemetry: dict[str, Any] | None = None) -> dict[str, Any]:
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
            self._apply_telemetry(node, telemetry)
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
            "result_delivery_degraded": node.result_delivery_degraded,
            "result_outbox_count": node.result_outbox_count,
            "last_result_delivery": node.last_result_delivery,
            "last_claim": node.last_claim,
            "last_operation": recent[-1] if recent else None,
            "recent_operations": recent,
            "uncertain_operations": self._journal.uncertain(node_id, 20),
        }

    def tools(self, node_id: str) -> dict[str, Any]:
        node = self._node(node_id)
        return {**self.status(node_id), "tools": node.tools}

    async def submit(self, node_id: str, tool_name: str, arguments: dict[str, Any], journal: dict[str, Any] | None = None) -> dict[str, Any]:
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
                token_urlsafe(18), tool_name, arguments, loop.create_future(),
                operation["operation_id"], operation["mutation"], retain_result=True,
            )
            snapshot = {
                **operation, "command_id": command.command_id, "node_id": node_id,
                "tool_name": tool_name, "arguments_sha256": self._json_hash(arguments),
                "status": "queued", "created_at": time.time(), "claimed_at": None,
                "completed_at": None, "result_sha256": None, "retain_result": True,
            }
            try:
                self._journal.create(snapshot)
            except ValueError as exc:
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion operation id already exists") from exc
            node.queue.append(command)
            node.commands[command.command_id] = command
            self._condition.notify_all()
        return {"operation_id": command.operation_id, "status": "queued"}

    def operation_status(self, node_id: str, operation_id: str) -> dict[str, Any]:
        self._configured()
        self._validate_node_id(node_id)
        operation_id = self._validate_operation_id(operation_id, "Fusion operation id")
        snapshot = self._journal.get(operation_id)
        if snapshot is None or snapshot.get("node_id") != node_id:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion operation is unknown")
        if snapshot.get("status") == "claimed":
            snapshot["status"] = "running"
        return snapshot

    def operation_result(self, node_id: str, operation_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        snapshot = self.operation_status(node_id, operation_id)
        status = snapshot.get("status")
        if status == "orphaned":
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "Fusion operation was never claimed and cannot produce a result",
                details={"operation_id": operation_id, "status": status},
            )
        if status not in self._TERMINAL_OPERATION_STATES:
            raise BridgeError(
                ErrorCode.DESKTOP_NODE_BUSY, "Fusion operation is not complete", retryable=True,
                details={"operation_id": operation_id, "status": status},
            )
        result_id = snapshot.get("result_id")
        if not isinstance(result_id, str):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion operation result is unavailable")
        return self.external_result({"result_id": result_id})

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
                        node.last_claim = time.time()
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
        external = result.get("external_result")
        result_hash = (
            external.get("sha256")
            if isinstance(external, dict)
            and isinstance(external.get("sha256"), str)
            else self._json_hash(result)
        )
        result_failed = bool(result.get("isError", False))
        external_result_id = (
            external.get("result_id")
            if isinstance(external, dict) and isinstance(external.get("result_id"), str)
            else None
        )
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
                    retained_result_id = external_result_id
                    if archived.get("retain_result") and retained_result_id is None:
                        retained_result_id = self._store_result_value(node_id, command_id, result)
                    self._journal.update(
                        archived["operation_id"],
                        status="late_failed" if result_failed else "late_succeeded",
                        completed_at=time.time(),
                        result_sha256=result_hash,
                        result_id=retained_result_id,
                    )
                    self._condition.notify_all()
                    return
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Command is unknown or no longer pending")
            if not command.claimed:
                node.commands[command_id] = command
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Command is unknown or no longer pending")
            retained_result_id = external_result_id
            if command.retain_result and retained_result_id is None:
                retained_result_id = self._store_result_value(node_id, command_id, result)
            self._journal.update(
                command.operation_id,
                status="failed" if result_failed else "succeeded",
                completed_at=time.time(),
                result_sha256=result_hash,
                result_id=retained_result_id,
            )
            if not command.future.done():
                command.future.set_result(result)
            node.last_result_delivery = time.time()
            self._condition.notify_all()

    def _artifact_dir(self) -> Path:
        path = self.settings.result_artifact_directory.expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _store_result_value(self, node_id: str, command_id: str, value: dict[str, Any]) -> str:
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        result_id = token_urlsafe(18)
        created_at = time.time()
        path = self._artifact_dir() / f"{result_id}.json"
        path.write_bytes(raw)
        self._external_results[result_id] = {
            "path": path, "node_id": node_id, "command_id": command_id,
            "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "created_at": created_at, "mime_type": "application/json", "resource_ids": [],
        }
        self._extract_image_resources(result_id, value, created_at)
        return result_id

    def _extract_image_resources(self, result_id: str, value: dict[str, Any], created_at: float) -> None:
        parent = self._external_results[result_id]
        extensions = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}
        for index, content in enumerate(value.get("content", [])):
            if not isinstance(content, dict) or content.get("type") != "image":
                continue
            data = content.get("data")
            mime_type = content.get("mimeType")
            if not isinstance(data, str) or not isinstance(mime_type, str):
                continue
            try:
                raw = base64.b64decode(data, validate=True)
            except (TypeError, ValueError):
                continue
            if not raw:
                continue
            resource_id = token_urlsafe(18)
            extension = extensions.get(mime_type, ".bin")
            path = self._artifact_dir() / f"{result_id}-image-{index}{extension}"
            path.write_bytes(raw)
            self._external_resources[resource_id] = {
                "path": path, "parent_result_id": result_id, "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(), "created_at": created_at,
                "mime_type": mime_type, "file_name": path.name,
            }
            parent["resource_ids"].append(resource_id)

    def _cleanup_external_results(self) -> None:
        cutoff = time.time() - self.settings.result_artifact_ttl_seconds
        for result_id, item in list(self._external_results.items()):
            if item["created_at"] <= cutoff:
                for resource_id in item.get("resource_ids", []):
                    resource = self._external_resources.pop(resource_id, None)
                    if resource is not None:
                        try:
                            resource["path"].unlink(missing_ok=True)
                        except OSError:
                            pass
                try:
                    item["path"].unlink(missing_ok=True)
                except OSError:
                    pass
                self._external_results.pop(result_id, None)

    def begin_result_upload(self, node_id: str, command_id: str, size_bytes: int, sha256: str) -> dict[str, Any]:
        node = self._node(node_id)
        current = node.commands.get(command_id)
        archived = self._journal.by_command(command_id)
        accepted_late = (
            archived is not None
            and archived.get("node_id") == node_id
            and archived.get("status") not in self._TERMINAL_OPERATION_STATES
        )
        if not ((current is not None and current.claimed) or accepted_late):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Command is unknown or no longer pending")
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or not 1 <= size_bytes <= self.settings.max_result_upload_bytes:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "External result size is invalid")
        if not isinstance(sha256, str) or re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "External result SHA-256 is invalid")
        self._cleanup_external_results()
        upload_id = token_urlsafe(18)
        path = self._artifact_dir() / f".{upload_id}.upload"
        path.write_bytes(b"")
        self._uploads[upload_id] = ResultUpload(upload_id, node_id, command_id, size_bytes, sha256, path)
        return {"upload_id": upload_id, "offset": 0}

    def append_result_upload(self, node_id: str, upload_id: str, offset: int, data: str) -> dict[str, Any]:
        upload = self._uploads.get(upload_id)
        if upload is None or upload.node_id != node_id:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "External result upload is unknown")
        if offset != upload.offset:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "External result upload offset is invalid")
        try:
            chunk = base64.b64decode(data, validate=True)
        except (ValueError, TypeError) as exc:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "External result chunk is invalid") from exc
        if not chunk or upload.offset + len(chunk) > upload.size_bytes:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "External result chunk size is invalid")
        with upload.path.open("ab") as target:
            target.write(chunk)
            target.flush()
        upload.offset += len(chunk)
        return {"upload_id": upload_id, "offset": upload.offset}

    def finalize_result_upload(self, node_id: str, upload_id: str) -> dict[str, Any]:
        upload = self._uploads.get(upload_id)
        if upload is None or upload.node_id != node_id:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "External result upload is unknown")
        if upload.offset != upload.size_bytes:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "External result upload is incomplete")
        digest = hashlib.sha256(upload.path.read_bytes()).hexdigest()
        if digest != upload.sha256:
            upload.path.unlink(missing_ok=True)
            self._uploads.pop(upload_id, None)
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "External result SHA-256 mismatch")
        try:
            value = json.loads(upload.path.read_bytes())
        except (OSError, ValueError) as exc:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "External result is not valid JSON") from exc
        if not isinstance(value, dict):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "External result must be an object")
        result_id = token_urlsafe(18)
        final_path = self._artifact_dir() / f"{result_id}.json"
        upload.path.replace(final_path)
        self._uploads.pop(upload_id, None)
        created_at = time.time()
        self._external_results[result_id] = {
            "path": final_path, "node_id": node_id, "command_id": upload.command_id,
            "size_bytes": upload.size_bytes, "sha256": upload.sha256, "created_at": created_at,
            "mime_type": "application/json", "resource_ids": [],
        }
        self._extract_image_resources(result_id, value, created_at)
        return {
            "external_result": {
                "result_id": result_id,
                "size_bytes": upload.size_bytes,
                "sha256": upload.sha256,
            },
            "isError": bool(value.get("isError", False)),
        }

    def _recover_external_result(self, result_id: Any) -> dict[str, Any] | None:
        if not isinstance(result_id, str) or re.fullmatch(r"[A-Za-z0-9_-]{16,64}", result_id) is None:
            return None
        path = self._artifact_dir() / f"{result_id}.json"
        try:
            stat = path.stat()
            if stat.st_mtime <= time.time() - self.settings.result_artifact_ttl_seconds:
                path.unlink(missing_ok=True)
                for image_path in self._artifact_dir().glob(f"{result_id}-image-*"):
                    image_path.unlink(missing_ok=True)
                return None
            raw = path.read_bytes()
            value = json.loads(raw)
        except (OSError, ValueError):
            return None
        if not isinstance(value, dict):
            return None
        item = {
            "path": path, "node_id": None, "command_id": None,
            "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "created_at": stat.st_mtime, "mime_type": "application/json", "resource_ids": [],
        }
        self._external_results[result_id] = item
        self._extract_image_resources(result_id, value, stat.st_mtime)
        return item

    def external_result(self, reference: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        self._cleanup_external_results()
        result_id = reference.get("result_id") if isinstance(reference, dict) else None
        item = self._external_results.get(result_id) or self._recover_external_result(result_id)
        if item is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "External desktop result is unavailable")
        value = json.loads(item["path"].read_bytes())
        metadata = {key: item[key] for key in ("size_bytes", "sha256")}
        metadata["file_name"] = f"fusion-result-{result_id}.json"
        metadata["resources"] = []
        if self._public_base_url is not None:
            token, grant = self._exports.issue(result_id)
            metadata["export_url"] = f"{self._public_base_url}{self._export_path}/{quote(token, safe='')}"
            metadata["expires_at"] = grant.expires_at.isoformat()
            for resource_id in item.get("resource_ids", []):
                resource = self._external_resources.get(resource_id)
                if resource is None:
                    continue
                resource_token, resource_grant = self._exports.issue(f"resource:{resource_id}")
                metadata["resources"].append({
                    "uri": f"{self._public_base_url}{self._export_path}/{quote(resource_token, safe='')}",
                    "file_name": resource["file_name"], "mime_type": resource["mime_type"],
                    "size_bytes": resource["size_bytes"], "sha256": resource["sha256"],
                    "expires_at": resource_grant.expires_at.isoformat(),
                })
        return value, metadata

    def resolve_external_export(self, token: str) -> tuple[Path, dict[str, Any]] | None:
        grant = self._exports.lookup(token)
        if grant is None:
            return None
        self._cleanup_external_results()
        if grant.subject.startswith("resource:"):
            item = self._external_resources.get(grant.subject.removeprefix("resource:"))
        else:
            item = self._external_results.get(grant.subject)
        return (item["path"], item) if item is not None else None
