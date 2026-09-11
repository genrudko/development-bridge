"""Pinned local Shimmer process and guarded-overlay contract for Fusion Hands."""

from __future__ import annotations

import importlib.util
import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

SHIMMER_UPSTREAM_SHA = "97a06e76c289420a721590ddcab334f5f3dc3178"
HANDS_NODE_ID = "fusion-hands"
HANDS_MCP_HOST = "127.0.0.1"
HANDS_MCP_PORT = 18768
HANDS_MCP_URL = "http://127.0.0.1:18768/mcp"
SHIMMER_ADDIN_PORT = 9000
SHIMMER_ADDIN_URL = "http://127.0.0.1:9000"
ADDIN_API_TIMEOUT = 0.65
REQUIRED_BRIDGE_OPS = frozenset({"bridge.cad_guard", "bridge.cad_apply"})
DEFAULT_BRIDGE_URL = "https://mcp.vigilante.website"


@dataclass(frozen=True)
class HandsOverlayState:
    state: str
    detail: str


@dataclass(frozen=True)
class HandsAddinState:
    ready: bool
    detail: str


def _default_token_file(environ: Mapping[str, str] | None = None) -> Path:
    values = os.environ if environ is None else environ
    profile = values.get("USERPROFILE")
    return (Path(profile) if profile else Path.home()) / ".fusion-mcp" / "token"


def _read_local_token(token_file: Path) -> str | None:
    try:
        token = token_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return token or None


def _operation_names(value: object) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        names: set[str] = set()
        for item in value:
            names.update(_operation_names(item))
        return names
    if isinstance(value, dict):
        names = set()
        for key, item in value.items():
            if key in {"name", "op", "operation"} and isinstance(item, str):
                names.add(item)
            else:
                names.update(_operation_names(item))
        return names
    return set()


def _addin_request(
    method: str, path: str, *, token_file: Path, opener, payload: object | None = None,
) -> object:
    token = _read_local_token(token_file)
    if token is None:
        raise RuntimeError("local add-in auth unavailable")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        SHIMMER_ADDIN_URL + path,
        data=data,
        method=method,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    with opener(request, timeout=ADDIN_API_TIMEOUT) as response:
        body = response.read()
    return json.loads(body.decode("utf-8"))


def probe_hands_addin_ops(
    *, token_file: Path | None = None, opener=urllib.request.urlopen,
) -> HandsAddinState:
    try:
        result = _addin_request("GET", "/ops", token_file=token_file or _default_token_file(), opener=opener)
        missing = REQUIRED_BRIDGE_OPS - _operation_names(result)
        if missing:
            return HandsAddinState(False, "required Bridge operations are not loaded")
        return HandsAddinState(True, "required Bridge operations are loaded")
    except RuntimeError:
        return HandsAddinState(False, "local add-in auth unavailable")
    except Exception as exc:
        return HandsAddinState(False, f"add-in readiness failed: {type(exc).__name__}")


def reload_hands_addin_ops(
    *, token_file: Path | None = None, opener=urllib.request.urlopen,
) -> HandsAddinState:
    try:
        _addin_request(
            "POST", "/rpc", token_file=token_file or _default_token_file(), opener=opener,
            payload={"op": "system.reload", "params": {}},
        )
        return HandsAddinState(True, "add-in operation reload requested")
    except Exception as exc:
        return HandsAddinState(False, f"add-in reload failed: {type(exc).__name__}")


def _default_overlay_dir() -> Path:
    bundled = Path(__file__).resolve().parent / "fusion_shimmer_overlay"
    return bundled if bundled.is_dir() else Path(__file__).resolve().parents[1] / "ops" / "fusion_shimmer_overlay"


def _installer(overlay_dir: Path):
    path = overlay_dir / "install.py"
    spec = importlib.util.spec_from_file_location("development_bridge_shimmer_overlay", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"overlay installer unavailable: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def hands_runtime_paths(app_dir: Path, *, environ: Mapping[str, str]) -> dict[str, Path]:
    appdata = environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is unavailable")
    sidecar = Path(app_dir) / "shimmer-sidecar"
    source = sidecar / f"extract-{SHIMMER_UPSTREAM_SHA}" / f"self-host-fusion360-MCP-{SHIMMER_UPSTREAM_SHA}"
    return {
        "sidecar": sidecar,
        "source": source,
        "executable": sidecar / "venv" / "Scripts" / "fusion-mcp.exe",
        "addin_ops_init": Path(appdata) / "Autodesk" / "Autodesk Fusion 360" / "API" / "AddIns" / "Fusion360MCP" / "fusion_mcp_addin" / "ops" / "__init__.py",
        "server_tools_init": sidecar / "venv" / "Lib" / "site-packages" / "fusion_mcp" / "tools" / "__init__.py",
    }


def inspect_hands_overlay(app_dir: Path, *, environ: Mapping[str, str], overlay_dir: Path | None = None) -> HandsOverlayState:
    source = _default_overlay_dir() if overlay_dir is None else Path(overlay_dir)
    try:
        paths = hands_runtime_paths(app_dir, environ=environ)
        result = _installer(_default_overlay_dir()).inspect_overlay(
            paths["source"], expected_upstream_sha=SHIMMER_UPSTREAM_SHA,
            overlay_dir=source,
            runtime_paths={key: paths[key] for key in ("addin_ops_init", "server_tools_init")},
        )
        return HandsOverlayState(result["state"], result["detail"])
    except Exception as exc:
        return HandsOverlayState("mismatch", f"overlay inspection failed: {exc}")


def ensure_hands_overlay(app_dir: Path, *, environ: Mapping[str, str], overlay_dir: Path | None = None) -> HandsOverlayState:
    """Apply only a qualified preimage; an applied overlay is a no-op."""
    source = _default_overlay_dir() if overlay_dir is None else Path(overlay_dir)
    before = inspect_hands_overlay(app_dir, environ=environ, overlay_dir=source)
    if before.state in {"missing", "mismatch", "applied"}:
        return before
    try:
        installer = _installer(_default_overlay_dir())
        paths = hands_runtime_paths(app_dir, environ=environ)
        installer.apply_overlay(
            paths["source"], expected_upstream_sha=SHIMMER_UPSTREAM_SHA,
            overlay_dir=source,
            runtime_paths={key: paths[key] for key in ("addin_ops_init", "server_tools_init")},
        )
    except Exception as exc:
        return HandsOverlayState("mismatch", f"overlay apply failed: {exc}")
    return inspect_hands_overlay(app_dir, environ=environ, overlay_dir=source)


def build_hands_process_specs(
    token: str, *, app_dir: Path, root: Path, relay_python: Path,
    environ: Mapping[str, str] | None = None, bridge_url: str = DEFAULT_BRIDGE_URL,
) -> tuple[dict[str, object], dict[str, object]] | None:
    base = dict(os.environ if environ is None else environ)
    try:
        paths = hands_runtime_paths(app_dir, environ=base)
    except RuntimeError:
        return None
    executable = paths["executable"]
    agent = root / "windows_fusion_agent.py"
    if not token or not all(path.is_file() for path in (executable, relay_python, agent)):
        return None
    sidecar_env = dict(base)
    sidecar_env.update({"PYTHONUNBUFFERED": "1"})
    relay_env = dict(base)
    relay_env.update({
        "DEVELOPMENT_BRIDGE_URL": bridge_url,
        "DEVELOPMENT_BRIDGE_NODE_ID": HANDS_NODE_ID,
        "DEVELOPMENT_BRIDGE_DESKTOP_NODE_TOKEN": token,
        "FUSION_MCP_URL": HANDS_MCP_URL,
        "DEVELOPMENT_BRIDGE_FUSION_OUTBOX": str(app_dir / "hands-outbox"),
        "PYTHONUNBUFFERED": "1",
    })
    return (
        {"argv": [str(executable), "run", "--transport", "http", "--host", HANDS_MCP_HOST, "--port", str(HANDS_MCP_PORT), "--addin-url", SHIMMER_ADDIN_URL], "cwd": str(paths["sidecar"]), "env": sidecar_env},
        {"argv": [str(relay_python), str(agent)], "cwd": str(root), "env": relay_env},
    )
