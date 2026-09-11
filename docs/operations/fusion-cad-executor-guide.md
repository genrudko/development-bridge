# Fusion CAD Executor Guide

This runbook applies to any coding/review executor working on `fusion.cad/v1` or its Development Bridge/Fusion transport.
It complements `AGENTS.md`, `docs/operations/executor-operating-contract.md`, the canonical Fusion CAD design spec, and `docs/operations/fusion-cad-agent-acceptance.md`.

## 1. Operating principle

Treat `fusion.cad/v1` as the normal agent interface to Autodesk Fusion.
The Windows relay and Autodesk local Fusion MCP are transport infrastructure, not the primary modeling API for executor work.

Default to the public semantic tools:

- `fusion_read` — model snapshots, feature/sketch reads, revisions, selectors, capabilities;
- `fusion_inspect` — measurements, geometric relations, clearances;
- `fusion_view` — camera, screenshots, visual pick, named/section views when capability allows;
- `fusion_metadata` — tags, roles, provenance;
- `fusion_style` — text, visibility, appearance operations that are actually capability-supported;
- `fusion_validate` — model hygiene, reference integrity, mechanical validation;
- `fusion_transaction` — staged mutation, preview, diff, rollback/abort, commit.

Use `fusion_tools`, `fusion_call`, `fusion_submit`, raw `fusion_mcp_execute`, or direct Autodesk Python only as an escape hatch for bounded diagnosis, transport repair, or a task that explicitly requires them. Do not replace a working semantic path with raw Python because raw execution appears easier.

## 2. Owner interaction boundary

The owner is not the Fusion API designer or implementation debugger.
Executors are expected to make ordinary low-level engineering choices themselves from repository/runtime evidence.

Do **not** ask the owner to choose:

- Autodesk API method names or object-model details;
- internal helper structure;
- selector/ref implementation details;
- test mechanics;
- error-decoder/transport implementation details;
- ordinary TDD/debugging decisions.

Ask the owner only when a genuine owner decision is required, for example:

- permission to modify or save a protected/original Fusion document;
- permission to push, merge, deploy, restart a service, or alter topology when not already granted;
- choosing between materially different user-visible behavior, risk, destructive scope, cost, or product direction;
- accepting a proven limitation that changes the requested outcome.

A technical difficulty is not automatically an owner blocker. Diagnose it first.

## 3. Required start state

Before changing Fusion CAD code:

1. Read `AGENTS.md` and `docs/operations/executor-operating-contract.md`.
2. Read the relevant current Fusion spec/plan and `docs/operations/fusion-cad-agent-acceptance.md`.
3. Inspect exact branch/HEAD/status and the intended worktree. Do not modify unrelated dirty state.
4. For live work, check `fusion_node_status` first. Confirm the target node is online, `fusion_available=true`, and inspect `pending_commands` plus `uncertain_operations`.
5. If the Fusion runtime or relay session changed, read `fusion_read(operation="capabilities")` before depending on a capability. Do not infer support from class/API presence alone.

For destructive or acceptance mutations, use a disposable document/copy unless the task explicitly authorizes the original.

## 4. Capability honesty is load-bearing

Capability state is part of the contract:

- `supported` — the requested contract path may be used;
- `degraded` — do not silently bypass the limitation with an unverified alternate path;
- `unavailable` — fail closed; do not pretend the feature exists.

A capability may be `degraded` even when an Autodesk class or method exists. Runtime proof can be stricter than API presence.

When a public semantic tool returns `CAPABILITY_DEGRADED` or a documented unavailable result that agrees with the capability matrix, that is correct behavior, not a reason to force a raw workaround.

## 5. Revision and mutation safety

Revision freshness is mandatory for mutation paths that require `expected_revision`.
The authoritative model fingerprint is the external-change guard; a stale caller must fail with `REVISION_CONFLICT` before applying staged geometry/provenance.

Do not weaken or bypass revision checks to make a live test pass.

Prefer the transaction lifecycle for grouped changes:

1. begin;
2. stage deterministic mutations;
3. preview;
4. inspect diff/validation/evidence;
5. abort/rollback if not committing, or commit once accepted.

Preview state is non-durable. Preview-only refs/provenance must not be treated as persistent after abort.

If an acceptance test requires `commit -> Undo` to prove reversibility, the Undo must be the immediate next Fusion command after terminal commit. Do not insert screenshots, reads, raw probes, or other Fusion commands between commit and that Undo because they may occupy command-stack frames.

## 6. Timeout and uncertain-result discipline

Assume live CAD mutations are non-idempotent unless explicitly proven otherwise.

After a timeout, disconnect, or ambiguous result from a mutation:

- do **not** replay the mutation;
- read operation status/result first;
- inspect `uncertain_operations`;
- inspect the model/revision if needed;
- decide from evidence whether the mutation applied.

A read may be repeated after a documented retryable transport failure. A mutation may not be repeated merely because no response was observed.

## 7. View freshness

`view_ref` is tied to the captured view/model state.
Camera/viewport changes and effective model visibility changes can invalidate a prior view.

`VIEW_STALE` is expected fail-closed behavior. On `VIEW_STALE`, acquire a fresh screenshot/view context before attempting pick/raycast again. Do not suppress the stale check.

## 8. Protected documents and saving

Saving is an explicit owner action unless the current task grants it.

Never save or overwrite an original/protected design merely to make acceptance easier. When using `Schedule` or any other owner document for live acceptance, prefer a disposable copy and record its stable document ref/fingerprint.

Do not interpret `Document.isModified=true` by itself as proof that the current task caused the dirty state unless a baseline was recorded before the task.

## 9. Current Autodesk Fusion MCP transport behavior

As of the 2026-09-10 accepted runtime, Autodesk Fusion MCP `fusion_mcp_execute` uses the structured input shape:

```json
{"featureType":"script","object":{"script":"..."}}
```

Its script runner accepts the Bridge-owned `run(_context=None)` entrypoint but does not reliably return Python stdout/return values to the caller.

Development Bridge therefore has a strict internal result transport for semantic scripts. Bridge-owned `fusion.cad/v1` scripts can emit a reserved `BRIDGE_CAD_RESULT_V1:<base64url-json>` marker through the native traceback channel; server-side code validates and decodes only that exact reserved protocol and still treats all other native exceptions as ordinary failures.

Executors must not:

- switch public domain tools back to legacy `{"script": ...}` arguments;
- assume `print()` is a reliable public result channel on the current runtime;
- manually parse arbitrary tracebacks as successful domain results;
- broaden the reserved marker parser or weaken normal error sanitization;
- require a Windows Relay rewrite when the existing server-side transport already satisfies the public path.

Large public semantic results may be externalized through the existing retained external-result mechanism instead of being returned inline. That is normal.

## 10. Raw Fusion MCP use

Raw `fusion_mcp_execute` is diagnostic/escape-hatch infrastructure.
If raw execution is required:

- use an exact bounded script;
- record journal metadata for important operations;
- set `mutation=true` for real mutations;
- do not save unless explicitly authorized;
- do not replay an uncertain mutation;
- restore disposable acceptance changes if the task requires restoration;
- label diagnostic raw failures separately from product-domain failures.

Do not claim a public `fusion.cad/v1` feature works merely because a hand-written raw Python probe works. Public acceptance must exercise the public semantic tool.

## 11. Verification before handoff/deploy

For a Fusion CAD implementation or repair, verification should attempt to falsify the change:

1. reproduce the original bug/acceptance condition;
2. run focused RED -> GREEN tests for the changed contract;
3. run the nearest Fusion regression contour;
4. run Ruff/static checks and `git diff --check`;
5. inspect the final relevant diff and worktree status;
6. for changes crossing the domain/desktop transport boundary, run the full repository test suite before deploy;
7. only after offline checks are green, run the smallest required live acceptance.

For a deployed transport/domain change, the minimum live smoke is:

- public `fusion_read(operation="capabilities")` succeeds;
- one normal public semantic read succeeds (for example `feature_tree`);
- one truthful degraded/unavailable path is exercised when relevant;
- `fusion_node_status` ends with `pending_commands=0`, `uncertain_operations=[]`, healthy result delivery/outbox;
- Git/deployment HEAD is the intended commit.

Do not substitute an exact-source loader/raw script acceptance for the final deployed public-tool smoke.

## 12. Evidence and handoff

Return compact evidence, not a diary:

- exact HEAD/branch/worktree;
- what behavior changed and why;
- targeted and neighboring test results;
- full-suite result when required;
- live public-tool evidence when required;
- final node `pending/uncertain` state;
- whether any original document was saved/modified;
- commit/push/deploy state;
- only real remaining blockers or owner decisions.

Do not call coordinator self-review an independent review. If an independent review requirement was explicitly waived/replaced by the owner, record that fact accurately.

## 13. P0 accepted baseline (historical reference)

P0 is closed. Do not reopen Task 14 or rerun the golden acceptance without new evidence or an explicit request.

Accepted/deployed baseline on 2026-09-10:

- final deployed `main`: `93ddfcf6cac767f1db9ba4c1fe4c750cb19fdc20`;
- Fusion runtime observed: `2704.1.53`;
- public `fusion_read(capabilities)` succeeded through `fusion.cad/v1`;
- public `fusion_read(feature_tree)` succeeded and exercised large external-result spill;
- final node state: online, `pending_commands=0`, `uncertain_operations=[]`, result delivery healthy/outbox `0`;
- full repository suite after the final transport repair: `2108 passed`;
- final transport repair also passed the focused transport tests and the Fusion regression contour.

At that runtime, load-bearing P0 capabilities such as `view.pick`, `transaction.preview_replay`, `style.text_read`, `style.text_update`, and `revision.external_change_detection` were `supported`. Some capabilities remain honestly `degraded` or `unavailable`; for example interactive selection primitives were degraded, while DXF export, section-view contract semantics, and assembly joints remained unavailable/P2-gated.

This SHA/capability list is historical acceptance evidence, not a permanent assumption. Re-probe capabilities after runtime changes.


## 14. P1 Hands offline-qualified boundary

The first reuse-first Hands slice is implemented and offline-qualified, but it is **not live-qualified yet**. Keep `hands.sketch` and `hands.feature` capability state `degraded` until the dedicated live gate succeeds on the installed Fusion/Shimmer runtime.

Provider roles are explicit and configuration-owned:

- `reference` — the accepted Autodesk/P0 provider and authoritative source of public `rev_N`, fingerprints, snapshots and post-mutation readback;
- `rich` — the pinned Shimmer provider used for the first rich modeling mutations;
- `eyes` — an optional read-only observation provider when configured.

The model-facing request continues to name the logical workstation. Do not expose or require provider node ids in normal agent workflows. Hands bindings are private and scoped by rich provider + document + public revision, and are invalidated on provider-session changes.

The offline-supported public Hands surface is deliberately narrow:

- `fusion_sketch(operation="create")` on `xy`, `xz`, `yz`, or an opaque planar-face ref;
- `fusion_sketch(operation="batch")` for line, rectangle, circle, geometric constraints and driving dimensions, including symbolic references only to earlier geometry actions in the same batch;
- `fusion_feature(operation="create")` for `extrude`, `hole`, `fillet`, and `chamfer`;
- `dry_run=true` through the guarded Shimmer preview/abort path.

Committed Hands calls require `expected_revision`. Bridge binds a private Shimmer guard around an authoritative P0 observation, checks the rich-provider session generation atomically at dispatch, and treats ambiguous post-dispatch/post-commit outcomes as non-replayable `OPERATION_UNCERTAIN`. Provider native tokens and Shimmer indices remain private; public results use existing opaque `ent_*` refs only after exact authoritative post-commit snapshot attestation. Preview-created refs are never published.

The source-controlled overlay lives under `ops/fusion_shimmer_overlay/` and is pinned to Shimmer commit `97a06e76c289420a721590ddcab334f5f3dc3178`. Its installer fails closed on upstream SHA or target-hash mismatch. The overlay delegates geometry work to Shimmer's existing allow-listed operations; it is not a second CAD implementation and it does not expose arbitrary-code dispatch or save/close behavior.

This slice does **not** add sketch/feature actions to `fusion_transaction` plan/replay. Standalone commit and `dry_run` are the only qualified Hands mutation semantics until the live gate is green and later work explicitly extends transaction replay.

Before reporting Hands as `supported`, run the live disposable-model gate and prove: provider guard coherence against manual external edits, session/reconnect invalidation, preview restoration, public `fusion_sketch` and `fusion_feature` commit paths, authoritative post-readback/ref attestation, and no mutation/save of the protected original document.
