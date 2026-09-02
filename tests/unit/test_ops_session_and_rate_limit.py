import time
import pytest

from app.ops.session import (
    COOKIE_NAME,
    create_session_cookie_value,
    verify_session_cookie_value,
    LoginRateLimiter,
    resolve_client_ip,
)


def test_cookie_name():
    assert COOKIE_NAME == "__Host-dbridge_ops"


def test_create_and_verify_session_cookie():
    secret = "test-session-secret-key"
    token = create_session_cookie_value(secret, ttl_seconds=3600)
    assert "." in token
    assert verify_session_cookie_value(token, secret) is True


def test_verify_session_cookie_rejects_tampered_payload():
    secret = "test-session-secret-key"
    token = create_session_cookie_value(secret, ttl_seconds=3600)
    payload_b64, sig_b64 = token.split(".", 1)
    tampered_token = f"{payload_b64}a.{sig_b64}"
    assert verify_session_cookie_value(tampered_token, secret) is False


def test_verify_session_cookie_rejects_wrong_secret():
    secret1 = "secret-1"
    secret2 = "secret-2"
    token = create_session_cookie_value(secret1, ttl_seconds=3600)
    assert verify_session_cookie_value(token, secret2) is False


def test_verify_session_cookie_rejects_expired():
    secret = "test-session-secret-key"
    # ttl = -1 second
    token = create_session_cookie_value(secret, ttl_seconds=-1)
    assert verify_session_cookie_value(token, secret) is False


@pytest.mark.parametrize("invalid_token", [
    "",
    "not-a-token",
    "part1.part2.part3",
    "invalid_base64.signature",
    "e30.signature", # empty json {}
])
def test_verify_session_cookie_malformed(invalid_token):
    assert verify_session_cookie_value(invalid_token, "test-secret") is False


def test_resolve_client_ip_behind_loopback():
    # When direct peer is loopback, trust leftmost X-Forwarded-For
    assert resolve_client_ip("127.0.0.1", "203.0.113.195, 10.0.0.1") == "203.0.113.195"
    assert resolve_client_ip("::1", "198.51.100.4") == "198.51.100.4"
    assert resolve_client_ip("localhost", "198.51.100.5") == "198.51.100.5"


def test_resolve_client_ip_direct_non_loopback():
    # When direct peer is NOT loopback, ignore X-Forwarded-For
    assert resolve_client_ip("192.168.1.50", "203.0.113.195") == "192.168.1.50"
    assert resolve_client_ip("10.0.0.5", None) == "10.0.0.5"


def test_login_rate_limiter():
    limiter = LoginRateLimiter(max_attempts=5, window_seconds=600.0)
    ip = "203.0.113.10"

    assert limiter.is_rate_limited(ip) is False
    for _ in range(4):
        limiter.record_failure(ip)
        assert limiter.is_rate_limited(ip) is False

    limiter.record_failure(ip) # 5th attempt
    assert limiter.is_rate_limited(ip) is True

    # Another IP is unaffected
    assert limiter.is_rate_limited("203.0.113.20") is False

    # Successful login clears rate limit
    limiter.record_success(ip)
    assert limiter.is_rate_limited(ip) is False
