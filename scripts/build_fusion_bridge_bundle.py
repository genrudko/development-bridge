#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = {
    "START_FUSION_GUI.cmd": ROOT / "agents/START_FUSION_GUI.cmd",
    "START_FUSION_GUI.ps1": ROOT / "agents/START_FUSION_GUI.ps1",
    "START_FUSION_AGENT.ps1": ROOT / "agents/START_FUSION_AGENT.ps1",
    "fusion_relay_gui.pyw": ROOT / "agents/fusion_relay_gui.pyw",
    "fusion_hands_runtime.py": ROOT / "agents/fusion_hands_runtime.py",
    "fusion_eyes_runtime.py": ROOT / "agents/fusion_eyes_runtime.py",
    "windows_fusion_agent.py": ROOT / "agents/windows_fusion_agent.py",
    "INSTALL_FUSION_EYES.ps1": ROOT / "agents/INSTALL_FUSION_EYES.ps1",
    "INSTALL_FUSION_HANDS.ps1": ROOT / "agents/INSTALL_FUSION_HANDS.ps1",
    "periscope-lost-event.patch": ROOT / "agents/periscope-lost-event.patch",
    "FUSION_GUI_README.txt": ROOT / "agents/FUSION_GUI_README.txt",
    "fusion_shimmer_overlay/README.md": ROOT / "ops/fusion_shimmer_overlay/README.md",
    "fusion_shimmer_overlay/install.py": ROOT / "ops/fusion_shimmer_overlay/install.py",
    "fusion_shimmer_overlay/manifest.json": ROOT / "ops/fusion_shimmer_overlay/manifest.json",
    "fusion_shimmer_overlay/addin_bridge_cad.py": ROOT / "ops/fusion_shimmer_overlay/addin_bridge_cad.py",
    "fusion_shimmer_overlay/server_bridge_cad.py": ROOT / "ops/fusion_shimmer_overlay/server_bridge_cad.py",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def write_bytes(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the curated Fusion Bridge Windows bundle")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()

    head = git("rev-parse", "HEAD")
    dirty = bool(git("status", "--porcelain", "--untracked-files=all"))
    if dirty and not args.allow_dirty:
        parser.error("working tree is dirty; commit/clean it before creating a release bundle")
    missing = [str(path) for path in ASSETS.values() if not path.is_file()]
    if missing:
        parser.error("missing bundle assets: " + ", ".join(missing))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"FusionBridge-Unified-{head[:7]}.zip"
    output = args.output_dir / archive_name
    build = {
        "format_version": 1,
        "source_commit": head,
        "archive_name": archive_name,
        "dirty": dirty,
        "asset_count": len(ASSETS),
    }
    with zipfile.ZipFile(output, "w") as archive:
        for name in sorted(ASSETS):
            write_bytes(archive, name, ASSETS[name].read_bytes())
        write_bytes(archive, "FUSION_BRIDGE_BUILD.json", (json.dumps(build, sort_keys=True, indent=2) + "\n").encode())
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
