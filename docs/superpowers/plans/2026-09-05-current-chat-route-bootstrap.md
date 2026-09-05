# Current-chat Route Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add URL-free creation-and-binding of a missing logical route from the exact current ChatGPT conversation.

**Architecture:** Extend the existing `coordinator_route_bind_current` OOB flow with an explicit `bootstrap_if_missing` flag. Missing routes get only a pending bootstrap operation until OOB commit; commit atomically creates generation 0 and binds the validated target. Existing route semantics stay unchanged.

**Tech Stack:** Python 3.12, existing RouteRegistry/RouteControlService/MCP tools, pytest.

**Spec:** `docs/superpowers/specs/2026-09-05-current-chat-route-bootstrap-design.md`

## Global Constraints

- No model-visible ChatGPT URL, conversation ID, project ID, MCP/session ID, redirect target, token, nonce, or marker/search fallback.
- Missing-route bootstrap must not mutate the route registry before successful OOB commit.
- Existing-route bind and exclusive endpoint ownership semantics must not regress.
- No push or production restart until tests and independent review are green.

---

### Task 1: Registry and route-control bootstrap transaction

**Files:**
- Modify: `app/coordinator/routes.py`
- Modify: `app/coordinator/route_control.py`
- Test: `tests/unit/test_coordinator_routes.py`
- Test: existing route-control unit tests

**Interfaces:**
- Consumes: existing bind operation/candidate lifecycle.
- Produces: pending missing-route bootstrap and atomic create-on-commit for generation 0.

- [ ] Write failing tests for missing-route pending bootstrap, zero pre-commit route mutation, successful generation-0 commit, replay/idempotency, expiry/failure no-route behavior, and concurrent conflict fail-closed semantics.
- [ ] Run focused tests and verify RED failures are caused by the missing bootstrap behavior.
- [ ] Implement the minimum registry/route-control changes.
- [ ] Run focused tests to GREEN and refactor without changing behavior.
- [ ] Commit the task.

### Task 2: MCP tool contract and integration

**Files:**
- Modify: `app/tools/coordinator.py`
- Test: `tests/integration/test_mcp_coordinator.py`
- Test: `tests/contract/test_tool_surface.py`
- Test: `tests/contract/test_guide_and_job_wake_tools.py` if schema/guide assertions require it

**Interfaces:**
- Consumes: Task 1 bootstrap transaction.
- Produces: `coordinator_route_bind_current(route_id, allow_project_change=false, bootstrap_if_missing=false)`.

- [ ] Write failing integration/contract tests proving default missing-route failure is preserved and explicit bootstrap returns only safe pending metadata.
- [ ] Verify RED.
- [ ] Add `bootstrap_if_missing` to the direct tool schema and route-control call without exposing physical identity material.
- [ ] Run integration/contract tests to GREEN.
- [ ] Commit the task.

### Task 3: Regression and release gate

**Files:**
- Modify documentation only if runtime behavior requires a runbook note.

**Interfaces:**
- Consumes: Tasks 1-2.
- Produces: reviewed merge-ready branch.

- [ ] Run route-control/coordinator neighboring suites and `git diff --check`.
- [ ] Run the complete pytest suite.
- [ ] Run Ruff when available in the repository/runtime; if unavailable, record that fact rather than claiming a lint pass.
- [ ] Independent whole-branch review against the spec.
- [ ] Fix any load-bearing findings with RED->GREEN regression tests and re-review.
- [ ] Fast-forward local `main` only after green review; do not push.
- [ ] Guarded idle restart and live acceptance with a disposable logical route; verify generation 0 and no model-visible physical identity leakage.
