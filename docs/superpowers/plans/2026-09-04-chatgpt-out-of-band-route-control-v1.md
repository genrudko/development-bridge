# ChatGPT Out-of-Band Route Control v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace model-mediated current-chat discovery with a guarded `openExternal -> redirectUrl` control plane and add safe route bind/status/unbind/wake-cancel lifecycle with diagnosable, human-readable outcomes.

**Architecture:** The existing `RouteRegistry` remains authoritative for logical routes, project policy, generations, and physical targets. A new `RouteControlService` owns short-lived bind operations/candidates, sanitized diagnostics, operator status, and lifecycle orchestration; the coordinator MCP App receives opaque control URLs only through tool-result `_meta`, while the external landing endpoint receives ChatGPT's `redirectUrl`, parses it strictly, stores a candidate on GET, and commits it only on same-origin POST. Wake cancellation spans both `CoordinatorService` pending delivery state and route-generation-scoped durable job terminal waiters without cancelling underlying jobs.

**Tech Stack:** Python 3.12, asyncio, Starlette, MCP Apps / ChatGPT `window.openai.openExternal`, existing `RouteRegistry`, `CoordinatorService`, `JobService`/SQLite `JobStore`, JSON state files, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-04-chatgpt-out-of-band-route-control-v1-design.md`

## Global Constraints

- Physical ChatGPT URL, conversation ID, Project/GPT physical identifier, raw `redirectUrl`, bind/candidate tokens, and raw browser target data MUST NOT appear in model-visible content, structured content, `sendMessage`, `updateModelContext`, continuation prose, or sanitized diagnostics.
- Production current-chat identity MUST come only from ChatGPT host `openExternal` return metadata; no marker/title/search heuristic fallback.
- State-changing GET is prohibited: external GET may validate/store a candidate only; binding changes only on guarded same-origin POST.
- Failed bind/unbind/cancel operations fail closed and preserve the previous active binding unless an earlier cancellation step was already safely committed and explicitly reported.
- Same-target rebind is idempotent; changed-target rebind increments generation and allocates the next channel exactly once.
- Unbound routes remain registered but are ineligible for mount/wake delivery.
- Wake cancellation cancels coordinator delivery state and matching durable wake waiters, never the underlying executor/repository jobs.
- Legacy marker discovery is not a production fallback. Keep dead legacy code only until all live gates pass, then remove it in a separate final task.
- Chat catalog work and Jobs API `busy` observability are out of scope.
- Work only in `/home/eodadmin/.local/state/development-bridge/worktrees/out-of-band-route-control-v1`; do not modify the dirty runtime checkout or Fusion CAD worktree.
- No push, merge, deploy, service restart, live ChatGPT action, credential change, or topology change without an explicit acceptance step from the owner after offline review is green.
- Every implementation task follows RED -> GREEN -> debug sweep -> `git diff --check` -> bounded independent review before the next task.

---

### Task 1: Make RouteRegistry binding state explicit and candidate-based

**Files:**
- Modify: `app/coordinator/routes.py`
- Modify: `app/coordinator/chatgpt_target.py` only if strict parser coverage exposes a real gap
- Test: `tests/unit/test_coordinator_routes.py`
- Test: `tests/unit/test_route_autodiscovery.py`
- Test: `tests/unit/test_chatgpt_target.py` or nearest existing parser test file

**Interfaces:**
- Consumes: existing `RouteRegistry.resolve()`, `prepare_current_bind()`, `complete_current_bind()`, `parse_chatgpt_target()`, `project_identity()`.
- Produces: `RouteRegistry.prepare_current_bind(route_id, *, session_id, allow_project_change=False) -> dict` with no marker field.
- Produces: `RouteRegistry.record_current_bind_candidate(route_id, token, url) -> dict` that validates target/project/source generation and stores the candidate without mutating the active binding.
- Produces: `RouteRegistry.complete_current_bind(route_id, token) -> dict` that atomically consumes a stored candidate.
- Produces: `RouteRegistry.unbind(route_id, *, expected_generation) -> dict` that preserves logical route/generation/channel history while removing active physical target fields and setting `binding_state="unbound"`.
- Produces: `RouteRegistry.is_bound(route) -> bool`; legacy records without `binding_state` are interpreted as bound only when valid physical target fields exist.

- [ ] **Step 1: Write failing registry/parser tests** for legacy-bound migration semantics, marker-free pending bind records, GET-stage candidate recording without route mutation, one-time candidate consumption, TTL expiry, replay, project mismatch, source-generation race, same-target idempotency, changed-target single generation increment, and explicit unbind.

```python
pending = registry.prepare_current_bind("bridge", session_id="session-1")
assert "marker" not in pending
before = registry.resolve("bridge")
registry.record_current_bind_candidate("bridge", pending["token"], candidate_url)
assert registry.resolve("bridge") == before
bound = registry.complete_current_bind("bridge", pending["token"])
assert bound["binding_state"] == "bound"
```

- [ ] **Step 2: Run focused tests and verify RED** for missing candidate/unbind APIs and old marker semantics.

```bash
.venv/bin/pytest -q tests/unit/test_coordinator_routes.py tests/unit/test_route_autodiscovery.py tests/unit/test_chatgpt_target.py
```

- [ ] **Step 3: Implement minimal registry changes**. Candidate target exists only under `current_binds` until commit. Preserve project identity and source-generation guards. Same-target commit is `changed=False`; changed target increments generation once and allocates `telegram-{route_id}-g{generation}` once. `unbind()` removes active physical target fields and writes `binding_state="unbound"` atomically.
- [ ] **Step 4: GREEN/debug sweep** for malformed/cross-origin target, stale/replayed token, generation race, same-target and changed-target bind, and unbind/reload persistence.
- [ ] **Step 5: Verify and commit** with focused pytest, `git diff --check`, intended status only, commit `feat(coordinator): add candidate-based route binding state`.

---

### Task 2: Add route-control diagnostics and bind orchestration service

**Files:**
- Create: `app/coordinator/route_control.py`
- Create: `app/coordinator/route_control_diagnostics.py`
- Modify: `app/coordinator/__init__.py`
- Modify: `app/container.py`
- Test: `tests/unit/test_route_control.py`
- Test: `tests/unit/test_route_control_diagnostics.py`

**Interfaces:**
- Produces: `RouteControlTraceStore(state_dir: Path, raw_ttl_seconds: int = 86400)` with `start()`, `stage()`, `finish()`, `sanitized()`, `purge_expired()`.
- Produces: `RouteControlService.prepare_bind(route_id, *, session_id, allow_project_change=False) -> dict` returning safe logical state plus an opaque external operation URL for component-only delivery.
- Produces: `RouteControlService.accept_bind_return(operation_id, redirect_url) -> dict` that records a candidate but never commits it.
- Produces: `RouteControlService.commit_bind(operation_id) -> dict` that consumes the candidate once.
- Produces: `RouteControlService.safe_status(route_id) -> dict` with safe route state only.

- [ ] **Step 1: Write failing tests** proving sanitized traces never expose forbidden values, raw traces are local-only with 24h default TTL, diagnostic IDs are opaque, prepare/accept do not expose physical identity, GET-stage accept does not mutate the route, commit is single-use, and failures record stable stage/error codes.

```python
prepared = service.prepare_bind("bridge", session_id="session-1")
assert prepared["state"] == "bind_pending"
accepted = service.accept_bind_return(prepared["operation_id"], return_target)
assert registry.resolve("bridge")["conversation_id"] == old_conversation
result = service.commit_bind(prepared["operation_id"])
assert result["state"] in {"bound", "already_bound"}
```

- [ ] **Step 2: Run RED** with `tests/unit/test_route_control.py` and `tests/unit/test_route_control_diagnostics.py`.
- [ ] **Step 3: Implement services** with atomic JSON persistence under route-registry state dir; raw trace path mode `0600`, 24h TTL, never returned by `sanitized()`.
- [ ] **Step 4: GREEN/debug sweep** for missing return target, parse failure, expired/replayed token, project mismatch, generation race, candidate expiry, same/changed target commit, persistence reload, raw expiry.
- [ ] **Step 5: Verify and commit** `feat(coordinator): add out-of-band route control service`.

---

### Task 3: Implement non-mutating landing GET, guarded commit POST, and operator result page

**Files:**
- Create: `app/coordinator/route_control_result.html`
- Modify: `app/transport.py`
- Modify: `app/runtime.py`
- Test: `tests/integration/test_route_control_http.py`
- Remove/replace spike-only `tests/integration/test_chat_return_probe.py` if present in this branch

**Interfaces:**
- Produces: `GET {endpoint}/x/route-control/bind/{operation_id}` accepting ChatGPT-added `redirectUrl`; GET validates/stores candidate only.
- Produces: `POST {endpoint}/x/route-control/bind/{operation_id}/commit`; only this endpoint mutates binding.
- Produces: `GET {endpoint}/x/route-control/return/{diagnostic_id}` server-side redirect to the stored target without embedding physical URL in page HTML.
- Produces: responsive `✅ / ⚠️ / ❌` human result page with safe route/generation/wake summary and diagnostic code.

- [ ] **Step 1: Write failing integration tests** proving GET never changes active route, POST commits once, replay fails closed, invalid/missing return target gives a clear page, HTML contains no raw target/token/physical ID, redirect CSP is Bridge-only, and return uses a server-side redirect.
- [ ] **Step 2: Run RED** with `tests/integration/test_route_control_http.py`.
- [ ] **Step 3: Implement minimal endpoints/template**; remove `/return-probe`, `/tmp` probe state, and probe-only wording.
- [ ] **Step 4: GREEN/debug sweep** for success, missing return, malformed target, expiry/replay, cross-project reject, body/header leakage.
- [ ] **Step 5: Verify and commit** `feat(coordinator): add guarded route-control landing flow`.

---

### Task 4: Switch coordinator widget and bind tool to component-only out-of-band metadata

**Files:**
- Modify: `app/tools/coordinator.py`
- Modify: `app/coordinator/x_ui.html`
- Modify: `app/runtime.py` if needed
- Modify: `app/tools/compact.py` only if surface exposure changes
- Test: `tests/unit/test_coordinator_routes.py`
- Test: `tests/integration/test_mcp_coordinator.py`
- Test: `tests/contract/test_guide_and_job_wake_tools.py`
- Test: `tests/unit/test_compact_surface.py`

**Interfaces:**
- `coordinator_route_bind_current` keeps public intent but no marker/search discovery.
- Model-visible result contains only safe `route_id/state/generation`.
- Opaque bind/control URL and nonce exist only in MCP result `_meta` delivered to the component.
- Widget uses `window.openai.openExternal({href})` only on owner click; no `openLink` fallback and no model-mediated fallback.

- [ ] **Step 1: Write failing tests** asserting model-visible output has no token/URL/physical target, `_meta` has component-only control descriptor, widget uses `openExternal`, and identity discovery contains no marker emission or identity-bearing `sendMessage`/`updateModelContext`.
- [ ] **Step 2: Run RED** against current marker flow.
- [ ] **Step 3: Implement switch** while preserving wake-delivery messaging behavior unrelated to identity discovery.
- [ ] **Step 4: GREEN/debug sweep** for bound/unbound route, repeated UI prep, missing host API, and forbidden-metadata leakage.
- [ ] **Step 5: Verify and commit** `feat(coordinator): bind current chat out of band`.

---

### Task 5: Add route-generation-scoped wake cancellation and guarded unbind

**Files:**
- Modify: `app/coordinator/service.py`
- Modify: `app/jobs/service.py`
- Modify: `app/jobs/store.py`
- Modify: `app/container.py`
- Modify: `app/coordinator/route_control.py`
- Modify: `app/tools/coordinator.py`
- Test: `tests/unit/test_coordinator.py`
- Test: `tests/unit/test_durable_job_waiters.py`
- Test: `tests/integration/test_mcp_coordinator.py`
- Test: `tests/contract/test_guide_and_job_wake_tools.py`

**Interfaces:**
- Produces: `CoordinatorService.cancel_pending(channel_id) -> dict`, idempotent idle; fail closed for actively claimed/in-flight/uncertain wake.
- Produces: `JobService.cancel_durable_waiters(*, handler_name: str, payload_match: dict[str, object]) -> dict`, removing waiter state only, never cancelling jobs.
- Route-scoped waiter payloads include `route_id`, `generation`, `channel_id`.
- `resume_coordinator_waiter()` consumes stale/unbound generation waiters as safe no-op rather than waking a successor route.
- `RouteControlService.cancel_wakes()`, `.unbind()`, `.unbind_and_cancel()` return safe counts/state.

- [ ] **Step 1: Write failing tests** for pending cancel, in-flight fail-closed, durable waiter cancel without job cancel, generation pinning, stale waiter no-op, unbind refusal with wake-producing state, unbind+cancel ordering, idempotency, unbound no-wake.
- [ ] **Step 2: Run RED** on coordinator + durable waiter + MCP coordinator suites.
- [ ] **Step 3: Implement under existing locks**; exact waiter match on handler and payload keys; unbind+cancel verifies zero wake-producing state before registry unbind.
- [ ] **Step 4: GREEN/debug sweep** including restart restoration and a job finishing after unbind+cancel with no wake while result remains queryable.
- [ ] **Step 5: Verify and commit** `feat(coordinator): add guarded wake cancel and unbind lifecycle`.

---

### Task 6: Add safe widget status/actions and sanitized diagnostic tools

**Files:**
- Modify: `app/coordinator/x_ui.html`
- Modify: `app/transport.py`
- Modify: `app/tools/coordinator.py`
- Modify: `app/tools/compact.py`
- Modify: `app/coordinator/route_control.py`
- Test: `tests/integration/test_route_control_http.py`
- Test: `tests/integration/test_mcp_coordinator.py`
- Test: `tests/contract/test_tool_surface.py`
- Test: `tests/unit/test_compact_surface.py`

**Interfaces:**
- Widget actions: `Status`, `Unbind`, `Cancel wake`, `Unbind + cancel wakes` via same-origin control endpoints authorized by component-only metadata.
- Hidden/read-only `coordinator_route_control_status(route_id)` returns safe logical status.
- Hidden/read-only `coordinator_route_control_diagnostic(diagnostic_id)` returns sanitized trace only.
- `coordinator_route_list` removes model-visible physical Project/GPT identifiers and adds safe binding state/generation.
- `_resolve_destination()` rejects unbound route before session binding or wake registration.

- [ ] **Step 1: Write failing surface tests** for all actions, forged/missing control token, safe counts, diagnostics, route-list sanitization, unbound route reject, recursive leakage scan against known physical fixture values.
- [ ] **Step 2: Run RED**.
- [ ] **Step 3: Implement app-only control endpoints and safe tools**; destructive unbind actions require widget confirmation; all actions refresh safe status.
- [ ] **Step 4: GREEN/debug sweep** for stale/forged token, pending counts, failed cancel, diagnostic not found, route-list leakage.
- [ ] **Step 5: Verify and commit** `feat(coordinator): add safe route control surface`.

---

### Task 7: Offline integration, migration safety, and independent review

**Files:**
- Modify only if verification exposes a defect.

- [ ] **Step 1: Run complete focused route-control regression** across parser, registry, route-control, diagnostics, coordinator, durable waiters, HTTP, MCP coordinator, guide/job-wake contract, tool surface, compact surface.
- [ ] **Step 2: Run closest broader suites, repository-standard Ruff, `git diff --check`, and full pytest if bounded runtime remains acceptable. Record unrelated failures separately.
- [ ] **Step 3: Run leakage/debug sweep** for `/return-probe`, raw targets, marker activation, model-visible token/URL paths; verify legacy route migration keeps generation/channel.
- [ ] **Step 4: Independent Codex review** of full implementation range, findings first. Critical/Important => one bounded Antigravity repair pass + focused Codex re-review.
- [ ] **Step 5: Commit review fixes only after fresh verification; keep worktree clean. No push/deploy/restart.**

---

### Task 8: Explicit live acceptance gates

**Files:** runtime/deployment only after owner explicitly authorizes this acceptance step.

- [ ] **Step 1: Obtain explicit owner authorization for temporary deployment/restart**, then synchronize reviewed code without resetting dirty runtime checkout.
- [ ] **Step 2: Ordinary Web:** bind, clear human page, sanitized diagnostic, same-chat idempotency, non-sending ReviewGPT target probe.
- [ ] **Step 3: Project Web:** bind + non-sending probe; cross-Project unauthorized attempt fails closed.
- [ ] **Step 4: Expiry/replay + unbind/cancel:** expired/replayed candidate rejected; real durable waiter cancelled; underlying job finishes; no later wake; job result still queryable.
- [ ] **Step 5: Mobile:** owner taps bind from one mobile ChatGPT client; page reports success; no URL/ID copying.
- [ ] **Step 6: Record live evidence. Any failure returns to bounded offline TDD repair; never fall back to marker discovery.**

---

### Task 9: Retire marker/search discovery after live stabilization

**Files:**
- Modify: `app/coordinator/x_ui.html`
- Modify: `app/coordinator/wake_delivery.py`
- Modify: `app/coordinator/wake_transport.py`
- Modify: `app/coordinator/review_gpt_transport.py` only where marker discovery hooks exist
- Modify: `app/coordinator/routes.py`
- Modify: `app/tools/coordinator.py`
- Modify: `docs/operations/review-gpt-coordinator-wake.md`
- Modify: `AGENTS.md`
- Modify/remove marker-specific tests

- [ ] **Step 1: Adjust tests first** so production bind cannot call marker discovery.
- [ ] **Step 2: Remove only marker/Global-Search current-chat discovery code and obsolete docs/tests**; preserve ReviewGPT wake delivery and unrelated Browser Host infrastructure.
- [ ] **Step 3: Run focused + full bounded regression, Ruff, diff-check, leakage grep.**
- [ ] **Step 4: Independent Codex final review; bounded repair only for validated Critical/Important findings.**
- [ ] **Step 5: Commit** `refactor(coordinator): retire marker-based chat discovery`.

Do not push, merge, or deploy the branch without a separate explicit owner command.
