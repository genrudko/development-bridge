# Unified Fusion Windows Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** One manually launched Fusion Bridge GUI supervises Reference, Eyes, and Hands; Fusion itself remains manual.

**Architecture:** Keep `fusion_relay_gui.pyw` as the only GUI. Reuse workstation + Eyes, add `fusion_hands_runtime.py` for pinned Shimmer, guarded overlay state, and Hands process specs. Provider groups recover independently with bounded retry. Existing `START_FUSION_GUI.cmd` remains the entrypoint.

**Tech Stack:** Python 3.12, Tkinter, subprocess, pathlib, hashlib/json, pytest, Windows DPAPI.

**Spec:** `docs/superpowers/specs/2026-09-11-fusion-unified-windows-launcher-design.md`

## Global Constraints
- Fusion and GUI both launch manually.
- Shimmer pin `97a06e76c289420a721590ddcab334f5f3dc3178`.
- Reference 27182; Eyes 18769; Hands 18768; add-in bridge 9000.
- Unknown Eyes/Hands listener occupancy fails closed.
- Terminate only GUI-owned child processes.
- Overlay uses existing manifest contract and local filesystem only.
- Hands capability promotion remains Bridge-owned/session-scoped.
- No Fusion document save/close/mutation side effects.

### Task 1: Hands runtime + overlay inspection
**Files:** create `agents/fusion_hands_runtime.py`; modify launcher tests.
- [ ] RED process-spec tests: exact sidecar argv, relay env/node/outbox/token, missing runtime.
- [ ] Implement `build_hands_process_specs` + constants; GREEN.
- [ ] RED overlay-state tests: missing, unapplied-valid, applied-valid, source/live mismatch.
- [ ] Implement `inspect_hands_overlay`; GREEN; commit.

### Task 2: Guarded overlay application
**Files:** Hands helper + launcher tests.
- [ ] RED tests: exact four-file apply, idempotence, mismatch refusal, rollback.
- [ ] Implement `ensure_hands_overlay` with atomic replace + rollback.
- [ ] GREEN, diff-check, commit.

### Task 3: Unified GUI supervision
**Files:** modify `agents/fusion_relay_gui.pyw`, launcher tests.
- [ ] RED tests for explicit Reference/Eyes/Hands rows, Hands process ownership, auto-supervision, Stop/close cleanup.
- [ ] Implement Hands start/stop/watchers and separate logs.
- [ ] RED tests for independent process failure and bounded retry/backoff.
- [ ] Implement provider-scoped recovery and GUI-before-Fusion auto-convergence.
- [ ] Preserve token repair/forget and idempotent Stop; normal start is automatic.
- [ ] Run launcher tests GREEN; commit.

### Task 4: Bootstrap + operator UX
**Files:** modify `agents/START_FUSION_GUI.ps1`, `agents/FUSION_GUI_README.txt`, launcher tests.
- [ ] RED tests for manual Fusion/manual GUI, no startup registration, no separate Hands launcher, consoleless bootstrap, existing token/mcp behavior.
- [ ] Update bootstrap/docs minimally; GREEN; commit.

### Task 5: Verification + package
- [ ] Run focused launcher/runtime tests.
- [ ] Run related Fusion CAD service/Hands tests.
- [ ] Run full repository suite and `git diff --check`.
- [ ] Independent read-only review; repair only proven findings through RED/GREEN.
- [ ] Build Windows package containing unified GUI/bootstrap/helper plus guarded overlay assets and record SHA256.
- [ ] Next Windows interaction: manually launch Fusion + unified GUI once; verify all three nodes online and resume approved disposable Hands live gate.
