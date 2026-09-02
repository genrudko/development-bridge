# Coordinator Wake Transports Implementation Plan

**Status:** implemented and live-accepted on 2026-09-01. This file is retained as implementation history; unchecked boxes below are historical plan notation, not current TODOs. Current operations are documented in `docs/operations/review-gpt-coordinator-wake.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Development Bridge coordinator wake delivery transport-neutral and add a fail-closed `review-gpt` direct transport without replacing the existing durable continuation state machine.

**Architecture:** `CoordinatorService` remains the single durable source of continuation state. A new `CoordinatorWakeDeliveryService` claims transport-eligible wakes and routes them through a `WakeTransport` protocol; `ReviewGptWakeTransport` is the first backend, while X remains intact and Work can be added later behind the same interface.

**Tech Stack:** Python 3.12, asyncio, Pydantic settings, existing CoordinatorService/RouteRegistry, `pytest`, external Node24 `review-gpt` CLI via argv.

**Spec:** `docs/superpowers/specs/2026-08-31-coordinator-wake-transports-design.md`

## Global Constraints

- Keep `CoordinatorService` as the single durable continuation/outbox state machine.
- Do not use private ChatGPT APIs, auth replay, Cloudflare bypass, or coordinate clicking.
- Direct delivery is disabled by default.
- Exact route conversation UUID and authoritative Project URL are required for every direct send.
- No automatic retry or cross-transport fallback after an uncertain submission.
- Existing X / Browser Host behavior must remain unchanged by default.
- Do not run live ChatGPT Web E2E until code review and offline verification are complete.

---

### Task 1: Direct-transport coordinator state semantics

**Files:**
- Modify: `app/coordinator/service.py`
- Test: `tests/unit/test_coordinator.py`

**Interfaces:**
- Produces: transport-aware `status()` / `claim()` behavior preserving X defaults.
- Produces: durable finalization API for `delivered`, `not_submitted`, `uncertain`, and `owner_input_required` results.

- [ ] **Step 1: Write failing tests** proving direct mode bypasses Browser Host preflight only, while X mode still requires it.
- [ ] **Step 2: Run targeted tests and verify RED** for missing direct transport behavior.
- [ ] **Step 3: Implement the minimal coordinator state changes** with bounded durable transport diagnostic fields.
- [ ] **Step 4: Run targeted tests and verify GREEN**, including persistence/reload for blocked uncertain state.
- [ ] **Step 5: Commit** coordinator state semantics.

### Task 2: Wake transport contract and ReviewGPT adapter

**Files:**
- Create: `app/coordinator/wake_transport.py`
- Create: `app/coordinator/review_gpt_transport.py`
- Test: `tests/unit/test_review_gpt_wake_transport.py`

**Interfaces:**
- Produces: `WakeTarget`, `WakeProbeResult`, `WakeDeliveryRequest`, `WakeDeliveryResult`, `WakeTransport`.
- Produces: `ReviewGptWakeTransport.probe()` and `.deliver()`.

- [ ] **Step 1: Write failing tests** for exact target probe, busy/Cloudflare rejection, deterministic receipt path, argv construction, and receipt-based no-resend.
- [ ] **Step 2: Run targeted tests and verify RED** because transport modules do not exist.
- [ ] **Step 3: Implement minimal protocol and adapter** using dependency-injected HTTP/process runners so tests remain offline.
- [ ] **Step 4: Run targeted tests and verify GREEN**; no live browser send.
- [ ] **Step 5: Commit** transport contract and adapter.

### Task 3: Direct delivery service and settings

**Files:**
- Create: `app/coordinator/wake_delivery.py`
- Modify: `app/settings.py`
- Modify: `app/container.py`
- Modify: `app/runtime.py`
- Modify: `app/coordinator/__init__.py`
- Modify: `.env.example`
- Modify: `config/bridge.example.yaml`
- Test: `tests/unit/test_wake_delivery.py`
- Test: `tests/unit/test_settings.py` or nearest existing settings test file.

**Interfaces:**
- Consumes: `WakeTransport`, coordinator direct claim/finalization, `RouteRegistry`.
- Produces: `CoordinatorWakeDeliveryService.start()` / `.stop()` lifecycle and disabled-by-default ReviewGPT configuration.

- [ ] **Step 1: Write failing tests** for disabled no-op startup, exact route mapping, one-lane delivery, result-to-coordinator-state mapping, and no resend after uncertain.
- [ ] **Step 2: Run targeted tests and verify RED** for missing service/settings.
- [ ] **Step 3: Implement settings and service**; wire into container and MCP lifespan without changing X tools/routes.
- [ ] **Step 4: Run targeted tests and verify GREEN**.
- [ ] **Step 5: Commit** delivery service/configuration.

### Task 4: Offline integration/regression verification

**Files:**
- Modify only if verification exposes a regression.
- Test: coordinator unit, coordinator contract/integration, settings, new wake transport tests.

**Interfaces:**
- Produces: verified code ready for runtime configuration, but no deployment/live send yet.

- [ ] **Step 1: Run coordinator-focused unit/contract/integration suites**.
- [ ] **Step 2: Run `ruff`/format checks used by the repository and `git diff --check`**.
- [ ] **Step 3: Run the broader test suite** within bounded runtime.
- [ ] **Step 4: Review the complete diff** for scope, secret leakage, accidental `tmp/`/transcript changes, and live-Web calls in tests.
- [ ] **Step 5: Commit any verification-only fixes**.

### Task 5: Runtime configuration and one acceptance gate

**Files:**
- Runtime configuration only after offline review is accepted; no repository secrets.

**Interfaces:**
- Consumes: proven existing headful Chromium/Xvfb + `review-gpt` runtime.
- Produces: one exact-current-chat continuation acceptance result.

- [ ] **Step 1: Configure ReviewGPT transport with explicit Node/CLI/config/CDP/receipt paths** on VPS.
- [ ] **Step 2: Restart Development Bridge using the guarded Bridge restart path only when idle**.
- [ ] **Step 3: Verify health without sending a ChatGPT message**.
- [ ] **Step 4: Run exactly one deliberate exact-current-chat continuation E2E**.
- [ ] **Step 5: If successful, keep X as fallback and begin soak; if uncertain/owner-input-required, do not retry automatically**.

## Post-implementation acceptance record

- ReviewGPT Project-route regression fixed in both ReviewGPT and Development Bridge.
- Read-only exact-Project preflight passed after operator re-authentication.
- Sequential production soak: 5/5 real terminal jobs, more than 70 minutes first-to-fifth committed wake, no observed duplicates or reordering.
- Separate failure-terminal job (`exit 7`) delivered correctly.
- Checked wake attempts left Chromium/Xvfb inactive with zero owned processes.
- Work / Cloud Browser independently passed 5/5 but remains fallback because it consumes Work quota.
- Executor/debug discipline for future changes is defined in `AGENTS.md` and `docs/operations/executor-operating-contract.md`.
