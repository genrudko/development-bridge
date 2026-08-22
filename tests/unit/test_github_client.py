from __future__ import annotations

import urllib.error

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.github import UrllibGitHubTransport


class Response:
    status = 200
    headers = {}

    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, limit=-1):
        return self.body[:limit] if limit >= 0 else self.body


class Opener:
    def __init__(self, result):
        self.result = result
        self.request = None

    def open(self, request, timeout):
        self.request = request
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.asyncio
async def test_github_transport_bounds_response_and_never_leaks_token(monkeypatch):
    oversized = Opener(Response(b"x" * 9))
    monkeypatch.setattr("urllib.request.build_opener", lambda *handlers: oversized)
    transport = UrllibGitHubTransport(
        "top-secret-token", timeout_seconds=1, response_limit_bytes=8
    )

    with pytest.raises(BridgeError) as raised:
        await transport.request("GET", "/user")
    assert raised.value.code is ErrorCode.GITHUB_API_ERROR
    assert "top-secret-token" not in str(raised.value)
    assert oversized.request.get_header("Authorization") == "Bearer top-secret-token"

    failed = Opener(urllib.error.URLError("top-secret-token timed out"))
    monkeypatch.setattr("urllib.request.build_opener", lambda *handlers: failed)
    with pytest.raises(BridgeError) as timeout:
        await transport.request("GET", "/user")
    assert timeout.value.retryable is True
    assert "top-secret-token" not in timeout.value.message
