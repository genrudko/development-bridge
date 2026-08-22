from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.github import GitHubResponse


class FakeGitHubTransport:
    def __init__(self) -> None:
        self.responses: dict[tuple[str, str], list[GitHubResponse]] = {}
        self.calls: list[tuple[str, str, object]] = []
        self.downloads: dict[str, bytes] = {}
        self.download_calls: list[str] = []

    def add(self, method: str, path: str, payload, status: int = 200, headers=None):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.responses.setdefault((method, path), []).append(
            GitHubResponse(status, headers or {}, body)
        )

    async def request(self, method: str, path: str, *, payload=None):
        self.calls.append((method, path, payload))
        responses = self.responses.get((method, path))
        if not responses:
            raise AssertionError(f"Unexpected GitHub request: {method} {path}")
        return responses.pop(0)

    async def download_to(self, path: str, destination: Path, max_bytes: int):
        self.download_calls.append(path)
        content = self.downloads[path]
        if len(content) > max_bytes:
            raise AssertionError("test artifact exceeds limit")
        destination.write_bytes(content)
        return len(content), "sha256:" + hashlib.sha256(content).hexdigest()

    async def download_bytes(self, path: str, max_bytes: int):
        content = self.downloads[path]
        return content[:max_bytes], len(content) > max_bytes
