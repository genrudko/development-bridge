# Fusion Eyes Managed Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make the existing Fusion Bridge GUI automatically own the PERISCOPE proxy and `fusion-eyes` Relay, removing the two manual PowerShell windows.

**Architecture:** Keep `windows_fusion_agent.py` unchanged. Extend only `fusion_relay_gui.pyw` with one optional eyes process group: existing installed `mcp-proxy` exposes PERISCOPE on `127.0.0.1:18769`, then a second unchanged Relay registers node `fusion-eyes` with a dedicated outbox. Missing PERISCOPE runtime degrades only Eyes, never the official `fusion-workstation` Relay.

**Tech Stack:** Python stdlib/Tkinter/subprocess, existing Relay, installed PERISCOPE venv/mcp-proxy, pytest.

**Spec:** `docs/research/fusion-cad-agent-operational-roadmap-2026-09-11.md`

## Global Constraints
- Do not rewrite Relay or add a transport/queue.
- Reuse the existing DPAPI token and `windows_fusion_agent.py`.
- Keep official `fusion-workstation` behavior unchanged.
- Eyes node is exactly `fusion-eyes`; proxy endpoint exactly `http://127.0.0.1:18769/mcp`; outbox is distinct.
- GUI does not silently install/update PERISCOPE.
- Stop/window-close terminates only eyes processes created by this GUI instance.
- Live Windows/Fusion acceptance is deferred until the owner powers the PC back on.

---

### Task 1: Eyes runtime profile
**Files:** Create `agents/fusion_eyes_runtime.py`; modify `agents/fusion_relay_gui.pyw`; test `tests/unit/test_fusion_gui_launcher.py`.

- [x] Write RED tests for pure profile helpers: paths under `%LOCALAPPDATA%/DevelopmentBridgeFusion/periscope/server/.venv`, proxy argv `mcp-proxy.exe --port 18769 --host 127.0.0.1 --pass-environment -- <python> -m periscope_mcp`, node `fusion-eyes`, endpoint `http://127.0.0.1:18769/mcp`, separate `eyes-outbox`, and missing-runtime reporting.
- [x] Run focused eyes tests; expect missing helper/constants failure.
- [x] Implement pure constants/helpers in `agents/fusion_eyes_runtime.py`; do not modify `windows_fusion_agent.py`.
- [x] Re-run focused helper tests; expect PASS.

### Task 2: GUI process lifecycle
**Files:** Modify `agents/fusion_relay_gui.pyw`, `agents/FUSION_GUI_README.txt`; test `tests/unit/test_fusion_gui_launcher.py`.

- [x] Write RED assertions that GUI owns `eyes_proxy_proc` and `eyes_relay_proc`, starts them after the official Relay using the same DPAPI token, tracks Eyes connected state, uses a distinct outbox, and stops both on Stop/close.
- [x] Run GUI tests; expect new assertions to fail.
- [x] Implement one Eyes status line; start hidden proxy + second Relay if runtime is present; parse second Relay output; terminate owned eyes processes; missing/broken runtime logs precise degradation but does not block official Relay.
- [x] Update README: one Start launches official Relay plus optional installed Eyes stack; manual proxy/Relay PowerShell no longer required.
- [x] Run GUI tests, `tests/unit/test_windows_fusion_agent.py`, syntax compile, and `git diff --check`; expect PASS.

### Task 3: Reproducible pinned PERISCOPE bootstrap
**Files:** Create `agents/INSTALL_FUSION_EYES.ps1` and `agents/periscope-lost-event.patch`; modify `agents/FUSION_GUI_README.txt`; test `tests/unit/test_fusion_gui_launcher.py`.

- [x] Write RED static contract test for the qualified commit, upstream URL, `mcp>=1.27,<2`, `mcp-proxy==0.12.0`, idempotent reverse/check patch detection, and the exact lost-event hunk.
- [x] Verify RED because installer/patch files do not exist.
- [x] Implement one-time bootstrap: clone/fetch/checkout exact pin when safe, reject unrelated dirty state, apply or recognize the bundled patch, run full install on first setup or `--sync` on an existing setup, then ensure proxy dependencies in the PERISCOPE venv. Normal GUI Start never calls this installer.
- [x] Verify launcher/installer tests and `git diff --check`.
