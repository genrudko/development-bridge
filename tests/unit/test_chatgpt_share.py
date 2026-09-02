from __future__ import annotations

import json
from itertools import pairwise

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.chatgpt_share.parser import parse_share_html
from app.chatgpt_share.service import ChatGPTShareService, validate_share_url

URL = "https://chatgpt.com/share/6a8aebc8-f5a8-83eb-bf0e-ea813861a2b1"


class FakeTransport:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.urls: list[str] = []

    def fetch(self, url: str) -> bytes:
        self.urls.append(url)
        return self.body


def _flatten(value):
    table = []

    def add(item):
        index = len(table)
        table.append(None)
        if isinstance(item, dict):
            table[index] = {f"_{add(key)}": add(child) for key, child in item.items()}
        elif isinstance(item, list):
            table[index] = [add(child) for child in item]
        else:
            table[index] = item
        return index

    add(value)
    return table


def _html(payload: dict) -> bytes:
    framed = "data:" + json.dumps(_flatten({"loaderData": {"serverResponse": {"data": payload}}})) + "\n"
    encoded = json.dumps(framed)
    return (
        "<html><script>irrelevant()</script><script>"
        f"window.__reactRouterContext.streamController.enqueue({encoded});"
        "</script></html>"
    ).encode()


def _split_html(payload: dict, split_at: tuple[int, ...]) -> bytes:
    framed = "data:" + json.dumps(
        _flatten({"loaderData": {"serverResponse": {"data": payload}}})
    ) + "\n"
    boundaries = (0, *split_at, len(framed))
    calls = "".join(
        "window.__reactRouterContext.streamController.enqueue("
        f"{json.dumps(framed[start:end])});"
        for start, end in pairwise(boundaries)
    )
    return f"<html><script>irrelevant()</script><script>{calls}</script></html>".encode()


def _message(
    identifier, role, parts, *, hidden=False, redacted=False,
    thinking_preamble=False, content_type="text",
):
    return {
        "id": identifier,
        "author": {"role": role},
        "content": {"content_type": content_type, "parts": parts},
        "create_time": 1.0,
        "metadata": {
            "is_visually_hidden_from_conversation": hidden,
            "is_redacted": redacted,
            "is_thinking_preamble_message": thinking_preamble,
        },
    }


def _payload() -> dict:
    return {
        "title": "A shared chat",
        "sharedConversationId": "share-id",
        "conversation_id": "conversation-id",
        "backing_conversation_id": "backing-id",
        "linear_conversation": [
            {"message": _message("s", "system", ["secret"])},
            {"message": _message("u1", "user", ["Hello", {"content_type": "image_asset_pointer"}, {"type": "text", "text": "caption"}])},
            {"message": _message("a-hidden", "assistant", ["hidden"], hidden=True)},
            {"message": _message("preamble", "assistant", ["internal preamble"], thinking_preamble=True)},
            {"message": _message("tool", "tool", ["tool output"])},
            {"message": _message("r", "assistant", ["chain"], content_type="reasoning")},
            {"message": _message("code", "assistant", ["internal code"], content_type="code")},
            {"message": _message("redacted", "assistant", ["old branch"], redacted=True)},
            {"message": _message("a1", "assistant", ["World"])},
            {"message": _message("empty", "assistant", ["  "])},
            {"message": _message("u2", "user", ["Find Needle here"])},
        ],
    }


@pytest.mark.parametrize("url", [
    "http://chatgpt.com/share/id", "https://example.com/share/id",
    "https://chatgpt.com.evil/share/id", "https://chatgpt.com/share/id/extra",
    "https://chatgpt.com/share/id?q=1", "https://user@chatgpt.com/share/id",
])
def test_url_validation_rejects_noncanonical_urls(url):
    with pytest.raises(BridgeError) as error:
        validate_share_url(url)
    assert error.value.code is ErrorCode.INVALID_ARGUMENT


def test_url_validation_accepts_optional_trailing_slash():
    assert validate_share_url(URL + "/") == URL.rsplit("/", 1)[1]


def test_parser_decodes_stream_reference_table():
    parsed = parse_share_html(_html(_payload()))
    assert parsed["sharedConversationId"] == "share-id"
    assert parsed["linear_conversation"][1]["message"]["author"]["role"] == "user"


def test_parser_reassembles_reference_table_record_split_across_enqueues():
    body = _split_html(_payload(), (17, 83))
    parsed = parse_share_html(body)
    assert parsed["sharedConversationId"] == "share-id"
    assert parsed["linear_conversation"][8]["message"]["id"] == "a1"


@pytest.mark.asyncio
async def test_filtering_and_order_and_recent():
    service = ChatGPTShareService(FakeTransport(_html(_payload())))
    result = await service.read(URL, mode="recent", limit=2)
    assert [(item["role"], item["text"]) for item in result["messages"]] == [
        ("assistant", "World"), ("user", "Find Needle here")
    ]
    assert result["total_visible_count"] == 3
    assert result["user_count"] == 2
    assert result["assistant_count"] == 1
    assert result["truncated"] is True
    assert result["backing_conversation_id"] == "backing-id"
    assert [item["index"] for item in result["messages"]] == [1, 2]


@pytest.mark.asyncio
async def test_search_is_case_insensitive_and_bounded():
    payload = _payload()
    payload["linear_conversation"].append({"message": _message("a2", "assistant", ["another needle"])})
    service = ChatGPTShareService(FakeTransport(_html(payload)))
    result = await service.read(URL, mode="search", query="NEEDLE", max_matches=1)
    assert result["total_match_count"] == 2
    assert result["returned_count"] == 1
    assert result["truncated"] is True
    assert result["messages"][0]["index"] == 2


@pytest.mark.asyncio
async def test_full_response_is_truncated_at_byte_cap():
    payload = _payload()
    payload["linear_conversation"] = [
        {"message": _message(str(index), "user", ["x" * 100])} for index in range(10)
    ]
    service = ChatGPTShareService(FakeTransport(_html(payload)), response_limit_bytes=700)
    result = await service.read(URL, mode="full")
    assert result["truncated"] is True
    assert 0 < result["returned_count"] < result["total_visible_count"]
    assert result["selected_count"] == result["returned_count"]
    assert len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()) <= 700


@pytest.mark.asyncio
async def test_search_requires_query():
    service = ChatGPTShareService(FakeTransport(_html(_payload())))
    with pytest.raises(BridgeError) as error:
        await service.read(URL, mode="search")
    assert error.value.code is ErrorCode.INVALID_ARGUMENT


def test_malformed_page_has_specific_error():
    with pytest.raises(BridgeError) as error:
        parse_share_html(b"<html><script>nothing useful</script></html>")
    assert error.value.code is ErrorCode.CHATGPT_SHARE_UNSUPPORTED_FORMAT
