# Route Isolation and Executor Routing Implementation Plan

**Status:** completed and coordinator-reviewed 2026-09-01.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for behavior changes. Steps use checkbox syntax for tracking.

**Goal:** Prevent one project/chat from hijacking another logical coordinator route and make normal workers mount the correct pre-registered route without asking the owner for ChatGPT URLs.

**Architecture:** Keep logical-route ownership in `RouteRegistry`. Add a read-only route-list capability for discovery, reject cross-project takeover of an existing route, and make normal worker guidance explicitly mount an existing route rather than call takeover. Exceptional physical-chat rollover continues through the existing automatic rollover path.

**Tech Stack:** Python 3.12, MCP 2.0, pytest, existing CoordinatorService/RouteRegistry.

**Spec:** Existing coordinator/wake contracts plus owner-approved routing policy from 2026-09-01.

## Global Constraints

- `bridge` is the general Development Bridge infrastructure route.
- `eod` is the EOD route.
- `ad5xwork` remains the AD5X product/work route.
- Ordinary workers must not call `coordinator_route_takeover` to begin work.
- Normal setup is route discovery/list -> `coordinator_x_mount(route_id=...)`; no owner-supplied URL.
- An existing route may not be taken over by a conversation in a different ChatGPT Project.
- Do not change coordinator wake delivery semantics, ReviewGPT transport, or unrelated repository topology.
- Follow VPS-first, Economy Mode, and mandatory debug-sweep rules.

---

### Task 1: Fail closed on cross-project route takeover

**Files:**
- Modify: `app/coordinator/routes.py`
- Test: `tests/unit/test_routes.py`

- [x] Add a failing test proving takeover of an existing route from a different non-equal `project_id` raises `POLICY_VIOLATION` and leaves the route unchanged.
- [x] Run the exact test and verify RED.
- [x] Implement the smallest ownership guard in `RouteRegistry.takeover`.
- [x] Run route tests and verify GREEN, including same-project takeover remaining valid.

### Task 2: Add read-only registered-route discovery

**Files:**
- Modify: `app/tools/coordinator.py`
- Test: coordinator tool unit/contract tests near existing coordinator route tests.

- [x] Add a failing test for `coordinator_route_list` returning bounded route metadata without mutating requested/default route or session binding.
- [x] Verify RED.
- [x] Add the hidden read-only tool using `RouteRegistry.list_routes()`; return route_id/title/project_id/channel_id/generation/default only, not secrets.
- [x] Verify GREEN and tool-catalog discoverability.

### Task 3: Codify no-URL normal worker setup

**Files:**
- Modify: `app/tools/guide.py`
- Modify: `app/tools/coordinator.py` tool descriptions
- Modify: `AGENTS.md`
- Modify: `docs/operations/executor-operating-contract.md`
- Modify: relevant contract tests for guide text.

- [x] Add/adjust tests first so guide/tool descriptions require: route-list discovery, mount existing route, never reuse another project's route, takeover only for exceptional explicit route migration/rollover.
- [x] Verify RED.
- [x] Update guidance with current route map: `development-bridge -> bridge`, `eod -> eod`, AD5X product work -> `ad5xwork`; workers should prefer `coordinator_route_list` if uncertain.
- [x] State explicitly that the owner must not be asked to copy a ChatGPT URL for ordinary executor setup; URLs are only an exceptional route-bootstrap/takeover concern.
- [x] Verify GREEN.

### Task 4: Debug sweep and review

- [x] Run targeted route/coordinator/guide tests.
- [x] Exercise same-project takeover, cross-project rejection, route-list read-only behavior, and ordinary mount behavior.
- [x] Run nearest coordinator/compact contract suites.
- [x] Run `git diff --check`, inspect bounded diff/status, and confirm unrelated untracked `share_transcript_6a921405.json`, `tmp/`, and the separate operator-dashboard spec are untouched.
- [x] Run the repository-required broader suite if bounded/time-feasible; classify unrelated existing failures instead of hiding them.
- [x] Return concise evidence to the coordinator; do not push/deploy/restart.

## Coordinator review correction

Independent coordinator review caught and fixed two defects before acceptance: `coordinator_route_context_update` had lost its return while `route_list` was inserted, and project comparison was tightened to compare the stable `g-p-<32hex>` identity so slug changes within one ChatGPT Project remain valid without permitting prefix-based cross-project takeover. Added regression coverage for both.
