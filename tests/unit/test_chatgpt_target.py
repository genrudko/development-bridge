from __future__ import annotations

import pytest

from app.api.errors import BridgeError
from app.coordinator.chatgpt_target import parse_chatgpt_target


def test_plain_conversation_normalizes_query_fragment_and_trailing_slash() -> None:
    target = parse_chatgpt_target(
        " https://chatgpt.com/c/6a96d2b0-2258-83ed-967c-cea1c441d0b9/?x=1#frag "
    )
    assert target.conversation_id == "6a96d2b0-2258-83ed-967c-cea1c441d0b9"
    assert target.route_url == "https://chatgpt.com/c/6a96d2b0-2258-83ed-967c-cea1c441d0b9"
    assert target.conversation_url == target.route_url
    assert target.project_id is None
    assert target.gpt_id is None
    assert target.slug is None


def test_project_conversation_without_slug_preserves_project_context() -> None:
    target = parse_chatgpt_target(
        "https://chatgpt.com/g/g-p-6a5e3143b89481919344560ff097cd0b/c/6a95bf09-1070-83eb-a0a0-b7d9e473a154"
    )
    assert target.project_id == "g-p-6a5e3143b89481919344560ff097cd0b"
    assert target.gpt_id is None
    assert target.slug is None
    assert target.conversation_url == "https://chatgpt.com/c/6a95bf09-1070-83eb-a0a0-b7d9e473a154"


def test_project_conversation_with_embedded_slug_keeps_full_route_context() -> None:
    target = parse_chatgpt_target(
        "https://chatgpt.com/g/g-p-6a5e3143b89481919344560ff097cd0b-plaginy-ad5x/c/6a95bf09-1070-83eb-a0a0-b7d9e473a154"
    )
    assert target.project_id == "g-p-6a5e3143b89481919344560ff097cd0b-plaginy-ad5x"
    assert target.slug is None
    assert target.route_url.endswith("/c/6a95bf09-1070-83eb-a0a0-b7d9e473a154")


def test_project_conversation_with_separate_slug_is_supported() -> None:
    target = parse_chatgpt_target(
        "https://chatgpt.com/g/g-p-6a5e3143b89481919344560ff097cd0b/plaginy-ad5x/c/6a95bf09-1070-83eb-a0a0-b7d9e473a154"
    )
    assert target.project_id == "g-p-6a5e3143b89481919344560ff097cd0b"
    assert target.slug == "plaginy-ad5x"


def test_custom_gpt_conversation_is_distinct_from_project_context() -> None:
    target = parse_chatgpt_target(
        "https://chatgpt.com/g/g-abc123-my-gpt/c/6a95bf09-1070-83eb-a0a0-b7d9e473a154"
    )
    assert target.project_id is None
    assert target.gpt_id == "g-abc123-my-gpt"


@pytest.mark.parametrize(
    "url",
    [
        "http://chatgpt.com/c/conv-a",
        "https://example.com/c/conv-a",
        "https://chatgpt.com:443/c/conv-a",
        "https://chatgpt.com/",
        "https://chatgpt.com/c/",
        "https://chatgpt.com/foo/c/conv-a",
        "https://chatgpt.com/c/conv-a/extra",
        "https://chatgpt.com/c/conv-a/c/conv-b",
        "https://chatgpt.com/g//c/conv-a",
        "https://chatgpt.com/g/g-p-project/slug/extra/c/conv-a",
    ],
)
def test_invalid_or_ambiguous_conversation_urls_fail_closed(url: str) -> None:
    with pytest.raises(BridgeError):
        parse_chatgpt_target(url)
