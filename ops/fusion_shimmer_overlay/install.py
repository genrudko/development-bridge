"""Fail-closed installer for the pinned Shimmer Development Bridge overlay."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent


class OverlayInstallError(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_manifest() -> dict:
    return json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))


def _git_head(repo: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise OverlayInstallError("upstream repository HEAD is unavailable") from exc


def _patch_addin_ops_init(data: bytes) -> bytes:
    text = data.decode("utf-8")
    anchor = "    api,\n    assembly,\n"
    if anchor not in text:
        raise OverlayInstallError("addin registration anchor mismatch")
    return text.replace(anchor, "    api,\n    bridge_cad,\n    assembly,\n", 1).encode("utf-8")


def _patch_server_tools_init(data: bytes) -> bytes:
    text = data.decode("utf-8")
    import_anchor = "        api,\n        assembly,\n"
    register_anchor = "    # Read-only generic-API helpers (introspect/docs) are always available.\n    api.register(mcp, client)\n"
    if import_anchor not in text or register_anchor not in text:
        raise OverlayInstallError("server registration anchor mismatch")
    text = text.replace(
        import_anchor,
        "        api,\n        bridge_cad,\n        assembly,\n",
        1,
    )
    text = text.replace(
        register_anchor,
        "    bridge_cad.register(mcp, client)\n\n" + register_anchor,
        1,
    )
    return text.encode("utf-8")


def apply_overlay(repo, *, expected_upstream_sha=None, manifest=None):
    repo = Path(repo).resolve()
    spec = dict(manifest) if manifest is not None else _load_manifest()
    pinned_head = spec.get("upstream_sha")
    if not isinstance(pinned_head, str) or not pinned_head:
        raise OverlayInstallError("upstream SHA is missing from overlay manifest")
    if expected_upstream_sha is not None and expected_upstream_sha != pinned_head:
        raise OverlayInstallError("requested upstream SHA does not match pinned upstream manifest")
    required_head = pinned_head
    actual_head = _git_head(repo)
    if actual_head != required_head:
        raise OverlayInstallError(
            f"upstream SHA mismatch: expected {required_head}, found {actual_head}"
        )

    targets = spec.get("targets")
    if not isinstance(targets, dict) or not targets:
        raise OverlayInstallError("overlay target manifest is missing")

    # Validate every preimage before preparing or writing any output.
    preimages = {}
    for key, target in targets.items():
        if not isinstance(target, dict):
            raise OverlayInstallError("overlay target manifest is invalid")
        rel = target.get("path")
        expected_hash = target.get("sha256_before")
        if not isinstance(rel, str) or not isinstance(expected_hash, str):
            raise OverlayInstallError("overlay target manifest is invalid")
        path = repo / rel
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise OverlayInstallError(f"target preimage unavailable: {key}") from exc
        actual_hash = _sha256(data)
        if actual_hash != expected_hash:
            raise OverlayInstallError(
                f"target preimage hash mismatch for {key}: expected {expected_hash}, found {actual_hash}"
            )
        preimages[key] = (path, data)

    if "addin_ops_init" not in preimages or "server_tools_init" not in preimages:
        raise OverlayInstallError("overlay manifest lacks required registration targets")

    addin_init_path, addin_init_data = preimages["addin_ops_init"]
    server_init_path, server_init_data = preimages["server_tools_init"]
    prepared = {
        addin_init_path: _patch_addin_ops_init(addin_init_data),
        server_init_path: _patch_server_tools_init(server_init_data),
        repo / "addin/Fusion360MCP/fusion_mcp_addin/ops/bridge_cad.py": (HERE / "addin_bridge_cad.py").read_bytes(),
        repo / "server/fusion_mcp/tools/bridge_cad.py": (HERE / "server_bridge_cad.py").read_bytes(),
    }

    # All validation and patch preparation has succeeded; only now mutate files.
    originals = {
        path: (path.read_bytes() if path.exists() else None)
        for path in prepared
    }
    try:
        for path, data in prepared.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    except OSError as exc:
        rollback_errors = []
        for path, original in originals.items():
            try:
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(original)
            except OSError as rollback_exc:
                rollback_errors.append((path, rollback_exc))
        if rollback_errors:
            raise OverlayInstallError(
                "overlay write failed and rollback was incomplete"
            ) from exc
        raise OverlayInstallError(
            "overlay write failed; original layout restored"
        ) from exc

    return {
        "status": "installed",
        "upstream_sha": actual_head,
        "files": [str(path.relative_to(repo)) for path in prepared],
    }
