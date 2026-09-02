from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.api.errors import BridgeError, ErrorCode


class ChatGPTShareTransport(Protocol):
    def fetch(self, url: str) -> bytes: ...


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True, slots=True)
class UrllibChatGPTShareTransport:
    timeout_seconds: float = 15.0
    response_limit_bytes: int = 16 * 1024 * 1024

    def fetch(self, url: str) -> bytes:
        request = Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with build_opener(_NoRedirect()).open(request, timeout=self.timeout_seconds) as response:
                content_type = response.headers.get_content_type()
                if content_type not in {"text/html", "application/xhtml+xml"}:
                    raise BridgeError(
                        ErrorCode.CHATGPT_SHARE_UNSUPPORTED_FORMAT,
                        "ChatGPT share response was not HTML",
                        details={"content_type": content_type},
                    )
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > self.response_limit_bytes:
                    raise self._too_large()
                body = response.read(self.response_limit_bytes + 1)
                if len(body) > self.response_limit_bytes:
                    raise self._too_large()
                return body
        except BridgeError:
            raise
        except HTTPError as exc:
            raise BridgeError(
                ErrorCode.CHATGPT_SHARE_HTTP_ERROR,
                "ChatGPT share request returned an HTTP error",
                retryable=exc.code >= 500,
                details={"status": exc.code},
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise BridgeError(
                ErrorCode.CHATGPT_SHARE_FETCH_FAILED,
                "ChatGPT share request failed",
                retryable=True,
            ) from exc
        except ValueError as exc:
            raise BridgeError(
                ErrorCode.CHATGPT_SHARE_FETCH_FAILED,
                "ChatGPT share response had invalid headers",
            ) from exc

    def _too_large(self) -> BridgeError:
        return BridgeError(
            ErrorCode.CHATGPT_SHARE_TOO_LARGE,
            "ChatGPT share response exceeded the HTML safety limit",
            details={"limit_bytes": self.response_limit_bytes},
        )
