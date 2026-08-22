from __future__ import annotations

import hashlib
import os
from pathlib import Path

from app.api.errors import BridgeError, ErrorCode

from .models import JobArtifact


INLINE_VISUAL_LIMIT_BYTES = 8 * 1024 * 1024
VISUAL_MEDIA_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})


def read_visual_artifact(artifact: JobArtifact, path: Path) -> bytes:
    if not artifact.available or artifact.size_bytes is None or artifact.sha256 is None:
        raise _not_found()
    if artifact.media_type not in VISUAL_MEDIA_TYPES:
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "Artifact media type is not supported for visual viewing",
            details={"media_type": artifact.media_type},
        )
    if artifact.size_bytes > INLINE_VISUAL_LIMIT_BYTES:
        raise BridgeError(
            ErrorCode.POLICY_VIOLATION,
            "Artifact exceeds the inline visual limit",
            details={
                "size_bytes": artifact.size_bytes,
                "limit": INLINE_VISUAL_LIMIT_BYTES,
            },
        )

    try:
        with path.open("rb") as snapshot:
            before = os.fstat(snapshot.fileno())
            if before.st_size != artifact.size_bytes:
                raise _not_found()
            data = snapshot.read(artifact.size_bytes)
            after = os.fstat(snapshot.fileno())
    except BridgeError:
        raise
    except OSError as exc:
        raise _not_found() from exc

    if (
        len(data) != artifact.size_bytes
        or after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
        or "sha256:" + hashlib.sha256(data).hexdigest() != artifact.sha256
    ):
        raise _not_found()
    return data


def _not_found() -> BridgeError:
    return BridgeError(ErrorCode.ARTIFACT_NOT_FOUND, "Artifact is not available")
