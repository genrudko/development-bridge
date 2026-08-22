from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import os
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.api.errors import BridgeError, ErrorCode

from .store import KnowledgeStore
from .telegram import (
    TelegramAdapter,
    TelegramAttachmentTooLarge,
    TelegramAuthorizationRequired,
    TelegramFloodWait,
    TelegramRequestFailed,
    TelegramSource,
    TelegramSourceNotFound,
)


INLINE_IMAGE_LIMIT = 8 * 1024 * 1024
TEXT_PREVIEW_LIMIT = 64 * 1024
PDF_PAGE_LIMIT = 20
VIDEO_FRAME_LIMIT = 8
TEXT_EXTENSIONS = {
    ".txt", ".log", ".cfg", ".conf", ".ini", ".yaml", ".yml", ".json",
    ".md", ".gcode", ".py", ".js", ".ts", ".css", ".html", ".xml",
}
IMAGE_MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


@dataclass(frozen=True, slots=True)
class PreviewFrame:
    data: bytes
    media_type: str = "image/png"


class VideoPreviewer(Protocol):
    def preview(self, path: Path, max_frames: int) -> tuple[dict[str, Any], tuple[PreviewFrame, ...]]: ...


class FfmpegVideoPreviewer:
    def __init__(self) -> None:
        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")

    def preview(self, path: Path, max_frames: int) -> tuple[dict[str, Any], tuple[PreviewFrame, ...]]:
        if self.ffmpeg is None or self.ffprobe is None:
            return {"available": False, "reason": "ffmpeg_unavailable"}, ()
        probe = subprocess.run(
            [self.ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            check=True, capture_output=True, timeout=30,
        )
        metadata = json.loads(probe.stdout)
        duration = float(metadata.get("format", {}).get("duration") or 0)
        video = next(
            (item for item in metadata.get("streams", []) if item.get("codec_type") == "video"),
            {},
        )
        summary = {
            "available": True,
            "duration_seconds": duration,
            "width": video.get("width"),
            "height": video.get("height"),
            "codec": video.get("codec_name"),
        }
        if duration <= 0:
            return summary, ()
        count = min(max_frames, VIDEO_FRAME_LIMIT)
        times = [duration * (index + 1) / (count + 1) for index in range(count)]
        frames = []
        for position in times:
            frame = subprocess.run(
                [
                    self.ffmpeg, "-v", "error", "-ss", f"{position:.3f}",
                    "-i", str(path), "-frames:v", "1", "-f", "image2pipe",
                    "-vcodec", "png", "pipe:1",
                ],
                check=True, capture_output=True, timeout=30,
            ).stdout
            if frame and len(frame) <= INLINE_IMAGE_LIMIT:
                frames.append(PreviewFrame(frame))
        return summary, tuple(frames)


@dataclass(frozen=True, slots=True)
class AttachmentResult:
    metadata: dict[str, Any]
    path: Path
    text_preview: str | None = None
    images: tuple[PreviewFrame, ...] = ()


class AttachmentStorage:
    def __init__(self, root: Path, max_bytes: int) -> None:
        self.root = root
        self.max_bytes = max_bytes
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

    def path_for(self, storage_name: str) -> Path:
        candidate = self.root / storage_name
        if candidate.is_symlink():
            raise FileNotFoundError(storage_name)
        path = candidate.resolve()
        try:
            path.relative_to(self.root.resolve())
        except ValueError as error:
            raise FileNotFoundError(storage_name) from error
        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError(storage_name)
        return path

    def temporary(self) -> Path:
        descriptor, name = tempfile.mkstemp(prefix=".knowledge-attachment-", dir=self.root)
        os.close(descriptor)
        path = Path(name)
        os.chmod(path, 0o600)
        return path

    def finalize(self, temporary: Path) -> tuple[str, Path, int, str]:
        size = temporary.stat().st_size
        if size > self.max_bytes:
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                "Knowledge attachment exceeds the snapshot size limit",
                details={"size_bytes": size, "limit": self.max_bytes},
            )
        digest = hashlib.sha256()
        with temporary.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        sha256 = "sha256:" + digest.hexdigest()
        storage_name = f"{digest.hexdigest()[:2]}/{digest.hexdigest()}"
        destination = self.root / storage_name
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(destination.parent, 0o700)
        if destination.exists():
            temporary.unlink()
        else:
            os.chmod(temporary, 0o600)
            os.replace(temporary, destination)
        os.chmod(destination, 0o600)
        return storage_name, destination, size, sha256

    @staticmethod
    def validate(path: Path, size: int, sha256: str) -> None:
        digest = hashlib.sha256()
        read = 0
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                read += len(chunk)
                digest.update(chunk)
        if read != size or "sha256:" + digest.hexdigest() != sha256:
            raise BridgeError(
                ErrorCode.KNOWLEDGE_ATTACHMENT_CORRUPT,
                "Cached knowledge attachment failed integrity validation",
            )


class KnowledgeAttachmentService:
    def __init__(
        self,
        store: KnowledgeStore,
        storage: AttachmentStorage,
        telegram: TelegramAdapter | None,
        *,
        video_previewer: VideoPreviewer | None = None,
    ) -> None:
        self.store = store
        self.storage = storage
        self.telegram = telegram
        self.video_previewer = video_previewer or FfmpegVideoPreviewer()
        self._lock = asyncio.Lock()

    async def open(self, source_id: str, message_id: str, attachment_id: str) -> AttachmentResult:
        async with self._lock:
            attachment = self._attachment(source_id, message_id, attachment_id)
            snapshot = self._snapshot(source_id, message_id, attachment_id)
            if snapshot is None:
                snapshot = await self._download(source_id, message_id, attachment)
            path = self.storage.path_for(snapshot["storage_name"])
            self.storage.validate(path, snapshot["size_bytes"], snapshot["sha256"])
        metadata = self._public_metadata(attachment, snapshot)
        text_preview = None
        images: tuple[PreviewFrame, ...] = ()
        media_type = snapshot["media_type"]
        if media_type in IMAGE_MEDIA_TYPES and snapshot["size_bytes"] <= INLINE_IMAGE_LIMIT:
            images = (PreviewFrame(path.read_bytes(), media_type),)
        elif self._text_candidate(media_type, snapshot["file_name"]):
            text_preview = self._read_text(path)
        elif media_type == "application/pdf":
            try:
                text_preview = self._read_pdf(path, metadata)
            except (OSError, ValueError, PdfReadError):
                metadata["pdf"] = {"extraction_error": "invalid_or_unsupported_pdf"}
        elif media_type.startswith("video/"):
            try:
                video_metadata, images = await asyncio.to_thread(
                    self.video_previewer.preview, path, VIDEO_FRAME_LIMIT
                )
            except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
                video_metadata, images = {"available": False, "reason": "preview_failed"}, ()
            metadata["video_preview"] = video_metadata
        elif media_type in {"application/zip", "application/x-zip-compressed"}:
            metadata["archive_listing"] = self._zip_listing(path)
        return AttachmentResult(metadata, path, text_preview, images)

    def snapshot_file(self, source_id: str, message_id: str, attachment_id: str):
        self._attachment(source_id, message_id, attachment_id)
        snapshot = self._snapshot(source_id, message_id, attachment_id)
        if snapshot is None:
            raise BridgeError(ErrorCode.KNOWLEDGE_ATTACHMENT_NOT_FOUND, "Attachment snapshot is not cached")
        path = self.storage.path_for(snapshot["storage_name"])
        self.storage.validate(path, snapshot["size_bytes"], snapshot["sha256"])
        return snapshot, path

    def _attachment(self, source_id: str, message_id: str, attachment_id: str):
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT a.*, s.platform, s.source_url, s.title,
                          x.entity_id, x.username, x.source_kind
                   FROM attachments a
                   JOIN messages m ON m.id=a.message_fk
                   JOIN sources s ON s.id=m.source_fk
                   LEFT JOIN source_sync_state x ON x.source_fk=s.id
                   WHERE s.source_id=? AND m.platform_message_id=? AND a.attachment_id=?""",
                (source_id, message_id, attachment_id),
            ).fetchone()
        if row is None:
            raise BridgeError(ErrorCode.KNOWLEDGE_ATTACHMENT_NOT_FOUND, "Knowledge attachment not found")
        return row

    def _snapshot(self, source_id: str, message_id: str, attachment_id: str):
        with self.store.connect() as connection:
            return connection.execute(
                """SELECT * FROM attachment_snapshots
                   WHERE source_id=? AND message_id=? AND attachment_id=?""",
                (source_id, message_id, attachment_id),
            ).fetchone()

    async def _download(self, source_id: str, message_id: str, attachment):
        if attachment["platform"] != "telegram" or self.telegram is None or attachment["entity_id"] is None:
            raise BridgeError(
                ErrorCode.KNOWLEDGE_ATTACHMENT_NOT_FOUND,
                "Attachment has no available live provider",
            )
        declared_size = attachment["declared_size"]
        if declared_size is not None and declared_size > self.storage.max_bytes:
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                "Knowledge attachment exceeds the snapshot size limit",
                details={
                    "declared_size": declared_size,
                    "limit": self.storage.max_bytes,
                },
            )
        source = TelegramSource(
            entity_id=attachment["entity_id"], username=attachment["username"],
            title=attachment["title"], kind=attachment["source_kind"],
            canonical_url=attachment["source_url"],
        )
        temporary = self.storage.temporary()
        try:
            await self.telegram.download_attachment(
                source,
                message_id=int(message_id),
                attachment_id=attachment["attachment_id"],
                expected_metadata=json.loads(attachment["metadata_json"]),
                destination=temporary,
                max_bytes=self.storage.max_bytes,
            )
            storage_name, path, size, sha256 = self.storage.finalize(temporary)
        except TelegramAttachmentTooLarge as error:
            raise BridgeError(
                ErrorCode.POLICY_VIOLATION,
                "Knowledge attachment exceeds the snapshot size limit",
                details={"actual_size": error.actual_size, "limit": error.limit},
            ) from error
        except (TelegramAuthorizationRequired, TelegramSourceNotFound, TelegramFloodWait, TelegramRequestFailed) as error:
            raise self._telegram_error(error) from error
        finally:
            temporary.unlink(missing_ok=True)
        media_type, detected_media_type = self._detect_media_type(
            path, attachment["media_type"], attachment["file_name"]
        )
        file_name = self._safe_filename(attachment["file_name"], media_type)
        snapshot_at = datetime.now(UTC).isoformat()
        provenance = {
            "source_id": source_id, "message_id": message_id,
            "attachment_id": attachment["attachment_id"],
            "telegram_media_id": json.loads(attachment["metadata_json"]).get("telegram_media_id"),
            "declared_media_type": attachment["media_type"],
            "detected_media_type": detected_media_type,
        }
        with self.store.connect() as connection:
            connection.execute(
                """INSERT INTO attachment_snapshots(
                     source_id, message_id, attachment_id, storage_name, size_bytes,
                     sha256, media_type, file_name, snapshot_at, provenance_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source_id, message_id, attachment["attachment_id"], storage_name,
                    size, sha256, media_type, file_name, snapshot_at,
                    json.dumps(provenance, ensure_ascii=False),
                ),
            )
        return self._snapshot(source_id, message_id, attachment["attachment_id"])

    @staticmethod
    def _detect_media_type(
        path: Path, declared: str | None, file_name: str | None
    ) -> tuple[str, str | None]:
        with path.open("rb") as stream:
            header = stream.read(16)
        signatures = (
            (b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"),
            (b"GIF87a", "image/gif"), (b"GIF89a", "image/gif"),
            (b"%PDF-", "application/pdf"), (b"PK\x03\x04", "application/zip"),
        )
        for signature, media_type in signatures:
            if header.startswith(signature):
                return media_type, media_type
        if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
            return "image/webp", "image/webp"
        if declared and declared.startswith("image/"):
            return "application/octet-stream", None
        effective = declared or mimetypes.guess_type(file_name or "")[0] or "application/octet-stream"
        return effective, None

    @staticmethod
    def _safe_filename(value: str | None, media_type: str) -> str:
        candidate = (value or "attachment").replace("\\", "/").rsplit("/", 1)[-1]
        candidate = "".join(character for character in candidate if character.isprintable() and character not in {'"', ';'})
        if candidate in {"", ".", ".."}:
            candidate = "attachment"
        if "." not in candidate:
            extension = mimetypes.guess_extension(media_type) or ""
            candidate += extension
        return candidate[:200]

    @staticmethod
    def _text_candidate(media_type: str, file_name: str) -> bool:
        return media_type.startswith("text/") or Path(file_name).suffix.lower() in TEXT_EXTENSIONS

    @staticmethod
    def _read_text(path: Path) -> str | None:
        with path.open("rb") as stream:
            data = stream.read(TEXT_PREVIEW_LIMIT + 1)
        try:
            text = data[:TEXT_PREVIEW_LIMIT].decode("utf-8")
        except UnicodeDecodeError:
            return None
        if len(data) > TEXT_PREVIEW_LIMIT:
            text += "\n[preview truncated]"
        return text

    @staticmethod
    def _read_pdf(path: Path, metadata: dict[str, Any]) -> str:
        reader = PdfReader(path)
        metadata["pdf"] = {"pages": len(reader.pages), "encrypted": reader.is_encrypted}
        if reader.is_encrypted:
            return "[PDF is encrypted; text extraction unavailable]"
        parts = []
        remaining = TEXT_PREVIEW_LIMIT
        for page in reader.pages[:PDF_PAGE_LIMIT]:
            text = page.extract_text() or ""
            parts.append(text[:remaining])
            remaining -= len(parts[-1])
            if remaining <= 0:
                break
        return "\n\n".join(parts) + ("\n[preview truncated]" if remaining <= 0 else "")

    @staticmethod
    def _zip_listing(path: Path) -> dict[str, Any]:
        try:
            with zipfile.ZipFile(path) as archive:
                names = [item.filename for item in archive.infolist()[:200]]
                return {"entries": names, "truncated": len(archive.infolist()) > 200}
        except (OSError, zipfile.BadZipFile):
            return {"error": "invalid_zip"}

    @staticmethod
    def _public_metadata(attachment, snapshot) -> dict[str, Any]:
        provenance = json.loads(snapshot["provenance_json"])
        declared_media_type = provenance.get("declared_media_type")
        detected_media_type = provenance.get("detected_media_type")
        return {
            "source_id": snapshot["source_id"],
            "message_id": snapshot["message_id"],
            "attachment_id": snapshot["attachment_id"],
            "type": attachment["attachment_type"],
            "media_type": snapshot["media_type"],
            "file_name": snapshot["file_name"],
            "declared_size": attachment["declared_size"],
            "size_bytes": snapshot["size_bytes"],
            "sha256": snapshot["sha256"],
            "snapshot_at": snapshot["snapshot_at"],
            "provider_metadata": json.loads(attachment["metadata_json"]),
            "declared_media_type": declared_media_type,
            "detected_media_type": detected_media_type,
            "media_type_mismatch": bool(
                declared_media_type
                and declared_media_type.startswith("image/")
                and declared_media_type != detected_media_type
            ),
            "cached": True,
        }

    @staticmethod
    def _telegram_error(error: Exception) -> BridgeError:
        if isinstance(error, TelegramAuthorizationRequired):
            return BridgeError(ErrorCode.TELEGRAM_AUTHORIZATION_REQUIRED, "Telegram session is not authorized")
        if isinstance(error, TelegramFloodWait):
            return BridgeError(
                ErrorCode.TELEGRAM_RATE_LIMITED, "Telegram rate limit requires a later retry",
                retryable=True, details={"retry_after_seconds": error.seconds},
            )
        if isinstance(error, TelegramSourceNotFound):
            return BridgeError(ErrorCode.KNOWLEDGE_ATTACHMENT_NOT_FOUND, str(error))
        return BridgeError(ErrorCode.TELEGRAM_REQUEST_FAILED, "Telegram request failed", retryable=True)
