from __future__ import annotations

import asyncio
import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse

from app.api.errors import BridgeError, ErrorCode


@dataclass(frozen=True, slots=True)
class GitHubResponse:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BridgeError(ErrorCode.GITHUB_API_ERROR, "GitHub returned invalid JSON") from exc


class GitHubTransport(Protocol):
    async def request(
        self, method: str, path: str, *, payload: dict | list | None = None
    ) -> GitHubResponse: ...

    async def download_to(self, path: str, destination: Path, max_bytes: int) -> tuple[int, str]: ...

    async def download_bytes(self, path: str, max_bytes: int) -> tuple[bytes, bool]: ...


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and urlparse(req.full_url).netloc != urlparse(newurl).netloc:
            redirected.remove_header("Authorization")
        return redirected


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UrllibGitHubTransport:
    def __init__(
        self, token: str, *, timeout_seconds: float, response_limit_bytes: int
    ) -> None:
        self._token = token
        self._timeout = timeout_seconds
        self._response_limit = response_limit_bytes
        self._base_url = "https://api.github.com/"

    async def request(
        self, method: str, path: str, *, payload: dict | list | None = None
    ) -> GitHubResponse:
        return await asyncio.to_thread(self._request, method, path, payload)

    def _request(self, method: str, path: str, payload: dict | list | None) -> GitHubResponse:
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            urljoin(self._base_url, path.lstrip("/")),
            data=data,
            method=method,
            headers=self._headers(),
        )
        opener = urllib.request.build_opener(_NoRedirect())
        try:
            with opener.open(request, timeout=self._timeout) as response:
                body = response.read(self._response_limit + 1)
                if len(body) > self._response_limit:
                    raise BridgeError(ErrorCode.GITHUB_API_ERROR, "GitHub response exceeded the safety limit")
                return GitHubResponse(response.status, dict(response.headers.items()), body)
        except urllib.error.HTTPError as error:
            body = error.read(self._response_limit + 1)
            return GitHubResponse(error.code, dict(error.headers.items()), body[:self._response_limit])
        except (TimeoutError, urllib.error.URLError) as exc:
            raise BridgeError(ErrorCode.GITHUB_API_ERROR, "GitHub request failed", retryable=True) from exc

    async def download_to(self, path: str, destination: Path, max_bytes: int) -> tuple[int, str]:
        return await asyncio.to_thread(self._download_to, path, destination, max_bytes)

    async def download_bytes(self, path: str, max_bytes: int) -> tuple[bytes, bool]:
        return await asyncio.to_thread(self._download_bytes, path, max_bytes)

    def _download_bytes(self, path: str, max_bytes: int) -> tuple[bytes, bool]:
        request = urllib.request.Request(
            urljoin(self._base_url, path.lstrip("/")), headers=self._headers()
        )
        opener = urllib.request.build_opener(_SafeRedirect())
        try:
            with opener.open(request, timeout=self._timeout) as response:
                body = response.read(max_bytes + 1)
        except urllib.error.HTTPError as exc:
            raise _http_error(exc.code, {}) from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            raise BridgeError(
                ErrorCode.GITHUB_API_ERROR,
                "GitHub download failed",
                retryable=True,
            ) from exc
        return body[:max_bytes], len(body) > max_bytes

    def _download_to(self, path: str, destination: Path, max_bytes: int) -> tuple[int, str]:
        request = urllib.request.Request(
            urljoin(self._base_url, path.lstrip("/")), headers=self._headers()
        )
        opener = urllib.request.build_opener(_SafeRedirect())
        digest = hashlib.sha256()
        size = 0
        try:
            with opener.open(request, timeout=self._timeout) as response, destination.open("xb") as output:
                while chunk := response.read(64 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise BridgeError(ErrorCode.GITHUB_API_ERROR, "GitHub artifact exceeded the size limit")
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        except urllib.error.HTTPError as exc:
            raise _http_error(exc.code, {}) from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            raise BridgeError(ErrorCode.GITHUB_API_ERROR, "GitHub artifact download failed", retryable=True) from exc
        return size, "sha256:" + digest.hexdigest()

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "development-bridge",
            "Content-Type": "application/json",
        }


def _http_error(status: int, headers: dict[str, str]) -> BridgeError:
    remaining = headers.get("x-ratelimit-remaining") or headers.get("X-RateLimit-Remaining")
    if status == 429 or status == 403 and remaining == "0":
        return BridgeError(ErrorCode.GITHUB_RATE_LIMITED, "GitHub API rate limit exceeded", retryable=True)
    if status in {409, 422}:
        return BridgeError(ErrorCode.GITHUB_CONFLICT, "GitHub rejected the requested state change")
    if status == 404:
        return BridgeError(ErrorCode.GITHUB_REPOSITORY_UNAVAILABLE, "GitHub resource is unavailable")
    if status in {401, 403}:
        return BridgeError(ErrorCode.PERMISSION_DENIED, "GitHub denied the operation")
    return BridgeError(ErrorCode.GITHUB_API_ERROR, "GitHub API request failed", retryable=status >= 500)
