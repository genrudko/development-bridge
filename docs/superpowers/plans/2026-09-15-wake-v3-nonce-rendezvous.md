# Wake v3 VPS-Only Nonce Rendezvous Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Browser Binder as the canonical current-chat bind path with a durable VPS-only ChatGPT Global Search nonce rendezvous.

**Architecture:** Bridge creates a safe model-visible marker and persists only logical rendezvous state. ReviewGPT's authenticated VPS browser searches the exact marker, verifies a sole candidate, and hands the candidate URL directly in memory to the existing guarded RouteControl bind candidate/commit path. Browser Binder remains fallback-only.

**Tech Stack:** Python 3.12, asyncio, existing Development Bridge coordinator/route-control services, Node.js CDP helper, pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-wake-v3-nonce-rendezvous-design.md`

## Global Constraints

- No owner desktop/browser dependency in the canonical bind path.
- Candidate ChatGPT URL/conversation/project identity must never enter durable rendezvous state, normal logs, or model-visible payloads.
- Exact marker only; zero candidates retry, one candidate verifies, more than one unique candidate fails closed.
- Reuse existing RouteControl generation/project/token guards; do not create parallel binding policy.
- Default TTL 30 minutes; retry delays 5s, 15s, 30s, 60s, then 120s capped.
- Browser Binder remains tested but is fallback-only.

---

### Task 1: ReviewGPT Global Search helper

**Files:**
- Create: `scripts/chatgpt_nonce_rendezvous.mjs`
- Create: `tests/unit/test_chatgpt_nonce_rendezvous_helper.py`

**Interfaces:** helper CLI accepts `--browser-endpoint` and `--marker`; stdout is one JSON object with `status` in `zero|unique|ambiguous|owner_input_required|transient`, and `candidate_url` only for `unique` after exact in-chat verification.
- [ ] Write failing tests for URL canonicalization/deduplication, zero/ambiguous fixture handling, and exact single-marker verification contract.
- [ ] Run `pytest -q tests/unit/test_chatgpt_nonce_rendezvous_helper.py` and confirm RED.
- [ ] Implement the helper using raw CDP WebSocket: open Global Search, wait for Search input, focus it, type via native `Input.dispatchKeyEvent`, verify exact input value, wait for loading to settle, canonicalize `/c/<id>` or `/g/<project>/c/<id>` result hrefs, dedupe, open a sole result, and require exactly one matching user-message turn.
- [ ] Run the helper unit tests and `node --check scripts/chatgpt_nonce_rendezvous.mjs`; confirm GREEN.
- [ ] Commit `feat: add ChatGPT nonce rendezvous resolver`.

### Task 2: ReviewGPT resolver integration

**Files:**
- Modify: `app/coordinator/review_gpt_transport.py`
- Modify: `tests/unit/test_review_gpt_wake_transport.py`

**Interfaces:** add `RendezvousResolution(status, candidate_url=None, detail=None)` and async `ReviewGptWakeTransport.resolve_bind_marker(marker)`. It must reuse `_operation_lock` and on-demand browser lifecycle; physical URL exists only in the returned in-memory object for `unique`.

- [ ] Write RED tests for zero/unique/ambiguous/transient/owner-input results and serialization rejection of malformed helper output.
- [ ] Implement minimal helper invocation and lifecycle reuse, bounding non-sensitive error detail while never embedding candidate URL in detail.
- [ ] Run `pytest -q tests/unit/test_review_gpt_wake_transport.py` and confirm GREEN.
- [ ] Commit `feat: expose ReviewGPT bind marker resolution`.

### Task 3: Durable rendezvous service

**Files:**
- Create: `app/coordinator/bind_rendezvous.py`
- Create: `tests/unit/test_bind_rendezvous.py`
- Modify: `app/coordinator/__init__.py`

**Interfaces:** `BindRendezvousService.prepare(route_id, allow_project_change=False)`, `status(route_id)`, `start()`, `stop()`. State file: sibling `bind-rendezvous.json` next to route registry. Resolver callback returns `RendezvousResolution`. Successful resolution creates an internal normal current-bind operation and immediately calls `accept_bind_return(..., retain_return_target=False)` then `commit_bind()` under route lock.

- [ ] Write RED tests for marker entropy/shape, 30-minute TTL, retry schedule, restart restoration, zero retry, ambiguity terminal failure, expiry, generation race, unique commit, and no physical identity persisted.
- [ ] Implement atomic JSON persistence, one-live-rendezvous-per-route rule, background due-work loop, exact retry schedule, and guarded commit reuse.
- [ ] Run `pytest -q tests/unit/test_bind_rendezvous.py tests/unit/test_route_control.py` and confirm GREEN.
- [ ] Commit `feat: add durable bind rendezvous service`.
### Task 4: MCP/container integration

**Files:**
- Modify: `app/container.py`
- Modify: `app/runtime.py`
- Modify: `app/tools/coordinator.py`
- Modify: `app/tools/compact.py`
- Modify: `app/coordinator/route_control.py`
- Modify: `tests/unit/test_coordinator_routes.py`
- Modify: `tests/unit/test_compact_surface.py`
- Modify: `tests/contract/test_tool_surface.py`
- Modify: `tests/integration/test_mcp_coordinator.py`

**Interfaces:** add compact-visible `coordinator_route_bind_rendezvous_prepare(route_id, allow_project_change=false)`. Safe success payload is exactly `route_id,state,generation,marker,expires_at`. Extend route-control status with `rendezvous` safe diagnostics excluding marker/nonce after prepare.

- [ ] Write RED tool/contract/integration tests including exact safe field assertions and compact tool-count update.
- [ ] Wire the rendezvous service to the existing ReviewGPT transport in the container and lifecycle `start()/stop()` in runtime.
- [ ] Add prepare tool and safe status projection; keep existing Browser Binder/direct-App paths unchanged.
- [ ] Run focused coordinator/tool/integration suites and confirm GREEN.
- [ ] Commit `feat: expose VPS-only route bind rendezvous`.

### Task 5: Operator docs and full offline acceptance

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/operations/review-gpt-coordinator-wake.md`
- Modify: `docs/operations/mcp-hub-routing.md`
- Modify: `tests/contract/test_guide_and_job_wake_tools.py`

- [ ] Add RED documentation contract proving canonical bind says VPS-only nonce rendezvous and Browser Binder is fallback-only.
- [ ] Update docs and guide text; preserve canonical wake re-entry `RDC -> GPTAdmin -> development-bridge -> coordinator_ack`.
- [ ] Run targeted Wake v3 suites, then full `pytest -q`, `git diff --check`, and Node syntax check.
- [ ] Commit `docs: make nonce rendezvous canonical bind path`.

### Task 6: Live VPS-only acceptance

**Files:** no product-code changes expected.

- [ ] Fast-forward local `main` only after the feature branch is fully green; do not push remote refs.
- [ ] Guarded-restart Development Bridge and verify the new compact tool is reachable through GPTAdmin.
- [ ] Prepare route `gptadmin` via the new rendezvous tool and emit its returned marker exactly once in this ChatGPT conversation.
- [ ] Observe durable search state progress `pending -> bound` without owner desktop/browser participation; confirm no physical target appears in logs/tool output.
- [ ] Run one synthetic durable job and wait for one ReviewGPT wake into this exact chat.
- [ ] Re-enter only through `RDC -> GPTAdmin -> development-bridge`, call `coordinator_ack` once for the emitted continuation, and verify no duplicate pending wake remains.

## Self-review

Every spec acceptance item maps to Tasks 1-6. No task introduces a second browser profile or parallel route policy. The only process-memory physical URL crosses Task 1 -> Task 2 -> Task 3 and is immediately consumed by existing RouteControl guards; no durable interface contains it.