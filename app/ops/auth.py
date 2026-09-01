from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets


def hash_password(
    password: str,
    *,
    n: int = 16384,
    r: int = 8,
    p: int = 1,
    salt: bytes | None = None,
) -> str:
    salt_bytes = salt if salt is not None else secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt_bytes,
        n=n,
        r=r,
        p=p,
        maxmem=64 * 1024 * 1024,
    )
    salt_b64 = base64.b64encode(salt_bytes).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    return f"scrypt${n}${r}${p}${salt_b64}${digest_b64}"


def verify_password(password: str, stored_hash: str) -> bool:
    if not isinstance(stored_hash, str) or not isinstance(password, str):
        return False
    parts = stored_hash.split("$")
    if len(parts) != 6:
        return False
    algorithm, n_str, r_str, p_str, salt_b64, digest_b64 = parts
    if algorithm != "scrypt":
        return False
    try:
        n = int(n_str)
        r = int(r_str)
        p = int(p_str)
        if n <= 1 or (n & (n - 1)) != 0 or r < 1 or p < 1:
            return False
        salt = base64.b64decode(salt_b64, validate=True)
        expected_digest = base64.b64decode(digest_b64, validate=True)
        if not salt or not expected_digest:
            return False
        computed_digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            maxmem=64 * 1024 * 1024,
            dklen=len(expected_digest),
        )
        return hmac.compare_digest(computed_digest, expected_digest)
    except (ValueError, TypeError, binascii.Error):
        return False
