from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any

BRIDGE_CAD_RESULT_PREFIX = "BRIDGE_CAD_RESULT_V1:"
BRIDGE_CAD_TRANSPORT_MODE = "fusion_mcp_exception_v1"
_TOKEN = re.compile(r"^[A-Za-z0-9_-]+$")


def extract_bridge_cad_result(value: Any) -> dict[str, Any] | None:
    """Decode the strict Bridge CAD result tunneled through Fusion MCP errors.

    Current Autodesk Fusion MCP executes Python but drops stdout/return values.
    It does preserve an uncaught exception traceback. Bridge-owned CAD scripts use
    exactly one reserved RuntimeError line containing a base64url fusion.cad/v1
    object. Everything else remains an ordinary native failure.
    """
    if not isinstance(value, dict):
        return None
    content = value.get("content")
    if not isinstance(content, list):
        return None
    line_prefix = "RuntimeError: " + BRIDGE_CAD_RESULT_PREFIX
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        text = block.get("text")
        if not isinstance(text, str) or not text:
            continue
        try:
            envelope = json.loads(text)
        except (TypeError, ValueError):
            continue
        if not isinstance(envelope, dict) or envelope.get("success") is not False:
            continue
        error_text = envelope.get("error")
        if not isinstance(error_text, str):
            continue
        lines = error_text.rstrip().splitlines()
        if not lines or not lines[-1].startswith(line_prefix):
            continue
        token = lines[-1][len(line_prefix):]
        if not token or len(token) > 64 * 1024 * 1024 or _TOKEN.fullmatch(token) is None:
            continue
        try:
            raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
            payload = json.loads(raw.decode("utf-8"))
        except (binascii.Error, UnicodeDecodeError, ValueError, TypeError):
            continue
        if not isinstance(payload, dict) or payload.get("api_version") != "fusion.cad/v1":
            continue
        return payload
    return None
