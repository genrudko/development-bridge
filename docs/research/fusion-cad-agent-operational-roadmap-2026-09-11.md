# Fusion CAD Agent Operational Roadmap — 2026-09-11

## Goal

Build a practical Fusion CAD agent for ChatGPT-class models with **eyes, ears, hands, and continuity**, while reusing existing software aggressively and writing the minimum amount of custom code.

The immediate objective is not P2 intelligence or a broad CAD platform. It is one reliable operational loop:

1. inspect and understand the current Fusion model;
2. modify it through proven CAD capabilities;
3. show the owner what is happening and accept corrections during the same model turn;
4. verify the result visually and semantically;
5. continue automatically into another model turn when more work remains, without requiring an owner message.

P2 is intentionally deferred until this loop works end-to-end.

## Measured status — 2026-09-12

- **P0: CLOSED.** The reference/control foundation is accepted and must not be reopened without new evidence.
- **Stage A: CLOSED.** A live disposable-model exercise combined viewport and semantic observation, detected an intentional 1.5x wrong result (45 x 30 x 15 mm instead of 30 x 20 x 10 mm), then verified the Undo restoration.
- **Stage B current slice: LIVE-ACCEPTED at its bounded scope.** The Shimmer-backed Hands path is deployed for the accepted sketch/feature slice, while Autodesk/P0 remains authoritative for public revisions, fingerprints, refs and post-mutation readback. This does not imply full wrapping of Shimmer's catalog or transaction-plan/replay expansion.
- **Stage C: CLOSED.** The Russian Fusion Palette supports same-turn owner corrections, durable chat history and read receipts. A live owner correction changed the active CAD plan in the same model turn; no second ChatGPT user turn was required.
- **Stage D: CLOSED / GREEN.** Five sequential automatic continuation turns completed in the same bound Project conversation. Transitions 1-4 delivered on attempt 1; transition 5 hit a proven pre-submit `context-timeout`, safely retried, then produced one committed turn and ACKed on attempt 2. No transition 6 was armed.
- **Boundary batching: GREEN.** A separate synthetic coordinator boundary probe preserved `SYNTHETIC_BOUNDARY_CORRECTION_20260912_V2` across the turn boundary: continuation `cont_PSYknTM7uBzjHX9w3ZvJgv-e` ACKed with `batched_count=1`, the payload appeared exactly once in `batched_messages`, and delivery completed on attempt 1. This is coordinator batching evidence, not a Fusion Palette message.

Continuity repairs proven during Stage D:

1. `3dcef407` — `coordinator_continue` now arms resilient continuations with a durable `cont_*` ID and model ACK requirement.
2. `ead0c8e` — the visible wake message always carries the exact Bridge continuation reference even when model-context injection reports success.
3. `564d9f2` — plain `coordinator_continue` instructions remain visible instead of collapsing to a generic completion message.
4. `a6ddfd6` — a `context-timeout` with `composerHasText=false` is classified as proven pre-submit `not_submitted`, even if unrelated output contains incidental login text; it may retry instead of becoming terminal `owner_input_required`.
5. `6caf36b` — continuation payload that would overflow the 500-character visible reason is preserved as queued coordinator batch data and returned through `coordinator_ack.batched_messages` instead of being silently truncated.
6. `3b54c6a` — `bridge_restart` now arms the same resilient `cont_*` continuation contract, so post-restart direct delivery no longer creates an undeliverable legacy wake without a continuation ID.

## Non-negotiable rule: reuse first

For every missing capability, use this order:

1. existing Shimmer capability;
2. official Autodesk Fusion/Fusion MCP capability;
3. permissively licensed donor such as Faust or another already-qualified project;
4. another mature external tool/project;
5. only then, a minimal local adapter or implementation.

Do **not** build a second CAD toolset, MCP transport, Windows Relay, durable job engine, coordinator, slicer, B-Rep kernel, nesting solver, or other subsystem that already exists and works.

Existing P0 safety behavior that is already useful stays in place, but new governance/security layers are not an objective of this roadmap.

## Current proven baseline

- Official Autodesk provider remains the accepted P0/reference provider.
- Pinned Shimmer has passed live qualification on the installed Fusion runtime.
- A second unchanged Windows Relay instance is live as `fusion-shimmer`.
- Shimmer exposes 103 MCP tools through the real Relay/Bridge path.
- Representative live sketch, constraints, driving dimension, extrude, fillet, component/occurrence, as-built joint, screenshot/readback and STEP export succeeded.
- The original `Schedule` document remained saved and `is_modified=false` after disposable qualification.
- One Shimmer contract defect is known: `fusion_sketch_dimension` advertises `entity_two` as optional where the runtime requires it for several dimension modes. The future adapter must normalize this rather than reproduce the bad contract.
- ReviewGPT already provides a production direct-wake transport capable of creating a committed user turn in the exact bound ChatGPT Project conversation from the VPS.

## Stage A — Maximize the agent's eyes

**Status: CLOSED on live disposable-model evidence.**

### Purpose

Give the model as much useful observability as practical. More vision is desirable if it comes from existing providers/APIs rather than a large custom subsystem.

### Research targets

Inventory and live-qualify the best available combination of:

- viewport screenshots and alternate camera views;
- fit/zoom/orbit/view orientation controls;
- component/occurrence/body/sketch/feature tree readback;
- faces, edges, vertices and stable references/selectors where available;
- bounding boxes, dimensions, parameters and physical properties;
- selections/highlights and any mechanism that links a visible object to a CAD entity;
- measurements, distances, clearances and interference;
- Named Views;
- Section Analysis / sectional inspection;
- visibility/isolation controls;
- geometry/topology summaries that help the model verify what it changed;
- any useful existing visual/semantic tools in Shimmer, official Fusion APIs, Faust or other qualified donors.

### Gate

On a disposable or safe test model, the model must be able to:

1. inspect the model using several independent observation methods;
2. identify the relevant component/body/feature/face rather than rely only on pixel location;
3. perform a change;
4. re-observe the result visually and semantically;
5. detect an intentionally wrong result or discrepancy with enough evidence to correct it.

Do not stop at the minimum screenshot capability if richer ready-made observation tools are available.

## Stage B — Finish the hands without rebuilding CAD

### Purpose

Make Shimmer the rich P1 CAD provider while keeping `fusion.cad/v1` as the stable agent-facing seam.

### Work

- Map only the operations needed by actual workflows; do not wrap all 103 tools up front.
- Normalize obvious provider contract defects such as the `fusion_sketch_dimension.entity_two` mismatch.
- Use official Autodesk/P0 readback or another provider where it gives stronger verification.
- When a needed operation is weak/missing in Shimmer, search qualified donors before implementing it locally.
- Keep provider choice hidden from the model-facing workflow where practical.

### Current accepted implementation status

The first Stage B facade slice is implemented and live-accepted behind the existing logical workstation contract. It adds public `fusion_sketch` and `fusion_feature` operations backed by a pinned Shimmer rich provider, while Autodesk/P0 remains the authoritative reference provider for public revisions, fingerprints and post-mutation readback.

The accepted slice covers sketch create/batch plus extrude, hole, fillet and chamfer, with guarded preview/abort. Bridge keeps Shimmer indices/native tokens private, resolves public `ent_*` refs fail-closed, scopes private guard bindings by rich provider/document/revision, checks provider session generation at dispatch, and publishes output refs only when the exact authoritative post-commit snapshot attests the provider token and kind. Ambiguous outcomes after dispatch/commit remain non-replayable `OPERATION_UNCERTAIN`. The source-controlled overlay is pinned to Shimmer `97a06e76c289420a721590ddcab334f5f3dc3178`.

The live gate also drove follow-up repairs for native ref resolution, sketch token precedence, component token preservation and preview rollback/revision reconciliation. This bounded acceptance does **not** claim sketch/feature support inside explicit `fusion_transaction` plan/replay, nor does it claim complete coverage of Shimmer's 103-tool catalog.

### Gate

A representative model-edit loop works through the normal facade/provider path:

`observe -> plan -> mutate through Shimmer -> observe/read back -> correct if needed`.

The gate is workflow capability, not percentage coverage of Shimmer's tool catalog.

## Stage C — Ears and mouth: live owner interaction during a model turn

**Status: CLOSED on live same-turn owner-correction evidence.**

### Purpose

Allow the owner and the model to communicate while a long model turn is still in progress.

### Preferred implementation direction

Reuse the Fusion Palette API plus existing Development Bridge durable state/SSE/coordinator services. Do not create another agent backend or another message queue.

The first useful Palette can stay deliberately small:

- current activity / current CAD step;
- next intended step;
- owner text input;
- Send correction;
- Stop after current atomic step;
- Continue/Resume where needed;
- clear indication whether the agent has received the latest owner message.

### Gate

During one real model turn:

1. the model starts a multi-step disposable CAD task;
2. the Palette shows what it is doing;
3. the owner sends a correction before the turn ends;
4. Bridge delivers that correction into the active work loop;
5. the model changes its plan and applies the correction in the same turn;
6. no second user chat turn is required to deliver the correction.

## Stage D — Automatic turn-to-turn self-continuation

**Status: CLOSED / GREEN — 5/5 live continuation soak plus boundary-batching probe accepted.**

### Purpose

Remove the final manual "poke" needed when a model turn ends but the bounded task is not finished.

### Reuse target

Reuse the existing coordinator + ReviewGPT wake stack. The existing `coordinator_continue` path can arm a delayed continuation for an already mounted/bound route, and ReviewGPT already performs exact-thread preflight and sends only when the target chat is idle/not generating.

Do not build another wake transport unless live evidence proves the existing path cannot support this use case.

### Required behavior

Before finishing a turn that still has bounded work remaining, the model arms a tiny self-continuation checkpoint. After the current turn becomes idle, ReviewGPT creates the next committed user turn in the same bound Project conversation. The next model turn ACKs the continuation, recovers any batched messages/state, and resumes from the durable task boundary.

### Gate

Run a live soak with **at least 5 sequential automatic turn transitions**:

- no owner message between transitions;
- same physical bound Project conversation;
- one committed continuation per transition;
- no duplicate or out-of-order turns;
- no delivery while the previous model turn is still generating;
- each new turn ACKs its continuation and resumes the correct bounded task;
- owner corrections queued near a boundary are preserved/batched rather than lost;
- failure/uncertain delivery remains diagnosable from Bridge state and receipts.

The browser UI not visually refreshing is a separate presentation issue; it must not block the actual continuation from starting.

## Stage E — Rewrite the old phase plans to match reality

Stages A-D are now measured. The old greenfield P0.5/P1/P2 plans/spec are historical references only and are explicitly superseded by this measured operational roadmap for current execution.

Expected phase meaning:

- **P0:** proven base/control/reference provider — already complete.
- **P0.5/P1 immediate objective:** one operational agent loop with rich observation, Shimmer-backed CAD actions, live owner dialogue and automatic turn continuation.
- **P2:** deferred higher-level intelligence and manufacturing/printability features using Trimesh, OrcaSlicer and other mature projects where useful.

Do not start P2 implementation before the Stage A-D end-to-end gate is green unless the owner explicitly changes priorities.

## Final current-stage acceptance

The current stage is complete only when a real end-to-end disposable CAD exercise proves all of the following without technical intervention from the owner:

1. the model sees enough of the design to understand what it is editing;
2. it can perform the required CAD edits mostly through reused Shimmer/other provider capabilities;
3. it can show progress and receive an owner correction during the same turn;
4. it can verify its own result with visual plus semantic evidence;
5. if the turn ends before the bounded task is complete, the next turn starts automatically and resumes correctly;
6. the workflow can repeat across several turns without owner "poke" messages.

Only after this gate is green do we expand into P2.

## Immediate execution order

1. Complete the observability/vision capability inventory and live probes.
2. Identify only the provider/facade gaps exposed by those real workflows.
3. Research and spike the minimal Palette interaction path using existing Bridge state/SSE/coordinator primitives.
4. Live-prove same-turn owner correction.
5. Live-prove `coordinator_continue` + ReviewGPT self-continuation and run the 5-transition soak.
6. Rewrite superseded phase plans from measured results.
7. Build only the minimal remaining glue needed for the final end-to-end acceptance.
