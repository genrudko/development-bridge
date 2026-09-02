from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from app.api.errors import BridgeError, ErrorCode

from .client import ChatGPTShareTransport
from .parser import parse_share_html

SHARE_PATH = re.compile(r"^/share/([^/]+?)/?$")


@dataclass(frozen=True, slots=True)
class ChatGPTShareService:
    transport: ChatGPTShareTransport
    default_recent: int = 40
    max_recent: int = 200
    max_matches: int = 100
    response_limit_bytes: int = 512 * 1024

    async def read(
        self, url: str, *, mode: str = "recent", limit: int | None = None,
        query: str | None = None, max_matches: int = 20,
    ) -> dict[str, Any]:
        share_id = validate_share_url(url)
        if mode not in {"recent", "search", "full"}:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Unknown share read mode")
        if mode == "search" and (not isinstance(query, str) or not query.strip()):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Search mode requires a non-empty query")
        if mode != "search" and query is not None:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Query is only valid in search mode")
        recent_limit = self.default_recent if limit is None else limit
        if not isinstance(recent_limit, int) or isinstance(recent_limit, bool) or not 1 <= recent_limit <= self.max_recent:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Recent limit is outside the allowed range")
        if not isinstance(max_matches, int) or isinstance(max_matches, bool) or not 1 <= max_matches <= self.max_matches:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "max_matches is outside the allowed range")

        body = await asyncio.to_thread(self.transport.fetch, url)
        payload = parse_share_html(body)
        messages = _visible_messages(payload)
        selected = messages
        truncated = False
        if mode == "recent":
            selected = messages[-recent_limit:]
            truncated = len(selected) < len(messages)
        elif mode == "search":
            needle = query.strip().casefold()  # type: ignore[union-attr]
            matches = [message for message in messages if needle in message["text"].casefold()]
            selected = matches[:max_matches]
            truncated = len(selected) < len(matches)

        result = {
            "title": payload.get("title"),
            "shared_conversation_id": payload.get("sharedConversationId") or payload.get("share_id") or share_id,
            "conversation_id": payload.get("conversation_id") or payload.get("conversationId"),
            "backing_conversation_id": payload.get("backing_conversation_id"),
            "mode": mode,
            "total_visible_count": len(messages),
            "user_count": sum(message["role"] == "user" for message in messages),
            "assistant_count": sum(message["role"] == "assistant" for message in messages),
            "selected_count": len(selected),
            "truncated": truncated,
            "messages": selected,
        }
        if mode == "search":
            result["total_match_count"] = sum(query.strip().casefold() in message["text"].casefold() for message in messages)  # type: ignore[union-attr]
        if mode == "full":
            result = self._cap_full_result(result)
        else:
            result["returned_count"] = len(result["messages"])
        return result

    def _cap_full_result(self, result: dict[str, Any]) -> dict[str, Any]:
        messages = result["messages"]
        encoded_messages = [
            json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode()
            for message in messages
        ]
        payload_bytes = 0
        returned_count = 0
        for index, encoded in enumerate(encoded_messages):
            candidate_count = index + 1
            candidate = {
                **result,
                "messages": [],
                "selected_count": candidate_count,
                "returned_count": candidate_count,
                "truncated": candidate_count < len(messages),
                "response_limit_bytes": self.response_limit_bytes,
            }
            metadata_bytes = len(
                json.dumps(candidate, ensure_ascii=False, separators=(",", ":")).encode()
            )
            candidate_payload_bytes = payload_bytes + len(encoded) + (1 if index else 0)
            # `messages:[]` already contributes the two array delimiters, so
            # only the serialized elements and their commas need adding.
            if metadata_bytes + candidate_payload_bytes > self.response_limit_bytes:
                break
            payload_bytes = candidate_payload_bytes
            returned_count = candidate_count
        result["messages"] = messages[:returned_count]
        result["selected_count"] = returned_count
        result["returned_count"] = returned_count
        result["truncated"] = returned_count < len(messages)
        result["response_limit_bytes"] = self.response_limit_bytes
        return result


def validate_share_url(url: str) -> str:
    if not isinstance(url, str):
        raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Share URL must be a string")
    parsed = urlsplit(url)
    match = SHARE_PATH.fullmatch(parsed.path)
    if parsed.scheme != "https" or parsed.hostname != "chatgpt.com" or parsed.port is not None or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment or match is None:
        raise BridgeError(ErrorCode.INVALID_ARGUMENT, "URL must be a public https://chatgpt.com/share/<id> URL")
    return match.group(1)


def _visible_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    linear = payload.get("linear_conversation")
    mapping = payload.get("mapping") if isinstance(payload.get("mapping"), dict) else {}
    if not isinstance(linear, list):
        linear = _mapping_path(mapping, payload.get("current_node"))
    messages: list[dict[str, Any]] = []
    for entry in linear:
        node = mapping.get(entry, {}) if isinstance(entry, str) else entry
        if not isinstance(node, dict):
            continue
        message = node.get("message", node)
        if not isinstance(message, dict):
            continue
        author = message.get("author")
        role = author.get("role") if isinstance(author, dict) else message.get("role")
        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        if (
            role not in {"user", "assistant"}
            or metadata.get("is_visually_hidden_from_conversation") is True
            or metadata.get("is_redacted") is True
            or metadata.get("is_user_system_message") is True
            or metadata.get("is_thinking_preamble_message") is True
        ):
            continue
        text = _message_text(message.get("content"))
        if not text.strip():
            continue
        clean = {
            "id": message.get("id") or node.get("id"),
            "role": role,
            "text": text.strip(),
            "create_time": message.get("create_time"),
            "metadata": metadata,
        }
        clean["index"] = len(messages)
        messages.append(clean)
    return messages


def _mapping_path(mapping: dict[str, Any], current: Any) -> list[Any]:
    path: list[Any] = []
    seen: set[str] = set()
    while isinstance(current, str) and current not in seen:
        seen.add(current)
        node = mapping.get(current)
        if not isinstance(node, dict):
            break
        path.append(node)
        current = node.get("parent")
    path.reverse()
    return path


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, dict):
        return ""
    content_type = content.get("content_type")
    if content_type not in {None, "text", "multimodal_text"}:
        return ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        text = content.get("text")
        return text if isinstance(text, str) else ""
    textual: list[str] = []
    for part in parts:
        if isinstance(part, str):
            textual.append(part)
        elif isinstance(part, dict):
            part_type = part.get("content_type") or part.get("type")
            if part_type in {"text", "input_text"} and isinstance(part.get("text"), str):
                textual.append(part["text"])
    return "\n".join(textual)
