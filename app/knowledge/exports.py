from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from app.api.capability_exports import CapabilityExportRegistry
from app.api.errors import BridgeError, ErrorCode

from .attachments import KnowledgeAttachmentService


MAX_EXPORT_TOKENS = 4096


@dataclass(frozen=True, slots=True)
class AttachmentExportSubject:
    source_id: str
    message_id: str
    attachment_id: str


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
        self._registry = CapabilityExportRegistry[AttachmentExportSubject](
            ttl_seconds,
            capacity=capacity,
            monotonic=monotonic,
            utcnow=utcnow,
        )

    def issue(
        self, source_id: str, message_id: str, attachment_id: str
    ) -> tuple[str, AttachmentExportGrant]:
        token, grant = self._registry.issue(
            AttachmentExportSubject(source_id, message_id, attachment_id)
        )
        return token, AttachmentExportGrant(
            source_id,
            message_id,
            attachment_id,
            grant.expires_at,
            grant.expires_monotonic,
        )

    def lookup(self, token: str) -> AttachmentExportGrant | None:
        grant = self._registry.lookup(token)
        if grant is None:
            return None
        subject = grant.subject
        return AttachmentExportGrant(
            subject.source_id,
            subject.message_id,
            subject.attachment_id,
            grant.expires_at,
            grant.expires_monotonic,
        )


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
