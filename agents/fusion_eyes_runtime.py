from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

EYES_NODE_ID = "fusion-eyes"
EYES_PROXY_HOST = "127.0.0.1"
EYES_PROXY_PORT = 18769
EYES_MCP_URL = "http://127.0.0.1:18769/mcp"
DEFAULT_BRIDGE_URL = "https://mcp.vigilante.website"


def build_eyes_process_specs(
    token: str,
    *,
    app_dir: Path,
    root: Path,
    relay_python: Path,
    environ: Mapping[str, str] | None = None,
    bridge_url: str = DEFAULT_BRIDGE_URL,
) -> tuple[dict[str, object], dict[str, object]] | None:
    """Describe the existing PERISCOPE proxy + unchanged Relay processes.

    Returns None when the already-installed runtime is incomplete.  Installation
    is intentionally a separate one-time operation; the normal GUI never mutates
    or upgrades the provider on Start.
    """
    server = app_dir / "periscope" / "server"
    scripts = server / ".venv" / "Scripts"
    periscope_python = scripts / "python.exe"
    proxy = scripts / "mcp-proxy.exe"
    agent = root / "windows_fusion_agent.py"
    required = (periscope_python, proxy, relay_python, agent)
    if not token or not all(path.is_file() for path in required):
        return None

    base_env = dict(os.environ if environ is None else environ)
    proxy_env = dict(base_env)
    proxy_env["PYTHONPATH"] = str(server)

    relay_env = dict(base_env)
    relay_env.update({
        "DEVELOPMENT_BRIDGE_URL": bridge_url,
        "DEVELOPMENT_BRIDGE_NODE_ID": EYES_NODE_ID,
        "DEVELOPMENT_BRIDGE_DESKTOP_NODE_TOKEN": token,
        "FUSION_MCP_URL": EYES_MCP_URL,
        "DEVELOPMENT_BRIDGE_FUSION_OUTBOX": str(app_dir / "eyes-outbox"),
        "PYTHONUNBUFFERED": "1",
    })

    proxy_spec: dict[str, object] = {
        "argv": [
            str(proxy),
            "--port", str(EYES_PROXY_PORT),
            "--host", EYES_PROXY_HOST,
            "--pass-environment",
            "--", str(periscope_python), "-m", "periscope_mcp",
        ],
        "cwd": str(server),
        "env": proxy_env,
    }
    relay_spec: dict[str, object] = {
        "argv": [str(relay_python), str(agent)],
        "cwd": str(root),
        "env": relay_env,
    }
    return proxy_spec, relay_spec
