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


## 14. Current Eyes/Hands accepted boundary

The reuse-first Hands slice is **live-qualified at its current bounded scope**. Do not revert the documentation or runtime to the earlier assumption that `hands.sketch` / `hands.feature` are merely offline-only. The accepted provider roles remain:

- `reference` — Autodesk/P0; authoritative public `rev_N`, fingerprints, snapshots, opaque refs and post-mutation readback;
- `rich` — pinned Shimmer; accepted rich sketch/feature mutations for the bounded slice;
- `eyes` — optional read-only observation provider when configured.

The model-facing workflow still names the logical workstation, not provider node IDs. Shimmer indices/native tokens remain private. Committed Hands calls keep revision/provider-session guards, preview must restore authoritative state, and ambiguous mutation outcomes remain non-replayable `OPERATION_UNCERTAIN`. The accepted scope still does **not** imply full Shimmer-tool wrapping or sketch/feature actions inside explicit `fusion_transaction` plan/replay.

The source-controlled overlay remains under `ops/fusion_shimmer_overlay/`, pinned to Shimmer commit `97a06e76c289420a721590ddcab334f5f3dc3178`. No save/close behavior is added by the overlay.

## 15. Normal live operator loop: Eyes + Hands + Palette

For an ordinary disposable CAD task, prefer this loop:

1. inspect the active document and current public revision;
2. use Eyes/semantic reads to identify the relevant body/sketch/feature/ref;
3. state the current step and next intended step through the Palette when the task is long enough to benefit;
4. perform the smallest guarded Hands mutation;
5. poll owner Palette messages before the next meaningful CAD step;
6. if the owner corrected the plan, apply that correction in the same model turn when safe;
7. re-observe visually **and** semantically;
8. close the disposable document unsaved when the bounded live exercise is complete.

Palette behavior on the accepted runtime:

- Russian chat UI: **«Диалог с CAD-агентом»**;
- durable `history[]` capped at 50 entries;
- new owner messages get `message_id` and real timestamps;
- `receipt=sent` renders `✓`; an actual `_bridge_palette_poll` marks the message `read`, records `read_at_ms`, and renders `✓✓`;
- Enter sends; Shift+Enter inserts a newline;
- `Остановить после шага` and `Продолжить` remain separate controls.

Do not invent a second owner-message queue. Palette interaction reuses the existing Bridge state path.

## 16. Automatic turn continuation and ACK protocol

When bounded work remains but the current model turn must end, arm one resilient `coordinator_continue` on the already bound route. The next committed user turn must visibly include the exact `cont_*` Bridge reference.

On the fresh model turn, **before other work**:

1. call `coordinator_ack` exactly once for that visible continuation ID;
2. process every returned item in `batched_messages` in the same model turn;
3. inspect the durable task/job/ledger boundary;
4. continue the bounded task;
5. if more model turns are required, arm the next continuation **before ending this turn**.

Do not arm a gratuitous continuation after the bounded task is complete. Do not rely on browser visual refresh as proof that a model turn did or did not start. Durable continuation state, committed-turn evidence and model ACK are authoritative.

The live 2026-09-12 soak completed five sequential automatic transitions in the same bound Project conversation. Four delivered on attempt 1. Transition 5 hit a proven pre-submit `context-timeout` (`composerHasText=false`), was classified as `not_submitted`, retried safely, then produced one committed turn and was ACKed on attempt 2. This is expected resilient behavior, not duplicate delivery.

The continuity repair chain is:

- `3dcef407` — resilient arming / durable continuation ID;
- `ead0c8e` — always-visible Bridge ref;
- `564d9f2` — visible plain continuation instructions;
- `a6ddfd6` — pre-submit context timeout remains retryable even with incidental login text elsewhere in process output.
- `6caf36b` — pre-delivery coalescing never hides batch overflow behind the 500-character visible-reason bound; overflow remains queued and is returned by `coordinator_ack.batched_messages`.
- `3b54c6a` — `bridge_restart` arms a resilient `cont_*` continuation with model ACK and retry semantics instead of the legacy ID-less wake.

A direct transport result of `uncertain` or genuine `owner_input_required` still fails closed and must not auto-resend. A proven `not_submitted` failure may retry according to the resilient continuation policy.

Boundary batching is part of the accepted protocol. If multiple near-boundary messages fit inside the visible continuation reason, they may coalesce there. If the combined payload would exceed the 500-character visible-reason limit, later messages stay in the durable queued batch and are returned exactly through `coordinator_ack.batched_messages`; they must not be dropped or silently truncated. The 2026-09-12 live synthetic probe verified this with `SYNTHETIC_BOUNDARY_CORRECTION_20260912_V2` (`batched_count=1`, exactly once).

## 17. Program boundary: P0/P1 operationally closed; P2 research/design is separate

As of 2026-09-13, executors must distinguish **using the accepted CAD agent** from **designing P2**:

- **P0 is closed.** Do not reopen its acceptance/golden work without new evidence or an explicit request.
- **P0.5/P1 operational loop is closed/accepted at the current measured scope.** Reference + Eyes + Shimmer-backed Hands + Palette/read receipts + same-turn correction + resilient multi-turn continuation/restart recovery are normal operating infrastructure, not a research task.
- **P2 is not implemented.** The owner has authorized a separate P2 **research and architecture/design phase** based on ready-made solutions and the existing reuse landscape. That authorization does not authorize production P2 implementation.

For ordinary modeling, stay on the normal operating loop in sections 14–16 and do not reopen infrastructure qualification by default.

For a P2 research/design task, read `docs/research/fusion-cad-p2-research-design-brief-2026-09-13.md` plus `docs/research/fusion-cad-reuse-landscape-2026-09-10.md` before using the old P2 plan/spec. Revalidate candidate versions/licenses/APIs against current upstream evidence; do not trust a 2026-09-10 README claim merely because it was recorded in the landscape. The historical P2 plan is an inventory of intended outcomes, not the architecture to implement.

P2 research is reuse-first. Prefer native Fusion/Shimmer capabilities, qualified OSS donors, Trimesh analysis and optional external providers over custom subsystems. Preserve all accepted P0/P1 safety, revision, capability, uncertainty, provider-session and no-save invariants in the eventual design.

Research spikes must be bounded and throwaway unless a later owner-approved implementation phase promotes them. The P2 research/design phase ends with a reviewed new design/spec and acceptance strategy; it must **not** silently continue into implementation.
