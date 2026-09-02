from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

COOKIE_NAME = "__Host-dbridge_ops"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padding = 4 - (len(s) % 4)
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s.encode("ascii"))


def create_session_cookie_value(
    session_secret: str,
    *,
    ttl_seconds: int = 43200,
    nonce: str | None = None,
    issued_at: int | None = None,
) -> str:
    now = int(time.time()) if issued_at is None else issued_at
    payload: dict[str, Any] = {
        "v": 1,
        "iat": now,
        "exp": now + ttl_seconds,
        "nonce": nonce if nonce is not None else secrets.token_hex(16),
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64url_encode(payload_json)
    signature = hmac.new(
        session_secret.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    sig_b64 = _b64url_encode(signature)
    return f"{payload_b64}.{sig_b64}"


def verify_session_cookie_value(cookie_value: str, session_secret: str) -> bool:
    if not isinstance(cookie_value, str) or not isinstance(session_secret, str):
        return False
    parts = cookie_value.split(".")
    if len(parts) != 2:
        return False
    payload_b64, sig_b64 = parts
    try:
        expected_sig = hmac.new(
            session_secret.encode("utf-8"),
            payload_b64.encode("ascii"),
            hashlib.sha256,
        ).digest()
        actual_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(actual_sig, expected_sig):
            return False
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
        if not isinstance(payload, dict):
            return False
        if payload.get("v") != 1:
            return False
        exp = payload.get("exp")
        iat = payload.get("iat")
        nonce = payload.get("nonce")
        if not isinstance(exp, (int, float)) or not isinstance(iat, (int, float)):
            return False
        if not isinstance(nonce, str) or len(nonce) < 8:
            return False
        now = time.time()
        if exp <= now:
            return False
        if iat > now + 60:
            return False
        return True
    except (ValueError, TypeError, binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
        return False


def resolve_client_ip(direct_host: str, forwarded_for: str | None) -> str:
    if direct_host in LOOPBACK_HOSTS and forwarded_for:
        client_part = forwarded_for.split(",")[0].strip()
        if client_part:
            return client_part
    return direct_host


class LoginRateLimiter:
    """In-memory rolling window rate limiter for login failures."""

    def __init__(self, max_attempts: int = 5, window_seconds: float = 600.0) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._failures_by_ip: dict[str, list[float]] = {}

    def _prune(self, ip: str, now: float) -> list[float]:
        cutoff = now - self.window_seconds
        attempts = [t for t in self._failures_by_ip.get(ip, []) if t > cutoff]
        if attempts:
            self._failures_by_ip[ip] = attempts
        else:
            self._failures_by_ip.pop(ip, None)
        return attempts

    def is_rate_limited(self, ip: str) -> bool:
        now = time.time()
        attempts = self._prune(ip, now)
        return len(attempts) >= self.max_attempts

    def record_failure(self, ip: str) -> None:
        now = time.time()
        attempts = self._prune(ip, now)
        attempts.append(now)
        self._failures_by_ip[ip] = attempts

    def record_success(self, ip: str) -> None:
        self._failures_by_ip.pop(ip, None)
