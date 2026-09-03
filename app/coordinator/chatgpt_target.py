from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from app.api.errors import BridgeError, ErrorCode

_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True, slots=True)
class ChatGptTarget:
    route_url: str
    conversation_url: str
    conversation_id: str
    project_id: str | None = None
    gpt_id: str | None = None
    slug: str | None = None


def _invalid() -> BridgeError:
    return BridgeError(
        ErrorCode.INVALID_ARGUMENT,
        "url must point unambiguously to an https://chatgpt.com conversation",
    )


def _valid_segment(value: str) -> bool:
    return bool(value) and bool(_SEGMENT_RE.fullmatch(value))


def canonical_conversation_url(conversation_id: str) -> str:
    value = str(conversation_id).strip()
    if not _valid_segment(value):
        raise _invalid()
    return f"https://chatgpt.com/c/{value}"


def parse_chatgpt_target(value: str) -> ChatGptTarget:
    raw = str(value).strip()
    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        raise _invalid() from exc

    if (
        parts.scheme.lower() != "https"
        or parts.netloc.lower() != "chatgpt.com"
        or parts.netloc != "chatgpt.com"
        or not parts.path.startswith("/")
    ):
        raise _invalid()

    path = parts.path.rstrip("/")
    segments = path.lstrip("/").split("/") if path != "/" else []
    if not segments or any(not segment for segment in segments):
        raise _invalid()
    if any(not _valid_segment(segment) for segment in segments):
        raise _invalid()

    c_positions = [index for index, segment in enumerate(segments) if segment == "c"]
    if len(c_positions) != 1:
        raise _invalid()
    c_index = c_positions[0]
    if c_index != len(segments) - 2:
        raise _invalid()

    conversation_id = segments[-1]
    prefix = segments[:c_index]
    project_id: str | None = None
    gpt_id: str | None = None
    slug: str | None = None

    if prefix:
        if len(prefix) not in {2, 3} or prefix[0] != "g":
            raise _invalid()
        context_id = prefix[1]
        if not context_id.startswith("g-"):
            raise _invalid()
        if context_id.startswith("g-p-"):
            project_id = context_id
        else:
            gpt_id = context_id
        if len(prefix) == 3:
            slug = prefix[2]

    route_path = "/" + "/".join(segments)
    route_url = urlunsplit(("https", "chatgpt.com", route_path, "", ""))
    return ChatGptTarget(
        route_url=route_url,
        conversation_url=canonical_conversation_url(conversation_id),
        conversation_id=conversation_id,
        project_id=project_id,
        gpt_id=gpt_id,
        slug=slug,
    )
