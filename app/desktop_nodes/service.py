from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from secrets import compare_digest, token_urlsafe
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
    session_generation: int = 1


@dataclass(slots=True)
class ResultUpload:
    upload_id: str
    node_id: str
    command_id: str
    size_bytes: int
    sha256: str
    path: Path
    offset: int = 0


_BASE64_MAGIC_PREFIXES: dict[str, str] = {
    "iVBORw0KGgo": "image/png",
    "/9j/": "image/jpeg",
    "R0lGOD": "image/gif",
    "UklGR": "image/webp",
    "Qk": "image/bmp",
    "JVBERi0": "application/pdf",
    "UEsDB": "application/zip",
}

_BINARY_MIME_PREFIXES: tuple[str, ...] = (
    "image/",
    "audio/",
    "video/",
    "model/",
)

_BINARY_MIME_EXACT: frozenset[str] = frozenset({
    "application/octet-stream",
    "application/pdf",
    "application/zip",
    "application/x-step",
    "application/sla",
    "application/vnd.ms-pki.stl",
    "application/step",
    "application/3mf",
})

_EXPLICIT_BINARY_KEYS: frozenset[str] = frozenset({
    "base64Data",
    "base64_data",
    "b64_data",
    "image_data",
    "binary_data",
    "raw_bytes",
    "thumbnail_b64",
    "screenshot_b64",
    "png_base64",
    "jpg_base64",
    "jpeg_base64",
    "stl_base64",
    "step_base64",
    "mesh_data",
    "blob",
    "bytes",
    "base64",
})

_EXPLICIT_BINARY_SUFFIXES: tuple[str, ...] = (
    "_b64",
    "_base64",
    "Base64",
    "_binary",
    "_bytes",
    "_blob",
)

_MIME_EXTENSIONS: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "application/pdf": ".pdf",
    "application/zip": ".zip",
    "model/stl": ".stl",
    "model/3mf": ".3mf",
    "model/step": ".step",
    "application/sla": ".stl",
    "application/vnd.ms-pki.stl": ".stl",
    "application/step": ".step",
    "application/x-step": ".step",
    "application/3mf": ".3mf",
    "application/octet-stream": ".bin",
}

_BASE64_CHARS_RE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")

# Persisted resource sidecar contract. Only exactly supported documents are
# honored on recovery; everything else fails closed (no binary resources).
_SIDECAR_VERSION = 2
_SIDECAR_LEGACY_VERSION = 1
_SIDECAR_MAX_BYTES = 1_048_576
_SIDECAR_MAX_RESOURCES = 1024
_SIDECAR_CREATED_AT_SKEW_SECONDS = 300.0

_SIDECAR_RESOURCE_ID_RE = re.compile(r"[A-Za-z0-9_-]{16,128}")
_SIDECAR_CAPABILITY_RE = re.compile(r"[A-Za-z0-9_-]{32,128}")
_SIDECAR_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_SIDECAR_MIME_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,126}/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,126}"
)
_SIDECAR_FILE_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._ ()+-]{0,127}")

_V2_SIDECAR_KEYS = frozenset({
    "resource_id", "path_name", "mime_type", "file_name",
    "size_bytes", "sha256", "created_at", "stable_capability",
})
_V1_SIDECAR_KEYS = _V2_SIDECAR_KEYS - {"stable_capability"}


@dataclass(slots=True)
class ExtractedBinaryResource:
    raw_bytes: bytes
    mime_type: str
    suggested_name: str | None = None


def _is_mime_binary(mime: Any) -> bool:
    if not isinstance(mime, str):
        return False
    mime_lower = mime.lower().strip()
    return mime_lower.startswith(_BINARY_MIME_PREFIXES) or mime_lower in _BINARY_MIME_EXACT


def parse_resource_sidecar(
    document: Any,
    *,
    result_id: str,
    max_resource_bytes: int,
    now: float,
) -> list[dict[str, Any]] | None:
    """Strictly validate a persisted resource sidecar document.

    Returns validated descriptors for an exactly supported v2 document, or for
    the legacy v1 shape (which is migrated explicitly by assigning a fresh
    stable capability). Everything else - a non-object document, an unknown or
    missing version, a wrong resources shape, or a descriptor with an invalid,
    unbounded, or unowned field - returns None so recovery can fail closed
    instead of trusting metadata an attacker may have crafted.

    `path_name` is pinned to the extracted resource file this result owns,
    `{result_id}-res-{index}{extension}`, so absolute paths and traversal are
    structurally impossible and the extension must agree with `mime_type`.
    """
    if not isinstance(document, dict):
        return None
    version = document.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        return None
    if version not in (_SIDECAR_VERSION, _SIDECAR_LEGACY_VERSION):
        return None
    resources = document.get("resources")
    if not isinstance(resources, list) or len(resources) > _SIDECAR_MAX_RESOURCES:
        return None
    expected_keys = _V2_SIDECAR_KEYS if version == _SIDECAR_VERSION else _V1_SIDECAR_KEYS
    descriptors: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(resources):
        if not isinstance(entry, dict) or set(entry) != expected_keys:
            return None
        resource_id = entry["resource_id"]
        if (
            not isinstance(resource_id, str)
            or resource_id in seen_ids
            or _SIDECAR_RESOURCE_ID_RE.fullmatch(resource_id) is None
        ):
            return None
        seen_ids.add(resource_id)
        mime_type = entry["mime_type"]
        if (
            not isinstance(mime_type, str)
            or _SIDECAR_MIME_RE.fullmatch(mime_type) is None
            or not _is_mime_binary(mime_type)
        ):
            return None
        extension = _MIME_EXTENSIONS.get(mime_type, ".bin")
        path_name = entry["path_name"]
        if path_name != f"{result_id}-res-{index}{extension}":
            return None
        file_name = entry["file_name"]
        if (
            not isinstance(file_name, str)
            or _SIDECAR_FILE_NAME_RE.fullmatch(file_name) is None
            or not file_name.endswith(extension)
        ):
            return None
        size_bytes = entry["size_bytes"]
        if (
            isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or not 1 <= size_bytes <= max_resource_bytes
        ):
            return None
        sha256 = entry["sha256"]
        if not isinstance(sha256, str) or _SIDECAR_SHA256_RE.fullmatch(sha256) is None:
            return None
        created_at = entry["created_at"]
        if (
            isinstance(created_at, bool)
            or not isinstance(created_at, (int, float))
            or not math.isfinite(created_at)
            or not 0.0 < float(created_at) <= now + _SIDECAR_CREATED_AT_SKEW_SECONDS
        ):
            return None
        capability = entry["stable_capability"] if version == _SIDECAR_VERSION else None
        if capability is not None and (
            not isinstance(capability, str)
            or _SIDECAR_CAPABILITY_RE.fullmatch(capability) is None
        ):
            return None
        descriptors.append({
            "resource_id": resource_id,
            "path_name": path_name,
            "mime_type": mime_type,
            "file_name": file_name,
            "size_bytes": size_bytes,
            "sha256": sha256,
            "created_at": float(created_at),
            "stable_capability": capability,
        })
    return descriptors


def _detect_verified_binary_magic(raw: bytes, preferred_mime: str | None = None) -> str | None:
    if len(raw) >= 8 and raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(raw) >= 3 and raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(raw) >= 6 and raw.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(raw) >= 12 and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "image/webp"
    if len(raw) >= 14 and raw.startswith(b"BM"):
        return "image/bmp"
    if len(raw) >= 5 and raw.startswith(b"%PDF-"):
        return "application/pdf"
    if len(raw) >= 4 and raw.startswith(b"PK\x03\x04"):
        return preferred_mime if preferred_mime in ("model/3mf", "application/3mf") else "application/zip"
    if len(raw) >= 14 and raw.startswith(b"ISO-10303-21;"):
        return preferred_mime if preferred_mime else "model/step"
    if len(raw) >= 84:
        triangle_count = int.from_bytes(raw[80:84], "little")
        if triangle_count > 0 and len(raw) == 84 + triangle_count * 50:
            return preferred_mime if preferred_mime else "model/stl"
    return None


def _detect_mime_from_bytes(raw: bytes, preferred_mime: str | None = None) -> str:
    if preferred_mime and _is_mime_binary(preferred_mime):
        return preferred_mime
    magic_mime = _detect_verified_binary_magic(raw, preferred_mime)
    if magic_mime:
        return magic_mime
    if raw.startswith((b"solid ", b"ISO-10303-21;")):
        return preferred_mime if preferred_mime else "model/stl"
    return preferred_mime or "application/octet-stream"


def extract_binary_resources(value: Any) -> list[ExtractedBinaryResource]:
    results: list[ExtractedBinaryResource] = []
    seen_raw: set[bytes] = set()

    def _add_resource(raw: bytes, mime: str, name: str | None = None) -> None:
        if not raw or raw in seen_raw:
            return
        seen_raw.add(raw)
        results.append(ExtractedBinaryResource(raw, mime, name))

    def _try_decode_base64_string(s: str, candidate_name: str | None = None, preferred_mime: str | None = None) -> bool:
        str_val = s.strip()
        if not str_val:
            return False

        if str_val.startswith("data:") and ";base64," in str_val:
            header, b64_payload = str_val.split(";base64,", 1)
            data_mime = header.removeprefix("data:").strip()
            try:
                raw = base64.b64decode(b64_payload, validate=True)
                if raw:
                    verified_magic = _detect_verified_binary_magic(raw, data_mime)
                    if _is_mime_binary(data_mime) or verified_magic:
                        mime = (
                            data_mime
                            if _is_mime_binary(data_mime)
                            else (verified_magic or preferred_mime or "application/octet-stream")
                        )
                        _add_resource(raw, mime, candidate_name)
                        return True
            except (ValueError, TypeError):
                return False

        is_explicit_binary = bool(
            (
                candidate_name
                and (
                    candidate_name in _EXPLICIT_BINARY_KEYS
                    or any(candidate_name.endswith(suffix) for suffix in _EXPLICIT_BINARY_SUFFIXES)
                )
            )
            or (preferred_mime and _is_mime_binary(preferred_mime))
        )

        if is_explicit_binary:
            try:
                raw = base64.b64decode(str_val, validate=True)
                if raw:
                    mime = _detect_mime_from_bytes(raw, preferred_mime)
                    _add_resource(raw, mime, candidate_name)
                    return True
            except (ValueError, TypeError):
                pass

        if len(str_val) >= 4 and len(str_val) % 4 == 0 and _BASE64_CHARS_RE.fullmatch(str_val):
            try:
                raw = base64.b64decode(str_val, validate=True)
                if raw:
                    verified_magic = _detect_verified_binary_magic(raw, preferred_mime)
                    if verified_magic:
                        _add_resource(raw, verified_magic, candidate_name)
                        return True
            except (ValueError, TypeError):
                pass

        return False

    def _traverse(node: Any, parent_key: str | None = None) -> None:
        if isinstance(node, (bytes, bytearray, memoryview)):
            raw = bytes(node)
            _add_resource(raw, _detect_mime_from_bytes(raw), parent_key)
            return

        if isinstance(node, str):
            _try_decode_base64_string(node, candidate_name=parent_key)
            return

        if isinstance(node, dict):
            node_type = str(node.get("type", "")).lower()
            node_mime = node.get("mimeType") or node.get("mime_type") or node.get("contentType") or node.get("content_type")
            node_encoding = str(node.get("encoding") or node.get("transfer_encoding", "")).lower()
            node_name = node.get("file_name") or node.get("name") or parent_key

            is_binary_container = (
                node_type in ("image", "binary", "blob")
                or _is_mime_binary(node_mime)
                or node_encoding in ("base64", "binary", "hex")
            )

            if is_binary_container:
                for data_key in ("data", "content", "bytes", "payload", "base64Data", "base64_data", "raw_bytes"):
                    if data_key in node:
                        val = node[data_key]
                        if isinstance(val, (bytes, bytearray, memoryview)):
                            raw = bytes(val)
                            _add_resource(raw, _detect_mime_from_bytes(raw, node_mime), node_name)
                        elif isinstance(val, str):
                            _try_decode_base64_string(val, candidate_name=node_name or data_key, preferred_mime=node_mime)

            for k, v in node.items():
                if isinstance(k, str) and (
                    k in _EXPLICIT_BINARY_KEYS or any(k.endswith(suffix) for suffix in _EXPLICIT_BINARY_SUFFIXES)
                ):
                    if isinstance(v, (bytes, bytearray, memoryview)):
                        raw = bytes(v)
                        _add_resource(raw, _detect_mime_from_bytes(raw, node_mime), k)
                    elif isinstance(v, str):
                        _try_decode_base64_string(v, candidate_name=k, preferred_mime=node_mime)
                else:
                    _traverse(v, parent_key=k)
            return

        if isinstance(node, (list, tuple, set, frozenset)):
            for item in node:
                _traverse(item, parent_key=parent_key)
            return

    _traverse(value)
    return results


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(obj)).decode("ascii")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _sanitize_binary_payload(value: Any) -> Any:
    """Deep copy of a payload with base64/binary data fields removed.

    Preserves semantic structure and only removes proven binary fields, matching
    the extraction detection so exported/model-visible JSON never duplicates
    screenshot base64/binary after image resources have been extracted.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return None
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_sanitize_binary_payload(v) for v in value]
        if isinstance(value, tuple):
            return tuple(items)
        if isinstance(value, set):
            return set(items)
        if isinstance(value, frozenset):
            return frozenset(items)
        return items
    if isinstance(value, dict):
        node_type = str(value.get("type", "")).lower()
        node_mime = (
            value.get("mimeType")
            or value.get("mime_type")
            or value.get("contentType")
            or value.get("content_type")
        )
        node_encoding = str(
            value.get("encoding") or value.get("transfer_encoding", "")
        ).lower()
        is_binary_container = (
            node_type in ("image", "binary", "blob")
            or _is_mime_binary(node_mime)
            or node_encoding in ("base64", "binary", "hex")
        )
        out: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and (
                k in _EXPLICIT_BINARY_KEYS
                or any(k.endswith(suffix) for suffix in _EXPLICIT_BINARY_SUFFIXES)
            ):
                continue
            if is_binary_container and k in (
                "data",
                "content",
                "bytes",
                "payload",
                "base64Data",
                "base64_data",
                "raw_bytes",
            ):
                continue
            out[k] = _sanitize_binary_payload(v)
        return out
    return value


def has_binary_data(value: Any) -> bool:
    return bool(extract_binary_resources(value))


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
                node = NodeState(node_id=node_id, last_seen=self._now(), last_seen_wall=time.time(), session_generation=1)
                self._nodes[node_id] = node
            else:
                node.session_generation += 1
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
            generation_bump = False
            if tools is not None:
                if tools != node.tools:
                    generation_bump = True
                node.tools = tools
            if fusion_available is not None:
                if fusion_available != node.fusion_available:
                    generation_bump = True
                node.fusion_available = fusion_available
            if generation_bump:
                node.session_generation += 1
            self._apply_telemetry(node, telemetry)
            self._condition.notify_all()
        return self.status(node_id)

    def get_session_generation(self, node_id: str) -> int:
        self._configured()
        node = self._node(node_id)
        return node.session_generation

    def status(self, node_id: str) -> dict[str, Any]:
        self._configured()
        node = self._node(node_id)
        recent = self._journal.recent(node_id, 10)
        return {
            "node_id": node.node_id,
            "session_generation": node.session_generation,
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

    def finalize_operation_result(
        self,
        node_id: str,
        operation_id: str,
        finalized: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist one public domain-finalized result for a terminal operation.

        The retained workstation artifact is raw adapter evidence until the domain
        service validates and sanitizes it.  Finalization is durable and idempotent:
        a public inline result replaces that raw artifact in place, while an already
        externalized public result becomes the operation's retained result.
        """
        snapshot = self.operation_status(node_id, operation_id)
        status = snapshot.get("status")
        if status not in self._TERMINAL_OPERATION_STATES:
            raise BridgeError(
                ErrorCode.DESKTOP_NODE_BUSY,
                "Fusion operation is not complete",
                retryable=True,
                details={"operation_id": operation_id, "status": status},
            )
        if snapshot.get("domain_finalization") == "finalized":
            result_id = snapshot.get("result_id")
            if not isinstance(result_id, str):
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion operation result is unavailable")
            item = self._external_results.get(result_id) or self._recover_external_result(result_id)
            if item is None:
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "External desktop result is unavailable")
            return {
                "result_id": result_id,
                "size_bytes": item["size_bytes"],
                "sha256": item["sha256"],
            }
        if not isinstance(finalized, dict):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Finalized Fusion result must be an object")

        external = finalized.get("external_result")
        if isinstance(external, dict):
            result_id = external.get("result_id")
            if not isinstance(result_id, str) or not result_id:
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "External result reference is invalid")
            # Validate/recover the service-owned finalized artifact before making
            # the operation journal point at it.
            self.external_result(external)
            item = self._external_results.get(result_id) or self._recover_external_result(result_id)
        else:
            result_id = snapshot.get("result_id")
            if not isinstance(result_id, str):
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion operation result is unavailable")
            self.overwrite_external_result({"result_id": result_id}, finalized)
            item = self._external_results.get(result_id) or self._recover_external_result(result_id)

        if item is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "External desktop result is unavailable")
        updated = self._journal.update(
            operation_id,
            result_id=result_id,
            result_sha256=item["sha256"],
            domain_finalization="finalized",
        )
        if updated is None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion operation is unknown")
        return {
            "result_id": result_id,
            "size_bytes": item["size_bytes"],
            "sha256": item["sha256"],
        }

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
        has_is_error = "isError" in result and result.get("isError") is not False

        def _explicit_operation_uncertain(payload: Any) -> bool:
            if not isinstance(payload, dict):
                return False
            error = payload.get("error")
            return (
                isinstance(error, dict)
                and error.get("code") == ErrorCode.OPERATION_UNCERTAIN.value
            )

        result_uncertain = _explicit_operation_uncertain(result)
        result_failed = bool(
            has_is_error
            or result.get("status") in ("failed", "error")
            or "error" in result
        )
        if isinstance(result.get("content"), list):
            for block in result["content"]:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, dict):
                            result_uncertain = result_uncertain or _explicit_operation_uncertain(parsed)
                            if (
                                ("isError" in parsed and parsed.get("isError") is not False)
                                or parsed.get("status") in ("failed", "error")
                                or "error" in parsed
                            ):
                                result_failed = True
                    except (ValueError, TypeError):
                        pass
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
                    late_status = (
                        "uncertain"
                        if result_uncertain and archived.get("mutation") is True
                        else ("late_failed" if result_failed else "late_succeeded")
                    )
                    self._journal.update(
                        archived["operation_id"],
                        status=late_status,
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
            result_status = (
                "uncertain"
                if result_uncertain and command.mutation
                else ("failed" if result_failed else "succeeded")
            )
            self._journal.update(
                command.operation_id,
                status=result_status,
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

    def _store_result_value(
        self,
        node_id: str,
        command_id: str,
        value: dict[str, Any],
        sanitize_binary: bool = False,
    ) -> str:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
            default=_json_default,
        ).encode("utf-8")
        result_id = token_urlsafe(18)
        created_at = time.time()
        path = self._artifact_dir() / f"{result_id}.json"
        path.write_bytes(raw)
        item = {
            "path": path, "node_id": node_id, "command_id": command_id,
            "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "created_at": created_at, "mime_type": "application/json", "resource_ids": [],
        }
        self._external_results[result_id] = item
        self._extract_image_resources(result_id, value, created_at)
        if item["resource_ids"]:
            self._write_resource_sidecar(result_id)
        if sanitize_binary:
            clean_value = _sanitize_binary_payload(value)
            clean_raw = json.dumps(
                clean_value,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
                default=_json_default,
            ).encode("utf-8")
            if clean_raw != raw:
                path.write_bytes(clean_raw)
                item["size_bytes"] = len(clean_raw)
                item["sha256"] = hashlib.sha256(clean_raw).hexdigest()
        return result_id


    def store_external_result(
        self,
        node_id: str,
        value: dict[str, Any],
        command_id: str = "direct",
        *,
        sanitize_binary: bool = False,
    ) -> dict[str, Any]:
        self._configured()
        self._validate_node_id(node_id)
        if not isinstance(value, dict):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion command result must be a JSON-safe object")
        self._cleanup_external_results()
        result_id = self._store_result_value(
            node_id, command_id, value, sanitize_binary=sanitize_binary
        )
        item = self._external_results[result_id]
        return {
            "external_result": {
                "result_id": result_id,
                "size_bytes": item["size_bytes"],
                "sha256": item["sha256"],
            },
            "isError": (value.get("isError") is not False) if "isError" in value else False,
        }

    def _extract_image_resources(self, result_id: str, value: dict[str, Any], created_at: float) -> None:
        parent = self._external_results[result_id]
        extracted = extract_binary_resources(value)
        for index, item in enumerate(extracted):
            resource_id = token_urlsafe(18)
            extension = _MIME_EXTENSIONS.get(item.mime_type, ".bin")
            base_name = item.suggested_name or f"{result_id}-resource-{index}"
            if not base_name.endswith(extension):
                file_name = f"{base_name}{extension}"
            else:
                file_name = base_name
            path = self._artifact_dir() / f"{result_id}-res-{index}{extension}"
            path.write_bytes(item.raw_bytes)
            self._external_resources[resource_id] = {
                "path": path,
                "parent_result_id": result_id,
                "size_bytes": len(item.raw_bytes),
                "sha256": hashlib.sha256(item.raw_bytes).hexdigest(),
                "created_at": created_at,
                "mime_type": item.mime_type,
                "file_name": file_name,
                "stable_capability": token_urlsafe(32),
            }
            parent["resource_ids"].append(resource_id)

    def _write_resource_sidecar(self, result_id: str) -> None:
        """Persist extracted resource descriptors so a sanitized (binary-free)
        result can still restore its image resources after a process restart."""
        item = self._external_results.get(result_id)
        if item is None:
            return
        descriptors = []
        for resource_id in item.get("resource_ids", []):
            res = self._external_resources.get(resource_id)
            if res is None:
                continue
            descriptors.append({
                "resource_id": resource_id,
                "path_name": res["path"].name,
                "mime_type": res["mime_type"],
                "file_name": res["file_name"],
                "size_bytes": res["size_bytes"],
                "sha256": res["sha256"],
                "created_at": res["created_at"],
                "stable_capability": res["stable_capability"],
            })
        sidecar = self._artifact_dir() / f"{result_id}.resources.json"
        sidecar.write_text(
            json.dumps(
                {"version": 2, "resources": descriptors},
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def overwrite_external_result(
        self,
        reference: dict[str, Any],
        value: dict[str, Any],
    ) -> None:
        """Replace the model-visible stored JSON of an existing external result.

        Used by the fusion_cad screenshot path to bind the exported ViewRef image
        to the real extracted image ResourceLink URI after store-time
        sanitization. Already-extracted image resource files and their
        registration (including process-restart recovery via the sidecar
        metadata file) are preserved.
        """
        self._configured()
        result_id = reference.get("result_id") if isinstance(reference, dict) else None
        if not isinstance(result_id, str) or not result_id:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT, "External result reference is invalid"
            )
        item = self._external_results.get(result_id) or self._recover_external_result(
            result_id
        )
        if item is None:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT, "External desktop result is unavailable"
            )
        if not isinstance(value, dict):
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "Fusion command result must be a JSON-safe object",
            )
        raw = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
            default=_json_default,
        ).encode("utf-8")
        if len(raw) > self.settings.max_result_bytes:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Fusion command result is too large")
        item["path"].write_bytes(raw)
        item["size_bytes"] = len(raw)
        item["sha256"] = hashlib.sha256(raw).hexdigest()

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
                for pattern in (f"{result_id}-res-*", f"{result_id}-image-*"):
                    for res_path in self._artifact_dir().glob(pattern):
                        try:
                            res_path.unlink(missing_ok=True)
                        except OSError:
                            pass
                sidecar = self._artifact_dir() / f"{result_id}.resources.json"
                try:
                    sidecar.unlink(missing_ok=True)
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
        if self._external_results[result_id]["resource_ids"]:
            self._write_resource_sidecar(result_id)
        return {
            "external_result": {
                "result_id": result_id,
                "size_bytes": upload.size_bytes,
                "sha256": upload.sha256,
            },
            "isError": (value.get("isError") is not False) if "isError" in value else False,
        }

    def _load_resource_sidecar(self, result_id: str) -> list[dict[str, Any]] | None:
        """Read and strictly validate the persisted resource sidecar.

        Returns None for a missing, unreadable, oversized, or invalid sidecar so
        recovery can fail closed instead of trusting its metadata.
        """
        sidecar = self._artifact_dir() / f"{result_id}.resources.json"
        try:
            if sidecar.stat().st_size > _SIDECAR_MAX_BYTES:
                return None
            document = json.loads(sidecar.read_text("utf-8"))
        except (OSError, ValueError):
            return None
        return parse_resource_sidecar(
            document,
            result_id=result_id,
            max_resource_bytes=self.settings.max_result_bytes,
            now=time.time(),
        )

    def _restore_resource_descriptors(
        self,
        result_id: str,
        item: dict[str, Any],
        descriptors: list[dict[str, Any]],
    ) -> bool:
        """Register validated sidecar resources for this result, all-or-nothing.

        Every descriptor must resolve to a regular file directly inside the
        artifact directory whose real size and SHA-256 match the sidecar; any
        mismatch leaves the result without binary resources.
        """
        artifact_dir = self._artifact_dir()
        restored: list[tuple[str, dict[str, Any]]] = []
        for descriptor in descriptors:
            resource_id = descriptor["resource_id"]
            if resource_id in self._external_resources:
                return False
            path = artifact_dir / descriptor["path_name"]
            try:
                contained = path.resolve()
                if contained.parent != artifact_dir or not contained.is_file():
                    return False
                if contained.stat().st_size != descriptor["size_bytes"]:
                    return False
                digest = hashlib.sha256(contained.read_bytes()).hexdigest()
            except OSError:
                return False
            if not compare_digest(digest, descriptor["sha256"]):
                return False
            restored.append((resource_id, {
                "path": contained,
                "parent_result_id": result_id,
                "size_bytes": descriptor["size_bytes"],
                "sha256": descriptor["sha256"],
                "created_at": descriptor["created_at"],
                "mime_type": descriptor["mime_type"],
                "file_name": descriptor["file_name"],
                "stable_capability": descriptor["stable_capability"] or token_urlsafe(32),
            }))
        for resource_id, resource in restored:
            self._external_resources[resource_id] = resource
            item["resource_ids"].append(resource_id)
        return True

    def _recover_external_result(self, result_id: Any) -> dict[str, Any] | None:
        if not isinstance(result_id, str) or re.fullmatch(r"[A-Za-z0-9_-]{16,64}", result_id) is None:
            return None
        path = self._artifact_dir() / f"{result_id}.json"
        try:
            stat = path.stat()
            if stat.st_mtime <= time.time() - self.settings.result_artifact_ttl_seconds:
                path.unlink(missing_ok=True)
                for pattern in (f"{result_id}-res-*", f"{result_id}-image-*"):
                    for res_path in self._artifact_dir().glob(pattern):
                        res_path.unlink(missing_ok=True)
                sidecar = self._artifact_dir() / f"{result_id}.resources.json"
                try:
                    sidecar.unlink(missing_ok=True)
                except OSError:
                    pass
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
        sidecar = self._artifact_dir() / f"{result_id}.resources.json"
        if sidecar.exists():
            descriptors = self._load_resource_sidecar(result_id)
            if descriptors and self._restore_resource_descriptors(result_id, item, descriptors):
                # Rewrite as the current schema; this is also the explicit
                # legacy v1 -> v2 migration (fresh stable capability).
                self._write_resource_sidecar(result_id)
        else:
            self._extract_image_resources(result_id, value, stat.st_mtime)
        return item

    def _stable_export_grant(
        self, holder: dict[str, Any], cache_key: str, subject: str
    ) -> tuple[str, Any]:
        """Reuse one live export token for an in-memory result/resource.

        ViewRef.image must equal the ResourceLink URI emitted for the same image.
        Export grants are process-local, just like ViewRefStore, so cache the token
        on the owning in-memory result/resource and renew only after expiry.
        """
        cached = holder.get(cache_key)
        if isinstance(cached, str):
            grant = self._exports.lookup(cached)
            if grant is not None and grant.subject == subject:
                return cached, grant
        token, grant = self._exports.issue(subject)
        holder[cache_key] = token
        return token, grant

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
            token, grant = self._stable_export_grant(item, "_export_token", result_id)
            metadata["export_url"] = f"{self._public_base_url}{self._export_path}/{quote(token, safe='')}"
            metadata["expires_at"] = grant.expires_at.isoformat()
            for resource_id in item.get("resource_ids", []):
                resource = self._external_resources.get(resource_id)
                if resource is None:
                    continue
                stable_capability = resource.get("stable_capability")
                if not isinstance(stable_capability, str) or re.fullmatch(
                    r"[A-Za-z0-9_-]{32,128}", stable_capability
                ) is None:
                    raise BridgeError(
                        ErrorCode.INTERNAL_ERROR,
                        "External binary resource lacks its stable capability",
                    )
                resource_token = f"r1.{result_id}.{stable_capability}"
                expires_at = datetime.fromtimestamp(
                    float(resource["created_at"]) + self.settings.result_artifact_ttl_seconds,
                    UTC,
                ).isoformat()
                metadata["resources"].append({
                    "uri": f"{self._public_base_url}{self._export_path}/{quote(resource_token, safe='')}",
                    "file_name": resource["file_name"], "mime_type": resource["mime_type"],
                    "size_bytes": resource["size_bytes"], "sha256": resource["sha256"],
                    "expires_at": expires_at,
                })
        return value, metadata

    def resolve_external_export(self, token: str) -> tuple[Path, dict[str, Any]] | None:
        self._cleanup_external_results()
        stable = re.fullmatch(
            r"r1\.([A-Za-z0-9_-]{16,64})\.([A-Za-z0-9_-]{32,128})", token
        )
        if stable is not None:
            result_id, capability = stable.groups()
            parent = self._external_results.get(result_id) or self._recover_external_result(
                result_id
            )
            if parent is None:
                return None
            for resource_id in parent.get("resource_ids", []):
                resource = self._external_resources.get(resource_id)
                stored = resource.get("stable_capability") if resource is not None else None
                if isinstance(stored, str) and compare_digest(stored, capability):
                    return resource["path"], resource
            return None

        grant = self._exports.lookup(token)
        if grant is None:
            return None
        if grant.subject.startswith("resource:"):
            item = self._external_resources.get(grant.subject.removeprefix("resource:"))
        else:
            item = self._external_results.get(grant.subject)
        return (item["path"], item) if item is not None else None
