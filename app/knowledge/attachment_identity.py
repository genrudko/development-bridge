from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def stable_attachment_id(
    attachment_type: str,
    metadata: dict[str, Any],
    *,
    exported_path: str | None = None,
    fallback_index: int = 0,
) -> str:
    prefix = re.sub(r"[^a-z0-9]+", "-", attachment_type.lower()).strip("-") or "file"
    provider_id = metadata.get("telegram_media_id")
    if provider_id is not None:
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(provider_id)).strip("-")
        if normalized:
            return f"{prefix}-{normalized}"[:200]
    payload = json.dumps(
        {
            "type": attachment_type,
            "metadata": metadata,
            "exported_path": exported_path,
            "index": fallback_index,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:24]}"


def attachment_fields(
    attachment_type: str,
    metadata: dict[str, Any],
    exported_path: str | None,
) -> tuple[str | None, str | None, int | None]:
    media_type = metadata.get("mime_type") or metadata.get("media_type")
    file_name = metadata.get("file_name")
    if file_name is None and exported_path:
        file_name = exported_path.replace("\\", "/").rsplit("/", 1)[-1]
    size = metadata.get("size") or metadata.get("file_size")
    try:
        declared_size = int(size) if size is not None else None
    except (TypeError, ValueError):
        declared_size = None
    return (
        str(media_type) if media_type else None,
        str(file_name) if file_name else None,
        declared_size,
    )
