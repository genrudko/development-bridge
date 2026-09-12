# Fusion CAD P2 Research & Design Brief — 2026-09-13

**Status:** authorized for research and architecture/design only. **Do not implement P2 from this brief.**

## Why this brief exists

P0 is closed and the current P0.5/P1 operational loop is live-accepted: Reference + Eyes + Shimmer-backed Hands + Russian Fusion Palette + read receipts + same-turn correction + resilient automatic turn continuation/restart recovery. Normal CAD modeling may continue on canonical `main` while P2 is researched separately.

The old 2026-09-04 P2 plan/spec is historical requirements inventory, not an execution plan. The P2 architecture must be redesigned from measured reuse evidence before implementation begins.

## Required source-of-truth order

1. Actual Git state on canonical `main` and current runtime facts only when a research question truly needs live Fusion.
2. `docs/operations/fusion-cad-executor-guide.md` — current safety and executor operating rules.
3. `docs/research/fusion-cad-agent-operational-roadmap-2026-09-11.md` — measured P0/P1 operational closure and current phase boundary.
4. `docs/research/fusion-cad-reuse-landscape-2026-09-10.md` — existing donor/provider/geometry/slicer research.
5. This brief.
6. Historical P2 files only as a requirements checklist:
   - `docs/superpowers/plans/2026-09-04-fusion-cad-agent-api-v1-p2.md`
   - `docs/superpowers/specs/2026-09-04-fusion-cad-agent-api-v1-design.md`

If historical phase text conflicts with the measured roadmap/reuse findings, the measured/current documents win.

## Research objective

Design the smallest high-value P2 that adds higher-level engineering intelligence **without rebuilding CAD, geometry, slicing, orchestration, or UI systems that already exist**.

P2 should be treated as an **evidence / DFM / recipes layer** over the accepted P0/P1 operating loop, not as a new CAD platform.

## Ready-solution baseline to revalidate, not rediscover from zero

The 2026-09-10/11 research already identified these starting points. Re-check current versions, licenses, activity, APIs, and actual fitness before freezing the design:

- **`jhk-a1/cad-copilot`** — strongest existing donor for typed Command IR, Safe Executor, proof-of-fitness/DFM patterns, persistent feature identity, rollback and one-command/one-undo semantics. Primary candidate for P2 recipe/IR/proof ideas; do not copy architecture blindly.
- **Trimesh** — preferred permissive geometry-analysis dependency. Already proved sufficient for basic proximity/thickness primitives; P2 research must qualify accuracy/performance on representative exported real parts rather than prove API existence again.
- **OrcaSlicer CLI** — optional separately installed external provider for slicer/orientation/arrangement evidence. Treat AGPL boundary deliberately; do not copy/link Orca code into Development Bridge by accident.
- **Autodesk Fusion stable APIs / accepted Shimmer provider** — use for CAD-native facts and operations that already exist. Joints/rigid groups/grounding, named views/sections, interference, export and similar native capabilities are not reasons to build custom P2 subsystems.
- **`faust-machines/fusion360-mcp-server`** — implementation/reference donor for individual Fusion operations/tests when a public-facade gap remains.
- **`er-fo/CADAgent`** — practical Fusion feature-edit/Palette/identity donor, not a replacement backend/orchestrator.
- **`Bhooorya/text-to-cad`** — declarative feature-plan/registry architecture ideas.
- **build123d or CadQuery** — at most one optional offline geometry oracle/fixture generator; do not create a second primary authoring model.
- **lib3mf** — only if P2 truly needs external 3MF inspection/post-processing/validation; Fusion already exports 3MF.
- **Fusion Automation / mature external packing provider** — consider only if high-quality arrangement/nesting evidence is worth the dependency. Do not write a sophisticated nesting solver locally.

Also re-check current user-facing Fusion copilots (Adam AI CAD Copilot, CADAgent, Bevell, Autodesk-native assistant capabilities) only where a real P2 workflow could be deleted by using them. Marketing claims are not implementation evidence.

## Questions the P2 research must answer

1. Which old P2 requirements still create user value after the P0/P1 reuse-first work, and which should be deleted or moved to existing native/provider capabilities?
2. What is the minimal P2 public contract: analysis/evidence operations, versioned recipes, or both?
3. Which facts must come from authoritative Fusion/P0 state, which can come from exported meshes/Trimesh, and which may come from optional slicer/external providers?
4. How should every heuristic result expose method, assumptions, confidence, source/provenance and revision so the model cannot present heuristics as guarantees?
5. What printer/profile schema is actually needed for bed fit, minimum wall/feature, clearance, overhang/bridge/island/orientation evidence without becoming a slicer clone?
6. Can `jhk-a1/cad-copilot` IR/proof ideas map onto the existing `fusion.cad/v1` revision/transaction/provider model, or is a thinner Bridge-owned recipe IR preferable?
7. What P2 operations can remain pure/read-only analysis, and which recipe/mutation workflows truly require new guarded public mutation surfaces?
8. What acceptance evidence proves value on representative real parts while keeping protected owner documents safe?

## Mandatory research method

Use **reuse-first evidence**:

1. Read the existing landscape completely enough to avoid repeating already-settled research.
2. Revalidate candidate repositories/products against current upstream state and official documentation. Record version/commit, license, activity, tests and API constraints.
3. Build a requirement-to-provider matrix for the historical P2 inventory: **reuse / wrap / optional provider / tiny glue / delete**.
4. Run only bounded throwaway spikes needed to discriminate architecture choices. Spikes are evidence, not production code.
5. Compare 2–3 viable P2 architecture shapes with trade-offs and recommend one.
6. Design the public contract, evidence/provenance model, provider boundaries, failure semantics and acceptance strategy.
7. Write the new P2 design/spec only after research supports it. Do not turn the historical P2 plan into an implementation checklist by editing names.
8. Stop before implementation. The implementation plan/worktree is a later owner-approved phase.

## Non-negotiable inherited invariants

P2 may not weaken accepted P0/P1 behavior:

- public `rev_N` freshness and external-change guards;
- opaque public `ent_*` refs and authoritative Reference readback;
- truthful `supported` / `degraded` / `unavailable` capability state;
- `VIEW_STALE` fail-closed behavior;
- ambiguous/non-idempotent mutation => uncertain, no replay;
- preview/abort/commit semantics and no preview-ref leakage;
- provider-session qualification/invalidation;
- no implicit save/close of owner documents;
- protected `Schedule` / historical Golden remain off-limits unless explicitly authorized;
- Palette/continuity are existing infrastructure, not P2 scope.

## Explicit non-goals

Do not propose or implement:

- a new B-Rep/kernel;
- a mini slicer;
- a custom sophisticated nesting/packing engine;
- a second durable jobs/coordinator/backend system;
- a duplicate Fusion authoring model as the normal workflow;
- wholesale wrapping of every Shimmer/Fusion MCP tool;
- literal execution of the frozen 2026-09-04 P2 plan;
- production P2 code during this research/design phase.

## Required deliverables for the separate P2 chat

The research/design chat should finish with:

1. **Fresh reuse matrix** — current candidate/version/license/evidence and exact P2 role.
2. **Requirements disposition matrix** — every meaningful historical P2 requirement marked reuse/wrap/glue/delete/defer.
3. **Recommended P2 scope** — what is actually in v1 P2 and explicit non-goals.
4. **Architecture decision** — components, data/evidence flow, provider boundaries, failure/capability semantics.
5. **Public-contract draft** — operations and result/evidence shapes at the level needed for a design review, not implementation code.
6. **Acceptance strategy** — representative real-part corpus/spikes, accuracy/performance expectations, live Fusion safety gate and final evidence.
7. **New canonical P2 design spec** — clearly superseding the frozen old P2 design assumptions.
8. **No implementation plan until owner reviews/approves the new design.**

## Research branch/worktree discipline

Use a separate clean research/design worktree/branch if repository files must be written, for example `research/fusion-cad-p2-reuse-design`. Do not disturb normal modeling on canonical `main`. Research documents/specs may be committed; P2 production implementation must not start in that worktree unless the owner explicitly changes the phase.

## Current operational baseline to preserve

At creation of this brief, canonical Development Bridge `main` / `origin/main` is `60f0a94562f95b6bcb281251ccc9079002555daa` (`Close Fusion Stage D continuity`). Stage D continuity, restart recovery and boundary batching are closed/green. The final Windows bundle is `FusionBridge-Unified-60f0a94.zip`. Verify actual state on a future chat instead of assuming this SHA remains current.
