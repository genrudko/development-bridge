"""Bounded, integrity-checked Visio artifact staging (Python stdlib only)."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import zipfile
from pathlib import Path

MAX_SIZE = 32 * 1024 * 1024
MAX_CHUNK = 160 * 1024
TRANSFER_ID = re.compile(r"^[a-f0-9]{32}$")
DOC_NAME = re.compile(r"^[\w .()\-]{1,120}\.(?:vsdx|vsdm)$", re.IGNORECASE)


def checked_name(name: str) -> str:
    if not isinstance(name, str) or not DOC_NAME.fullmatch(name):
        raise ValueError("Only safe .vsdx/.vsdm basenames are allowed")
    if name != Path(name).name or name.startswith(".") or name.endswith((" ", ".")):
        raise ValueError("Unsafe filename")
    if any(ch in name for ch in ("/", "\\", ":")):
        raise ValueError("Path separators prohibited")
    return name


def validate_package(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            parts = archive.infolist()
            if len(parts) > 10000:
                raise ValueError("Excessive Visio package entries")
            names = {p.filename for p in parts}
            required = {"[Content_Types].xml", "_rels/.rels", "visio/document.xml", "visio/pages/pages.xml"}
            if not required.issubset(names):
                raise ValueError("Missing required Visio OPC parts")
            if sum(p.file_size for p in parts) > 256 * 1024 * 1024:
                raise ValueError("Uncompressed package exceeds limit")
            for info in parts:
                parts_path = info.filename.replace("\\", "/").split("/")
                if any(p in {"..", ""} for p in parts_path[:-1]) or info.filename.startswith("/"):
                    raise ValueError("Invalid Visio package part name")
            if archive.testzip() is not None:
                raise ValueError("Corrupt Visio package CRC")
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ValueError("Not a valid Visio OPC file") from exc


class ArtifactReceiver:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, transfer_id: str) -> Path:
        if not isinstance(transfer_id, str) or not TRANSFER_ID.fullmatch(transfer_id):
            raise ValueError("Bad transfer identifier")
        return self.root / transfer_id

    def receive(self, *, transfer_id: str, file_name: str, offset: int,
                content_b64: str, total_size: int, sha256: str,
                final: bool = False) -> dict:
        checked_name(file_name)
        folder = self._dir(transfer_id)
        if not isinstance(total_size, int) or not 0 < total_size <= MAX_SIZE:
            raise ValueError("Artifact size outside limits")
        if not isinstance(sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", sha256):
            raise ValueError("Invalid digest")
        if not isinstance(offset, int) or offset < 0:
            raise ValueError("Invalid offset")
        try:
            raw = base64.b64decode(content_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Invalid base64") from exc
        if not 0 < len(raw) <= MAX_CHUNK:
            raise ValueError("Chunk outside limits")
        folder.mkdir(parents=True, exist_ok=True)
        part = folder / "incoming.part"
        manifest = folder / "manifest.json"
        if manifest.exists():
            raise ValueError("Transfer already finalized (immutable)")
        if offset == 0 and part.exists():
            raise ValueError("Transfer already exists, use a new transfer_id")
        have = part.stat().st_size if part.exists() else 0
        if have != offset or have + len(raw) > total_size:
            raise ValueError("Non-sequential chunk or unexpected total size")
        with part.open("ab") as f:
            f.write(raw)
        size = have + len(raw)
        if not final:
            if size == total_size:
                raise ValueError("Final chunk must be explicitly marked")
            return {"transfer_id": transfer_id, "received": size, "total_size": total_size, "complete": False}
        if size != total_size or hashlib.sha256(part.read_bytes()).hexdigest() != sha256:
            part.unlink(missing_ok=True)
            raise ValueError("Final size or SHA-256 mismatch")
        try:
            validate_package(part)
        except Exception:
            part.unlink(missing_ok=True)
            raise
        target = folder / file_name
        part.replace(target)
        details = {"transfer_id": transfer_id, "file_name": file_name,
                   "sha256": sha256, "size_bytes": size}
        manifest.write_text(json.dumps(details, ensure_ascii=False), encoding="utf-8")
        return {"complete": True, **details}

    def status(self, transfer_id: str) -> dict:
        folder = self._dir(transfer_id)
        manifest = folder / "manifest.json"
        if not manifest.is_file():
            return {"transfer_id": transfer_id, "complete": False}
        details = json.loads(manifest.read_text(encoding="utf-8"))
        name = checked_name(details["file_name"])
        file = folder / name
        if (not file.is_file() or file.stat().st_size != details["size_bytes"]
                or hashlib.sha256(file.read_bytes()).hexdigest() != details["sha256"]):
            raise ValueError("Received artifact integrity verification failed")
        return {"complete": True, "path": str(file), **details}
