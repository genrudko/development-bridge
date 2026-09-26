from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any


OPENAI_NAMESPACE = "openai"
SESSION_FIELD = "session"
SESSION_META_KEY = OPENAI_NAMESPACE + "/" + SESSION_FIELD
_SESSION_FINGERPRINT_DOMAIN = b"development-bridge/chatgpt-session/v1\0"


def request_meta(source: Any) -> Mapping[str, Any]:
    request_context = getattr(source, "request_context", None)
    meta = getattr(request_context, "meta", None)
    if isinstance(meta, Mapping):
        return meta
    direct_meta = getattr(source, "meta", None)
    if isinstance(direct_meta, Mapping):
        return direct_meta
    return {}


def chatgpt_session_key(*sources: Any) -> str | None:
    for source in sources:
        value = request_meta(source).get(SESSION_META_KEY)
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def chatgpt_session_fingerprint(*sources: Any) -> str | None:
    key = chatgpt_session_key(*sources)
    if key is None:
        return None
    return sha256(_SESSION_FINGERPRINT_DOMAIN + key.encode("utf-8")).hexdigest()
