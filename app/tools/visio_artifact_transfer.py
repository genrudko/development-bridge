"""Server-pinned Visio document sender via the already-authenticated desktop-node queue."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from pathlib import Path
from zipfile import ZipFile

MAX_BYTES = 32 * 1024 * 1024
CHUNK_SIZE = 160 * 1024
_ALLOWED = re.compile(r"^[\w .()\-]{1,120}\.(?:vsdx|vsdm)$", re.IGNORECASE)


def outbox_file(outbox: Path, name: str) -> Path:
    if (not isinstance(name, str) or not _ALLOWED.fullmatch(name)
            or name.startswith(".") or name.endswith((" ", "."))
            or any(char in name for char in ("/", "\\", ":"))):
        raise ValueError("Only safe .vsdx/.vsdm basenames are allowed")
    root = outbox.resolve()
    path = (root / name).resolve(strict=True)
    if path.parent != root or not path.is_file():
        raise ValueError("Artifact must be a regular file inside outbox")
    if not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError("Artifact exceeds size limit")
    with ZipFile(path) as z:
        required = {"[Content_Types].xml", "_rels/.rels", "visio/document.xml", "visio/pages/pages.xml"}
        if not required.issubset(z.namelist()) or z.testzip() is not None:
            raise ValueError("Invalid Visio document package")
    return path


def outbox_path(container) -> Path:
    return (Path(container.desktop_nodes.settings.result_artifact_directory)
            .expanduser().resolve().parent / "visio-outbox")


def unpack_desktop_result(payload) -> dict:
    """Read structured or text-based tool response; reject unknown shapes."""
    if not isinstance(payload, dict):
        raise ValueError("Invalid desktop result envelope")
    structured = payload.get("structuredContent")
    if isinstance(structured, dict) and "result" in structured:
        value = structured["result"]
    else:
        messages = [
            item.get("text") for item in payload.get("content", [])
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        if len(messages) != 1:
            raise ValueError("Missing desktop result")
        value = messages[0]
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("Invalid desktop result payload")
    return value


async def transfer_artifact(container, *, node_id: str, file_name: str,
                            open_in_visio: bool, error_reader):
    path = outbox_file(outbox_path(container), file_name)
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    transfer_id = uuid.uuid4().hex
    chunk_count = 0
    for offset in range(0, len(raw), CHUNK_SIZE):
        chunk = raw[offset:offset + CHUNK_SIZE]
        result = await container.desktop_nodes.call(
            node_id, "stage_visio_artifact_chunk", {
                "transfer_id": transfer_id,
                "file_name": path.name,
                "offset": offset,
                "content_b64": base64.b64encode(chunk).decode("ascii"),
                "total_size": len(raw),
                "sha256": sha,
                "final": offset + len(chunk) == len(raw),
            }, {"mutation": True, "summary": "Stage SHA256-pinned Visio document into dedicated Windows workspace"})
        failure = error_reader(result)
        if failure:
            raise RuntimeError("Visio artifact chunk rejected: " + failure)
        chunk_count += 1

    status = await container.desktop_nodes.call(
        node_id, "visio_artifact_status", {"transfer_id": transfer_id},
        {"mutation": False, "summary": "Verify completed Visio document on desktop"})
    failure = error_reader(status)
    if failure:
        raise RuntimeError("Visio received artifact verification failed: " + failure)
    verified = unpack_desktop_result(status)
    if (verified.get("complete") is not True
            or verified.get("transfer_id") != transfer_id
            or verified.get("sha256") != sha
            or verified.get("size_bytes") != len(raw)
            or verified.get("file_name") != path.name):
        raise RuntimeError("Desktop receipt mismatch; do not open document")

    opening = None
    if open_in_visio:
        opening = await container.desktop_nodes.call(
            node_id, "open_received_visio_artifact", {"transfer_id": transfer_id},
            {"mutation": True, "summary": "Open transferred Visio document in read-only macro-disabled mode"})
        failure = error_reader(opening)
        if failure:
            raise RuntimeError("Artifact transferred but Visio could not open it: " + failure)
        opened = unpack_desktop_result(opening)
        if (opened.get("transfer_id") != transfer_id
                or opened.get("sha256") != sha
                or opened.get("mode") != "read_only_macro_disabled"
                or not opened.get("document_name")):
            raise RuntimeError("Desktop open acknowledgment mismatch")

    return {
        "transfer_id": transfer_id,
        "file_name": path.name,
        "sha256": sha,
        "size_bytes": len(raw),
        "chunks": chunk_count,
        "opened": bool(open_in_visio),
        "transport": "authenticated-visio-node-chunked",
    }
