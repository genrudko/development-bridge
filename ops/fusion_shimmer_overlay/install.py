"""Fail-closed installer for the pinned Shimmer Development Bridge overlay."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
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


def _upstream_revision(repo: Path, pinned: str, targets: dict) -> str:
    """Resolve a strict git checkout or the exact GitHub archive extraction."""
    if (repo / ".git").exists():
        return _git_head(repo)
    if (repo.name != f"self-host-fusion360-MCP-{pinned}"
            or repo.parent.name != f"extract-{pinned}"):
        raise OverlayInstallError("pinned archive path provenance mismatch")
    for key, target in targets.items():
        try:
            data = (repo / target["path"]).read_bytes()
            expected = target["sha256_before"]
        except (KeyError, OSError, TypeError) as exc:
            raise OverlayInstallError(f"archive source preimage unavailable: {key}") from exc
        if _sha256(data) != expected:
            raise OverlayInstallError(f"archive source preimage hash mismatch for {key}")
    return pinned


def _target_paths(repo: Path, targets: dict, runtime_paths) -> dict[str, Path]:
    if runtime_paths is None:
        return {key: repo / target["path"] for key, target in targets.items()}
    paths = {key: Path(path).resolve() for key, path in runtime_paths.items()}
    if set(paths) != set(targets):
        raise OverlayInstallError("explicit runtime targets do not match manifest")
    return paths


def _overlay_sources(source: Path, spec: dict) -> tuple[bytes, bytes]:
    try:
        addin = (source / "addin_bridge_cad.py").read_bytes()
        server = (source / "server_bridge_cad.py").read_bytes()
    except OSError as exc:
        raise OverlayInstallError("overlay source unavailable") from exc
    hashes = spec.get("overlay_sha256")
    if hashes is not None:
        expected = {
            "addin_bridge_cad.py": _sha256(addin),
            "server_bridge_cad.py": _sha256(server),
        }
        if not isinstance(hashes, dict) or any(hashes.get(name) != digest for name, digest in expected.items()):
            raise OverlayInstallError("overlay source hash mismatch")
    return addin, server


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


def inspect_overlay(repo, *, expected_upstream_sha=None, manifest=None, overlay_dir=None,
                    runtime_paths=None):
    """Classify the guarded overlay without changing the Shimmer tree."""
    repo = Path(repo).resolve()
    source = HERE if overlay_dir is None else Path(overlay_dir).resolve()
    spec = dict(manifest) if manifest is not None else json.loads(
        (source / "manifest.json").read_text(encoding="utf-8")
    )
    pinned = spec.get("upstream_sha")
    if expected_upstream_sha is not None and expected_upstream_sha != pinned:
        return {"state": "mismatch", "detail": "requested revision differs from manifest"}
    if not repo.is_dir():
        return {"state": "missing", "detail": "Shimmer runtime is not installed"}
    targets = spec.get("targets")
    if not isinstance(targets, dict) or not targets:
        return {"state": "mismatch", "detail": "overlay target manifest is missing"}
    try:
        actual = _upstream_revision(repo, pinned, targets)
        if actual != pinned:
            return {"state": "mismatch", "detail": f"upstream revision mismatch: {actual}"}
        paths = _target_paths(repo, targets, runtime_paths)
        addin_target = targets["addin_ops_init"]
        server_target = targets["server_tools_init"]
        addin_path = paths["addin_ops_init"]
        server_path = paths["server_tools_init"]
        addin_data = addin_path.read_bytes()
        server_data = server_path.read_bytes()
        addin_source, server_source = _overlay_sources(source, spec)
    except (KeyError, OSError, TypeError, OverlayInstallError) as exc:
        return {"state": "mismatch", "detail": f"overlay input unavailable: {exc}"}
    preimage = (
        _sha256(addin_data) == addin_target.get("sha256_before")
        and _sha256(server_data) == server_target.get("sha256_before")
    )
    try:
        expected_addin = _patch_addin_ops_init(addin_data) if preimage else None
        expected_server = _patch_server_tools_init(server_data) if preimage else None
    except OverlayInstallError:
        expected_addin = expected_server = None
    overlay_files = (addin_path.parent / "bridge_cad.py", server_path.parent / "bridge_cad.py")
    if preimage and not any(path.exists() for path in overlay_files):
        return {"state": "unapplied", "detail": "qualified overlay is not applied"}
    if not preimage:
        # Reconstruct qualified postimages by removing only our exact anchors.
        addin_before = addin_data.replace(b"    api,\n    bridge_cad,\n    assembly,\n", b"    api,\n    assembly,\n", 1)
        server_before = server_data.replace(b"        api,\n        bridge_cad,\n        assembly,\n", b"        api,\n        assembly,\n", 1).replace(
            b"    bridge_cad.register(mcp, client)\n\n    # Read-only generic-API helpers",
            b"    # Read-only generic-API helpers", 1,
        )
        if (_sha256(addin_before) == addin_target.get("sha256_before")
                and _sha256(server_before) == server_target.get("sha256_before")):
            expected_addin, expected_server = addin_data, server_data
    applied = (
        expected_addin == addin_data and expected_server == server_data
        and overlay_files[0].is_file() and overlay_files[0].read_bytes() == addin_source
        and overlay_files[1].is_file() and overlay_files[1].read_bytes() == server_source
    )
    if applied:
        return {"state": "applied", "detail": "qualified overlay is applied"}
    return {"state": "mismatch", "detail": "live/source overlay hash mismatch"}


def apply_overlay(repo, *, expected_upstream_sha=None, manifest=None, overlay_dir=None,
                  runtime_paths=None):
    repo = Path(repo).resolve()
    source = HERE if overlay_dir is None else Path(overlay_dir).resolve()
    spec = dict(manifest) if manifest is not None else json.loads(
        (source / "manifest.json").read_text(encoding="utf-8")
    )
    pinned_head = spec.get("upstream_sha")
    if not isinstance(pinned_head, str) or not pinned_head:
        raise OverlayInstallError("upstream SHA is missing from overlay manifest")
    if expected_upstream_sha is not None and expected_upstream_sha != pinned_head:
        raise OverlayInstallError("requested upstream SHA does not match pinned upstream manifest")
    targets = spec.get("targets")
    if not isinstance(targets, dict) or not targets:
        raise OverlayInstallError("overlay target manifest is missing")

    actual_head = _upstream_revision(repo, pinned_head, targets)
    if actual_head != pinned_head:
        raise OverlayInstallError(
            f"upstream SHA mismatch: expected {pinned_head}, found {actual_head}"
        )
    paths = _target_paths(repo, targets, runtime_paths)

    # Validate every installed preimage before preparing or writing any output.
    preimages = {}
    for key, target in targets.items():
        if not isinstance(target, dict):
            raise OverlayInstallError("overlay target manifest is invalid")
        rel = target.get("path")
        expected_hash = target.get("sha256_before")
        if not isinstance(rel, str) or not isinstance(expected_hash, str):
            raise OverlayInstallError("overlay target manifest is invalid")
        path = paths[key]
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
    addin_overlay, server_overlay = _overlay_sources(source, spec)
    prepared = {
        addin_init_path: _patch_addin_ops_init(addin_init_data),
        server_init_path: _patch_server_tools_init(server_init_data),
        addin_init_path.parent / "bridge_cad.py": addin_overlay,
        server_init_path.parent / "bridge_cad.py": server_overlay,
    }

    # All validation and patch preparation has succeeded; only now mutate files.
    originals = {
        path: (path.read_bytes() if path.exists() else None)
        for path in prepared
    }
    temporary = {}
    try:
        for path, data in prepared.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
            with open(descriptor, "wb", closefd=True) as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            temporary[path] = Path(name)
        for path in prepared:
            temporary[path].replace(path)
    except OSError as exc:
        for temp_path in temporary.values():
            temp_path.unlink(missing_ok=True)
        rollback_errors = []
        for path, original in originals.items():
            try:
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    descriptor, name = tempfile.mkstemp(prefix=path.name + ".rollback.", suffix=".tmp", dir=path.parent)
                    with open(descriptor, "wb", closefd=True) as handle:
                        handle.write(original)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(name, path)
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
        "files": [str(path) for path in prepared],
    }
