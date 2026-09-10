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

### Gate

A representative model-edit loop works through the normal facade/provider path:

`observe -> plan -> mutate through Shimmer -> observe/read back -> correct if needed`.

The gate is workflow capability, not percentage coverage of Shimmer's tool catalog.

## Stage C — Ears and mouth: live owner interaction during a model turn

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

After Stages A-D are measured, update the old P0.5/P1/P2 documents so they stop describing greenfield work that donor projects have made unnecessary.

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
