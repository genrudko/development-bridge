from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "build_fusion_bridge_bundle.py"


def test_bundle_builder_emits_sha_named_self_describing_curated_zip(tmp_path):
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(tmp_path), "--allow-dirty"],
        cwd=ROOT, check=True, text=True,
    )
    archives = list(tmp_path.glob("FusionBridge-Unified-*.zip"))
    assert [path.name for path in archives] == [f"FusionBridge-Unified-{head[:7]}.zip"]
    with zipfile.ZipFile(archives[0]) as archive:
        names = set(archive.namelist())
        required = {
            "START_FUSION_GUI.cmd", "START_FUSION_GUI.ps1", "START_FUSION_AGENT.ps1",
            "fusion_relay_gui.pyw", "fusion_hands_runtime.py", "fusion_eyes_runtime.py",
            "windows_fusion_agent.py", "INSTALL_FUSION_EYES.ps1", "INSTALL_FUSION_HANDS.ps1",
            "periscope-lost-event.patch", "FUSION_GUI_README.txt",
            "fusion_shimmer_overlay/install.py", "fusion_shimmer_overlay/manifest.json",
            "fusion_shimmer_overlay/addin_bridge_cad.py", "fusion_shimmer_overlay/server_bridge_cad.py",
            "FUSION_BRIDGE_BUILD.json",
        }
        assert required <= names
        manifest = json.loads(archive.read("FUSION_BRIDGE_BUILD.json"))
    assert manifest["source_commit"] == head
    assert manifest["archive_name"] == archives[0].name
    expected_dirty = bool(subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True
    ).strip())
    assert manifest["dirty"] is expected_dirty
    assert manifest["format_version"] == 1


def test_bundle_builder_refuses_dirty_release_without_explicit_override(tmp_path):
    dirty_probe = ROOT / ".bundle-builder-dirty-probe"
    dirty_probe.write_text("dirty\n", encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--output-dir", str(tmp_path)],
            cwd=ROOT, text=True, capture_output=True,
        )
    finally:
        dirty_probe.unlink(missing_ok=True)
    assert result.returncode != 0
    assert "working tree is dirty" in (result.stdout + result.stderr).lower()
    assert list(tmp_path.glob("FusionBridge-Unified-*.zip")) == []
