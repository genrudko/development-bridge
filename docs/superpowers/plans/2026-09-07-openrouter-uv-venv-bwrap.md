# OpenRouter uv venv bwrap Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow a repo-local `.venv` whose Python symlink resolves into the host user's uv-managed Python installation to execute inside the OpenRouter bwrap sandbox without exposing arbitrary host paths.

**Architecture:** Keep the repo-local `.venv` read-only as today. Resolve the selected repo-local venv Python path with kernel-order symlink semantics; if its final target is outside the repo and already-mounted system roots, accept only a target under the uv Python root with shape `<uv-root>/<install>/bin/python*`. Read-only bind only the verified installation contents at the real prefix and, when the literal venv chain requires it, at a verified uv alias destination under the same uv root. Reject arbitrary external interpreters or intermediate external alias hops before launching bwrap.

**Tech Stack:** Python 3.12+, pytest, bubblewrap, uv-managed CPython.

**Spec:** User task in coordinator chat, 2026-09-07.

## Global Constraints

- OpenRouter worker only; do not change Fusion P0 code, routes, wake, GitHub, remotes, push, or unrelated infrastructure.
- Do not expose arbitrary host paths or bind all of HOME.
- Existing system-Python venv behavior must remain unchanged.
- TDD RED -> GREEN; one coherent commit; independent review; full suite if practical; one inspection/test-only live smoke.

---

### Task 1: Resolve and mount uv-managed external interpreter prefix

**Files:**
- Modify: `app/executors/openrouter_worker.py`
- Modify: `tests/unit/test_openrouter_worker.py`

**Interfaces:**
- Consumes: repo-local `.venv`, `BWRAP_PATH`, existing `run_process()` sandbox construction.
- Produces: helper that returns an optional verified uv Python installation prefix for read-only bind, or rejects unsupported external interpreter targets.

- [ ] **Step 1: Write failing tests**
- [ ] **Step 2: Verify RED**
- [ ] **Step 3: Implement minimal resolver and bind**
- [ ] **Step 4: Verify GREEN and real bwrap reproduction**
- [ ] **Step 5: Regression/full verification and commit**
