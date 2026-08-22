from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from app.api.errors import BridgeError, ErrorCode

from .attachments import KnowledgeAttachmentService


MAX_EXPORT_TOKENS = 4096


@dataclass(frozen=True, slots=True)
class AttachmentExportGrant:
    source_id: str
    message_id: str
    attachment_id: str
    expires_at: datetime
    expires_monotonic: float


class AttachmentExportRegistry:
    """Bounded, process-local registry of opaque attachment export grants."""

    def __init__(
        self,
        ttl_seconds: int,
        *,
        capacity: int = MAX_EXPORT_TOKENS,
        monotonic: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if ttl_seconds <= 0 or capacity <= 0:
            raise ValueError("Export token TTL and capacity must be positive")
        self.ttl_seconds = ttl_seconds
        self.capacity = capacity
        self._monotonic = monotonic
        self._utcnow = utcnow
        self._grants: dict[str, AttachmentExportGrant] = {}
        self._lock = threading.Lock()

    def issue(
        self, source_id: str, message_id: str, attachment_id: str
    ) -> tuple[str, AttachmentExportGrant]:
        with self._lock:
            now = self._monotonic()
            self._cleanup(now)
            if len(self._grants) >= self.capacity:
                oldest = min(
                    self._grants,
                    key=lambda token: self._grants[token].expires_monotonic,
                )
                del self._grants[oldest]
            token = secrets.token_urlsafe(32)
            while token in self._grants:
                token = secrets.token_urlsafe(32)
            grant = AttachmentExportGrant(
                source_id=source_id,
                message_id=message_id,
                attachment_id=attachment_id,
                expires_at=self._utcnow() + timedelta(seconds=self.ttl_seconds),
                expires_monotonic=now + self.ttl_seconds,
            )
            self._grants[token] = grant
            return token, grant

    def lookup(self, token: str) -> AttachmentExportGrant | None:
        with self._lock:
            now = self._monotonic()
            self._cleanup(now)
            return self._grants.get(token)

    def _cleanup(self, now: float) -> None:
        expired = [
            token
            for token, grant in self._grants.items()
            if grant.expires_monotonic <= now
        ]
        for token in expired:
            del self._grants[token]


class KnowledgeAttachmentExportService:
    def __init__(
        self,
        attachments: KnowledgeAttachmentService,
        registry: AttachmentExportRegistry,
        public_base_url: str | None,
        endpoint: str,
    ) -> None:
        self.attachments = attachments
        self.registry = registry
        self.public_base_url = public_base_url.rstrip("/") if public_base_url else None
        self.export_path = endpoint.rstrip("/") + "/knowledge/exports"

    async def export(self, source_id: str, message_id: str, attachment_id: str) -> dict:
        if self.public_base_url is None:
            raise BridgeError(
                ErrorCode.KNOWLEDGE_EXPORT_NOT_CONFIGURED,
                "server.public_base_url is required for knowledge attachment export",
            )
        snapshot, _ = await self.attachments.ensure_snapshot(
            source_id, message_id, attachment_id
        )
        token, grant = self.registry.issue(source_id, message_id, attachment_id)
        return {
            "source_id": source_id,
            "message_id": message_id,
            "attachment_id": attachment_id,
            "file_name": snapshot["file_name"],
            "media_type": snapshot["media_type"],
            "size_bytes": snapshot["size_bytes"],
            "sha256": snapshot["sha256"],
            "export_url": f"{self.public_base_url}{self.export_path}/{quote(token, safe='')}",
            "expires_at": grant.expires_at.isoformat(),
        }

    def resolve(self, token: str) -> tuple[object, Path] | None:
        grant = self.registry.lookup(token)
        if grant is None:
            return None
        try:
            return self.attachments.snapshot_file(
                grant.source_id, grant.message_id, grant.attachment_id
            )
        except (BridgeError, OSError):
            return None
