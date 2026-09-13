# Blender Bridge/Hub v1 Task 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the durable seven-block Blender Hub v1 design and implement its core-only catalog, concurrency, operator, and transport primitives.

**Architecture:** A new `app.blender_hub` package keeps provider catalog/supervision, same-turn operator coordination, and replay-safe generic dispatch in focused modules. The catalog is a namespaced multiplexer with one global asynchronous mutation lock; no MCP, network, Windows, Blender, or print wiring is included.

**Tech Stack:** Python 3.12, dataclasses, asyncio, threading, pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-09-13-blender-bridge-hub-v1-design.md`

## Global Constraints

- Blender Hub remains a thin multiplexer/supervisor/glue layer; Blender knowledge remains upstream.
- Only explicit read-only metadata bypasses the global write lock; destructive metadata wins conflicts.
- No public MCP wiring, network implementation, Windows/Blender action, Print Pipeline, or remote shell capability is part of Task 1.
- Strict RED → GREEN TDD is required for every production behavior.

---

### Task 1: Provider catalog and global mutation gate

**Files:**
- Create: `app/blender_hub/__init__.py`
- Create: `app/blender_hub/catalog.py`
- Test: `tests/unit/test_blender_hub_catalog.py`

**Interfaces:**
- Produces: `ProviderTool`, `ProviderState`, `ProviderStatus`, `NamespacedToolCatalog.register_provider`, `.set_provider_status`, `.list_tools`, `.provider_statuses`, and `.invoke`.

- [x] Write focused registration/status tests and run them to observe missing-module RED.
- [x] Implement typed descriptors, atomic duplicate detection, provider-local state, and catalog listing; run GREEN.
- [x] Write classification tests for explicit read-only, absent/unknown metadata, and destructive conflict; run RED.
- [x] Implement fail-closed `is_mutating`; run GREEN.
- [x] Write concurrency tests proving reads overlap and writes/unknown calls do not; run RED.
- [x] Add one catalog-wide `asyncio.Lock` around mutating invocation; run GREEN.

### Task 2: Same-turn operator broker

**Files:**
- Create: `app/blender_hub/operator.py`
- Test: `tests/unit/test_blender_hub_operator.py`

**Interfaces:**
- Produces: `OperatorPrompt`, `OperatorNotification`, `OperatorBroker.ask`, `.submit_answer`, `.cancel`, `.notify`, `.pending_prompts`, and `.notifications`.

- [x] Write tests for structured pending prompts and cross-thread answer submission; run RED.
- [x] Implement loop-owned futures with thread-safe completion; run GREEN.
- [x] Write timeout, cancellation, stale-answer, and nonblocking notification tests; run RED.
- [x] Implement cleanup on every terminal path and immediate notification recording; run GREEN.

### Task 3: Replay-safe generic transport helper

**Files:**
- Create: `app/blender_hub/transport.py`
- Test: `tests/unit/test_blender_hub_transport.py`

**Interfaces:**
- Produces: `CallKind`, `TransportOutcome`, `TransportResult`, `TransportFailure`, and `dispatch_with_replay_policy`.

- [x] Write mutating transport-loss test expecting explicit `UNCERTAIN` and one attempt; run RED.
- [x] Implement the mutation branch; run GREEN.
- [x] Write idempotent-read single-retry and non-idempotent-read no-retry tests; run RED.
- [x] Implement the bounded reconnect/retry policy; run GREEN.

### Task 4: Adversarial verification and milestone commit

**Files:**
- Verify all files above; do not add later-task wiring.

- [x] Run all focused Blender Hub tests and closest relevant provider/locking tests.
- [x] Compile the new package and tests.
- [x] Run `git diff --check`; review status and complete diff for scope and accidental files.
- [x] Confirm adversarial cases: unknown/conflicting metadata, stale/timeout/cancel prompts, offline provider isolation, write overlap, and replay limits.
- [x] Commit the completed Task 1 milestone locally with a clear message.
