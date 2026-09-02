from __future__ import annotations

import json
from html.parser import HTMLParser
from typing import Any

from app.api.errors import BridgeError, ErrorCode


class _Scripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.in_script = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() == "script":
            self.in_script = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script":
            self.in_script = False

    def handle_data(self, data: str) -> None:
        if self.in_script:
            self.parts.append(data)


def parse_share_html(body: bytes) -> dict[str, Any]:
    try:
        html = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _format_error() from exc
    collector = _Scripts()
    collector.feed(html)
    chunks: list[str] = []
    marker = "streamController.enqueue("
    for script in collector.parts:
        start = 0
        while (position := script.find(marker, start)) >= 0:
            argument = position + len(marker)
            try:
                value, consumed = json.JSONDecoder().raw_decode(script[argument:].lstrip())
            except (json.JSONDecodeError, TypeError):
                start = argument
                continue
            if isinstance(value, str):
                chunks.append(value)
            start = argument + consumed
    candidates: list[Any] = []
    # enqueue() arguments are fragments of one logical React Router stream and
    # may end anywhere, including in the middle of a JSON record.  Parse the
    # reassembled stream first, then individual chunks for compatibility with
    # pages that enqueue independent, unframed records without newlines.
    streams = ["".join(chunks), *chunks]
    for stream in streams:
        for line in stream.splitlines():
            text = line.strip()
            if not text:
                continue
            # React Router may frame stream records as `data:<json>` or `<id>:<json>`.
            if not text.startswith(("[", "{")) and ":" in text:
                text = text.split(":", 1)[1].lstrip()
            try:
                raw = json.loads(text)
            except json.JSONDecodeError:
                continue
            candidates.extend((raw, _decode_reference_table(raw)))
    for candidate in candidates:
        found = _find_conversation(candidate)
        if found is not None:
            return found
    raise _format_error()


def _decode_reference_table(raw: Any) -> Any:
    if not isinstance(raw, list) or not raw:
        return raw
    table = raw
    memo: dict[int, Any] = {}

    def hydrate(index: int) -> Any:
        if index < 0:
            return None
        if index >= len(table):
            return None
        if index in memo:
            return memo[index]
        value = table[index]
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            memo[index] = result
            for encoded_key, encoded_value in value.items():
                key = hydrate(int(encoded_key[1:])) if encoded_key.startswith("_") and encoded_key[1:].isdigit() else encoded_key
                result[str(key)] = resolve(encoded_value)
            return result
        if isinstance(value, list):
            result_list: list[Any] = []
            memo[index] = result_list
            result_list.extend(resolve(item) for item in value)
            return result_list
        memo[index] = value
        return value

    def resolve(value: Any) -> Any:
        if isinstance(value, int) and not isinstance(value, bool):
            return hydrate(value)
        return value

    try:
        return hydrate(0)
    except (RecursionError, ValueError, TypeError):
        return raw


def _find_conversation(value: Any) -> dict[str, Any] | None:
    seen: set[int] = set()

    def visit(item: Any) -> dict[str, Any] | None:
        if isinstance(item, (dict, list)):
            identity = id(item)
            if identity in seen:
                return None
            seen.add(identity)
        if isinstance(item, dict):
            if "linear_conversation" in item or ("mapping" in item and "current_node" in item):
                return item
            for child in item.values():
                result = visit(child)
                if result is not None:
                    return result
        elif isinstance(item, list):
            for child in item:
                result = visit(child)
                if result is not None:
                    return result
        return None

    return visit(value)


def _format_error() -> BridgeError:
    return BridgeError(
        ErrorCode.CHATGPT_SHARE_UNSUPPORTED_FORMAT,
        "ChatGPT share page did not contain a supported streamed conversation payload",
    )
