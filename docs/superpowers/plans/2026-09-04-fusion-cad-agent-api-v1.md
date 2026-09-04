# Fusion CAD Agent API v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the accepted `fusion.cad/v1` contract from P0 semantic/visual foundations through P1 safe high-level modeling and P2 advanced engineering workflows.

**Architecture:** Preserve the existing outbound Windows Fusion relay, durable async operation journal, result artifacts, and raw Fusion MCP escape hatch. Add a focused `app/fusion_cad/` domain facade with strict request schemas, revision-aware orchestration, versioned Bridge-owned Fusion scripts, and semantic MCP adapters. P0, P1, and P2 are separate gated execution plans under this master plan.

**Tech Stack:** Python 3.12, Pydantic v2, MCP Python SDK, existing `DesktopNodeService`, Autodesk Fusion Python API through local `fusion_mcp_execute`, pytest/pytest-asyncio, Ruff, Development Bridge durable executors.

**Spec:** `docs/superpowers/specs/2026-09-04-fusion-cad-agent-api-v1-design.md`

## Global Constraints

- Contract version is exactly `fusion.cad/v1`; breaking public changes require a new contract version.
- Public CAD tools are semantic families, never one tool per Autodesk primitive.
- Existing Fusion transport tools and `fusion_mcp_execute(script)` remain available as infrastructure/escape hatch.
- Canonical units are `mm`, `mm^2`, `mm^3`, `deg`, `g`, and `g/cm^3`.
- Every standalone mutation requires `expected_revision`; transaction mutations bind to `baseline_revision`.
- `model_revision` must detect manual/external Fusion changes before a later mutation/commit; false-safe revision behavior is prohibited.
- Automatic `bridge.cad/v1` metadata/provenance is written only inside the same Fusion transaction as the geometry it describes.
- `view_ref` is immutable and binds model revision, camera, effective visibility, viewport dimensions, and section state.
- Version-dependent functions explicitly report `supported`, `degraded`, or `unavailable`; no silent semantic fallback.
- No CAD mutation, transaction, validation, screenshot, checkpoint, or export saves the Fusion document without explicit user authorization.
- Large JSON/binary outputs use retained external artifacts/resources; base64 does not return to model context.
- P1 is blocked until both P0 feasibility gates pass live Fusion acceptance: visual pick and transaction preview/abort/replay/commit.
- P2 is blocked until the P1 Schedule golden gate is accepted.
- Live release acceptance uses a disposable Schedule copy. If a disposable copy cannot be positively identified, stop before mutation rather than touching the original.
- Work VPS-first. Live Fusion/UI acceptance happens only after offline tests/review are green.
- No push, merge, runtime restart, deploy, service change, credential change, or repository-topology change unless that exact action is explicitly authorized at execution time.

## Executor Strategy

Development Bridge executors are the default implementation mechanism. The coordinator owns architecture, task boundaries, evidence review, rulings, and live acceptance; it does not manually implement large milestones when a healthy executor can do them.

### Primary roles

1. **Implementation:** explicitly dispatch `executor_start(..., executor="antigravity", task_kind="implementation")` for each bounded implementation task while Antigravity is available/authenticated and not known quota-exhausted.
2. **Task review:** dispatch a fresh independent `executor_start(..., executor="codex", task_kind="review")` after each implementation task. The reviewer reads the task brief, implementer report, and bounded diff package; it does not rewrite the implementation unless a separate fix task is authorized.
3. **Fix loop:** the original implementation executor gets the first repair pass with the concrete review findings. If Antigravity is unavailable, auth-blocked, quota-exhausted, or has a proven executor-runtime failure, classify that evidence first and explicitly dispatch Codex as the replacement implementation executor. Do not create an automatic retry loop.
4. **Whole-phase review:** use an executor independent from the latest significant implementation work. Prefer Codex when the phase was primarily implemented by Antigravity; if Codex performed substantial fallback implementation, use Antigravity for final cross-review when healthy.
5. **Coordinator verification:** the coordinator independently inspects commit range, test evidence, worktree status, capability claims, and live Fusion results before accepting a task/phase.

### Executor prompt contract

Every executor job receives one bounded outcome containing:

- exact repository/worktree and task number;
- path to the canonical spec;
- path to the phase plan;
- a task-specific brief containing only that task plus binding global constraints;
- allowed files/subsystems;
- explicit non-goals;
- required tests/debug sweep;
- commit permission state;
- explicit prohibition on push/merge/deploy/restart/topology/credential changes unless separately authorized;
- report-file path and required evidence fields.

The implementer must read `AGENTS.md` and `docs/operations/executor-operating-contract.md` before editing.

### Wake policy

Coordinator wake is **best-effort only**. It is not a correctness or progress dependency.

- Record every executor `job_id` in the phase ledger before any wake attempt.
- `coordinator_wake_on_jobs` may be armed opportunistically, but failure to wake does not imply executor failure and does not trigger a duplicate job.
- Never rely on a future wake as the only way to recover task state.
- Resume from durable `job_status`, terminal `job_output`, Git commits, and the phase ledger.
- Do not short-poll. Check status only after a reasonable idle interval, when the user returns/asks to continue, or when new evidence requires it.
- A missing/failed wake is never a reason to restart an executor job.

### Current executor capability note

At plan creation on 2026-09-04, both Codex and Antigravity were available/authenticated; Antigravity reported fresh `quota_state=ok`. This is evidence for the initial dispatch policy, not a permanent assumption. Future dispatches honor live executor state and the no-retry discipline.

## Worktree and ledger discipline

Implementation must occur in a dedicated worktree created from the accepted canonical `main`, not the runtime checkout. Create a phase ledger under a git-ignored `.superpowers/sdd/<phase-plan>/progress.md` containing:

```text
# SDD ledger — plan: <phase plan path>
BASE: <merge-base sha>
Task N: dispatched <executor> job_<id>
Task N: implemented <commit range>
Task N: review <verdict/findings>
Task N: complete <commit range>
Ruling: <decision> — <reason> — <cost if wrong>
```

The ledger is the recovery source if wake or chat continuation fails.

## Phase Plans

Execute in order:

1. **P0 — Semantic and Visual Foundation**  
   `docs/superpowers/plans/2026-09-04-fusion-cad-agent-api-v1-p0.md`
2. **P1 — Safe High-Level Modeling**  
   `docs/superpowers/plans/2026-09-04-fusion-cad-agent-api-v1-p1.md`
3. **P2 — Advanced Engineering Workflows**  
   `docs/superpowers/plans/2026-09-04-fusion-cad-agent-api-v1-p2.md`

Each phase is independently reviewable and ends in its Schedule golden acceptance gate. A phase plan may refine internal file locations discovered during execution, but it may not weaken the canonical spec or add new scope without a proven architectural blocker and a recorded ruling.

## Shared Domain File Map

The intended decomposition is:

```text
app/fusion_cad/
  __init__.py
  models.py
  requests.py
  schemas.py
  errors.py
  scripts.py
  service.py
  capabilities.py
  revisions.py
  refs.py
  selectors.py
  snapshots.py
  inspect.py
  views.py
  metadata.py
  validation.py
  diff.py
  transactions.py
  recipes.py
  fusion_scripts/
    common.py.txt
    read.py.txt
    inspect.py.txt
    view.py.txt
    mutate.py.txt
    transaction.py.txt
    validate.py.txt
    export.py.txt
```

Existing integration points expected to change:

```text
app/api/errors.py
app/container.py
app/tools/fusion.py
app/tools/registry.py
```

Tests are split by contract/domain responsibility, not by phase-only mega-files.

## Shared Review Gate Per Task

After an implementer reports DONE:

- [ ] Coordinator records task BASE and HEAD.
- [ ] Coordinator creates a bounded diff/review package for BASE..HEAD.
- [ ] Codex reviewer receives task brief + implementer report + diff package + binding global constraints.
- [ ] Review must state both spec compliance and code-quality verdict.
- [ ] Critical/Important findings enter one bounded fix pass; no coordinator hand-edit shortcut.
- [ ] Implementer reruns only affected tests plus required neighboring tests and updates its report.
- [ ] Scoped re-review verifies the fix diff.
- [ ] Coordinator records final verdict/rulings in ledger before the next task.

## Shared Offline Completion Gate Per Phase

Before any live Fusion acceptance:

```bash
pytest -q
git diff --name-only --diff-filter=ACMR "$PHASE_BASE"..HEAD -- '*.py' | xargs -r ruff check --ignore RUF012,TRY004
git diff --check
git status --short
git log --oneline <phase-base>..HEAD
```

Expected:

- full suite PASS;
- Ruff PASS under repository-approved rules;
- `git diff --check` no output;
- worktree contains only intentional changes;
- independent whole-phase review has no unresolved load-bearing finding.

## Shared Live Acceptance Rules

- Use one disposable Schedule copy.
- Confirm active document identity before mutation.
- Record baseline `document_ref`, `model_revision`, and whether the document is modified.
- Do not save the original or acceptance copy unless the owner explicitly requests save.
- Live mutation acceptance is executed once after offline gates are green; repeat only if new evidence requires it.
- Every capability asserted `supported` in release output must have runtime evidence from the installed Fusion/Relay combination.

## Master Completion

The v1 program is complete only when P0, P1, and P2 phase plans are complete, all four implementation invariants are evidenced in tests and live acceptance, and the final Schedule workflow passes without agent-authored raw Python for operations covered by the domain API.
