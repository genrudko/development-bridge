"""Local Cline authentication evidence.

Cline keeps its provider/account configuration locally. Development Bridge only
needs to know whether the account has local credential evidence, so this module
checks presence of provider/last-used markers and never returns or logs
credential material or account metadata.
"""

from __future__ import annotations

import json
from pathlib import Path

PROVIDERS_RELATIVE_PATH = Path("data") / "settings" / "providers.json"


def providers_path(config_directory: str | Path) -> Path:
    return Path(config_directory).expanduser() / PROVIDERS_RELATIVE_PATH


def load_configured_providers(config_directory: str | Path) -> tuple[str, ...]:
    """Return configured provider ids, or an empty tuple when evidence is absent.

    Handles both shapes Cline writes: a JSON array of provider ids and a dict
    keyed by provider id (the current account shape).
    """
    try:
        payload = json.loads(providers_path(config_directory).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    if not isinstance(payload, dict):
        return ()
    providers = payload.get("providers")
    if isinstance(providers, dict):
        return tuple(pid for pid in providers if isinstance(pid, str) and pid)
    if isinstance(providers, list):
        return tuple(item for item in providers if isinstance(item, str) and item)
    return ()


def local_auth_configured(
    config_directory: str | Path, provider: str = "cline-pass"
) -> bool:
    """Return local auth evidence for the configured Cline provider only.

    The probe never spends model quota and never returns credential material.
    A configured provider id or an exact last-used-provider marker is accepted;
    unrelated provider entries are not authentication evidence for this run.
    Missing or malformed configuration fails closed.
    """
    try:
        payload = json.loads(providers_path(config_directory).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(payload, dict) or not isinstance(provider, str) or not provider:
        return False
    providers = payload.get("providers")
    if isinstance(providers, dict) and provider in providers:
        return True
    if isinstance(providers, list) and provider in providers:
        return True
    return payload.get("lastUsedProvider") == provider
