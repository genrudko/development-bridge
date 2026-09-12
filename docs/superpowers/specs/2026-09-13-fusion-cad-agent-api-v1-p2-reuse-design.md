# Fusion CAD Agent API v1 P2 — Reuse-First Canonical Design

**Date:** 2026-09-13
**Status:** owner-approved architecture/design; **not implementation authorization**
**Branch:** `research/fusion-cad-p2-reuse-design`
**Research baseline:** `c4cfba1232c47325e52cd3f9852aa60c7db8ac43`
**Research evidence:** `docs/research/fusion-cad-p2-reuse-provider-evidence-2026-09-13.md`

## 1. Purpose and authority

This document is the canonical P2 architecture/design for Fusion CAD Agent v1. It supersedes the **P2 greenfield assumptions** in:

- `docs/superpowers/plans/2026-09-04-fusion-cad-agent-api-v1-p2.md`;
- the P2 sections of `docs/superpowers/specs/2026-09-04-fusion-cad-agent-api-v1-design.md`.

The accepted P0/P0.5/P1 safety model remains authoritative and is not redesigned here. If this document conflicts with measured current P0/P1 behavior, actual accepted runtime behavior plus the current operational guide wins and this P2 design must be corrected before implementation.

This design records the owner-approved **Option A**:

> a thin revision-bound Evidence layer, Fusion/Shimmer as CAD authority, Trimesh as local mesh-evidence provider, OrcaSlicer/Fusion Automation only as optional external providers, a tiny declarative recipe layer, and an optional Orca-backed Print Preparation stage.

P2 implementation planning and production code are a later, separately approved phase.

## 2. Product boundary

P0/P0.5/P1 already provide the working operational loop: authoritative Reference, Eyes, Shimmer-backed Hands, Palette/read receipts, same-turn correction, transaction/revision safety where genuinely supported, and resilient continuation/restart recovery.

P2 therefore adds **engineering intelligence around that loop** rather than another CAD platform.

P2 has four responsibilities:

1. **Revision-bound engineering evidence** over authoritative Fusion state.
2. **Provider composition** with explicit provenance and capability honesty.
3. **Versioned recipe intent** over existing semantic CAD operations without a second executor.
4. **Print Preparation** that can turn a revision-bound neutral model artifact into a reproducible Orca print project for a qualified printer/nozzle/filament configuration and a declared print objective.

## 3. Explicit non-goals

P2 does not build or own:

- a B-Rep/kernel;
- a second CAD authoring model;
- a slicer implementation;
- a sophisticated local nesting/packing solver;
- a second transaction/Safe Executor substrate;
- another durable jobs/coordinator/backend;
- another generic in-Fusion copilot/UI;
- wholesale wrappers for all Fusion/Shimmer tools;
- implicit document save/close;
- direct mutation of protected owner documents for acceptance;
- global mathematical guarantees from sampled or tessellated mesh heuristics;
- a claim of globally “optimal” print settings.

Print Preparation selects the **best qualified candidate among the candidates actually evaluated for a declared objective**. It may not relabel that result as a global optimum.

## 4. Inherited non-negotiable invariants

All P2 operations inherit the accepted P0/P1 invariants:

- public `rev_N` freshness and external-change guard;
- opaque public `ent_*` identity;
- authoritative Reference readback;
- truthful `supported` / `degraded` / `unavailable` capabilities;
- `VIEW_STALE` fail-closed behavior;
- ambiguous/non-idempotent mutation => uncertain, no replay;
- preview isolation and no preview-ref leakage;
- provider-session qualification/invalidation;
- no hidden save/close;
- no protected `Schedule` / historical Golden mutation without explicit owner authorization.

P2 analysis cannot use a stale mesh/export to justify a current-model conclusion without carrying the exact source revision and artifact hash.

## 5. High-level architecture

```text
Authoritative Fusion document @ rev_N
        |
        +--> Reference / native stable facts ------------------+
        |                                                       |
        +--> neutral revision-bound mesh / 3MF artifact ------+ |
                                                               | |
                       P2 Evidence facade <--------------------+ |
                         |              |                        |
                         |              +--> Trimesh provider ---+
                         |              +--> optional Orca evidence
                         |              +--> optional Fusion Automation
                         |
                         +--> evidence/provenance envelope
                         +--> recipe planning/proof metadata
                         +--> Print Preparation
                                  |
                                  +--> qualified machine/nozzle preset
                                  +--> qualified filament preset
                                  +--> process objective + bounded overrides
                                  +--> bounded candidate search
                                  +--> Orca CLI separate process
                                          |
                                          +--> print-project.3mf
                                          +--> effective-settings.json
                                          +--> slice/provider evidence
```

Fusion/Shimmer owns CAD truth and mutation. Trimesh owns only mesh-derived evidence. Orca owns slicer semantics. Fusion Automation owns any optional cloud arrangement/nesting semantics. Bridge owns normalization, revision binding, evidence composition, policy, bounded candidate selection, and public contracts.

## 6. Provider boundaries

### 6.1 Fusion / Shimmer

Fusion/Shimmer is authoritative for document identity/revision, `ent_*` mapping, native CAD facts, mutations, post-operation readback, and neutral STL/3MF/STEP export already covered by the accepted facade.

P2 does not duplicate native joints, rigid groups, grounding, named views, sections, interference, export, or other stable capabilities merely to place them under a P2 namespace.

### 6.2 Trimesh

Trimesh consumes a **revision-bound exported mesh artifact** and returns derived evidence. It may never invent CAD identity or silently promote sampled mesh evidence to authoritative CAD truth.

Every result records source revision/refs, artifact SHA-256, tessellation/export settings, Trimesh version, method/parameters, sampling budget, assumptions and limitations.

### 6.3 OrcaSlicer

OrcaSlicer is an **optional external executable provider**, invoked as a separate process. Development Bridge does not copy or link Orca AGPL code into its runtime by default.

The current CLI surface supports headless machine/process and filament setting loads, arrangement/orientation, slicing, project 3MF export, and effective-settings export. P2 relies only on capabilities qualified against the exact installed Orca version.

A historical Orca 2.3.x/2.4.2 CLI regression caused inherited preset chains to be loaded incompletely and silently fall back to hardcoded defaults. The issue is now closed upstream, but the failure mode is load-bearing evidence: P2 **must never trust a preset name or leaf JSON alone**. Provider qualification and every prepared result must prove the effective settings actually used.

### 6.4 Fusion Automation / CadQuery / lib3mf

Fusion Automation is optional for mature arrangement/nesting only. CadQuery is test-only ground truth/fixture generation. lib3mf remains deferred until an external 3MF validation/manipulation gap is proven.

## 7. Evidence and claim model

Every finding has one claim class:

- `authoritative` — direct stable Fusion/P0/P1 fact at the exact revision;
- `deterministic_derived` — exact derivation from explicit bounded inputs;
- `heuristic` — sampled/tessellated/geometric classification;
- `provider_reported` — external provider result such as Orca/Fusion Automation.

Only heuristic/provider findings may carry categorical confidence `high|medium|low`, always with a `basis`. Numeric pseudo-probabilities are not part of the public contract.

Provenance includes as applicable: `document_ref`, `model_revision`, source `ent_*`, artifact hash, provider+version, tessellation settings, process-profile hash, build frame/direction, method/parameters, analysis budget, assumptions/limitations, and evidence artifact refs.

`GREEN` means no problem was found **within executed checks and method bounds**. It never means “guaranteed printable.”

## 8. FDM evidence scope

| Check | Source / semantics |
| --- | --- |
| Bed fit | authoritative current orientation/frame + deterministic bed bounds; candidate orientations may use mesh evidence |
| Minimum wall | Trimesh heuristic with explicit mesh quality/sampling; not a global guarantee |
| Minimum feature | only explicitly defined measurable checks; otherwise `not_assessed` |
| Overhang | mesh face-normal/area heuristic relative to explicit build direction |
| Bridge candidates | local geometric candidate evidence; optional Orca may add slicer behavior |
| Unsupported islands | slicer/layer-order semantics; `not_assessed` without an eligible slicer provider |
| Print clearance | distinguish CAD geometric clearance from material/process printable-clearance policy |
| Orientation | decomposed component metrics; local heuristic plus optional Orca evidence |

Static mesh connectivity is not accepted as proof of layer-order unsupported islands.

## 9. Printer / nozzle / filament / process model

P2 uses a small versioned profile model. It is **not a slicer clone**.

### 9.1 Machine/nozzle profile

Records printer/profile identity, nozzle diameter/variant, printable region where needed, compatible Orca machine preset identity, profile version/hash, and provider qualification state. Machine safety limits are profile-owned and are never changed by automatic optimization.

### 9.2 Filament profile

Records material family, vendor/product identity when known, compatible Orca filament preset identity, compatibility constraints, profile version/hash, and qualification evidence.

Thermal/calibration-sensitive values such as temperature, flow ratio, pressure advance, retraction, and maximum volumetric flow are **qualified printer/filament calibration data**, not guessed optimization variables by default.

### 9.3 Print objective

One explicit objective is selected and recorded in provenance: `balanced`, `best_quality`, `functional_strength`, `dimensional_accuracy`, or `fast_draft`. The objective drives deterministic candidate ranking.

### 9.4 Bounded override policy

Automatic candidate generation may modify only an allowlisted set of process/orientation settings within profile-defined bounds. Initial candidates may include orientation, layer height within nozzle/profile limits, wall/perimeter count, sparse infill density/pattern, support policy, and provider-supported bridge/overhang parameters that the profile explicitly permits.

The optimizer may not silently change machine safety limits, nozzle identity, filament thermal/calibration values, or any setting not explicitly allowlisted.

## 10. Print Preparation

Print Preparation is a small optional provider-backed stage. It does not replace `fusion_export` and does not mutate the Fusion document.

### 10.1 Inputs

A request binds the exact Fusion revision or revision-bound neutral artifact, target bodies/occurrences, machine/nozzle profile, filament profile, base process profile, print objective, optional user-pinned overrides, candidate-search budget, and provider policy.

### 10.2 Artifacts

P2 preserves a two-artifact boundary:

1. **Neutral `model.3mf`** — geometry/export artifact bound to the Fusion revision and usable independently of Orca-specific decisions.
2. **Prepared `print-project.3mf`** — Orca project artifact with selected machine/nozzle/filament/process configuration and print-preparation state.

The result also retains `effective-settings.json`, provider diagnostics, candidate metrics/ranking evidence, exact Orca version, and hashes of input artifact, presets, effective settings, and output project.

Optional future printer-output artifacts are capability-gated and are not required for the initial P2 contract.

### 10.3 Candidate selection

P2 may evaluate a bounded set of qualified candidates. Each candidate differs only in allowlisted orientation/process settings and is actually passed through Orca slicing/validation whenever slicer evidence is required.

Candidate evidence may include provider-reported print time, material use, support material/volume where available, plate validity/errors, layer/support/island behavior, and other exact metrics exposed by the qualified provider.

Bridge computes selection deterministically from the declared objective and explicit component metrics. The result returns the evaluated candidate set, selected candidate, ranking rationale/trade-offs, and whether the requested search budget completed.

Public language is **selected best candidate among evaluated candidates**, never globally optimal.

### 10.4 Effective-settings verification

A successful preparation is not proven by an Orca zero exit code alone. It must verify the effective configuration actually used:

- export/read back Orca effective settings;
- check expected machine/nozzle identity sentinel fields;
- check filament/process sentinel fields;
- hash the resulting effective settings;
- fail closed on missing/incompatible/ambiguous profile resolution;
- record any CLI/provider limitation.

This specifically guards against preset-inheritance/provider regressions and accidental fallback to slicer defaults.

### 10.5 Owner pilot configuration

The initial real acceptance target is the owner's Flashforge AD5X workflow using **versioned, explicitly qualified** machine/nozzle/filament presets. P2 remains generic, but the first production-quality acceptance must prove the path on at least one actual owner configuration instead of only synthetic profiles.

Additional nozzle/material combinations are separate profile qualifications; they are not assumed valid because one combination passed.

## 11. Public contract

### 11.1 Engineering evidence

Extend the existing validation family:

```text
fusion_validate(operation="fdm_printability", ...)
```

Request concepts: target refs/selectors, revision binding, printer/process profile, requested checks, build direction/orientation policy, provider policy, and analysis budget.

Result concepts: validation envelope, per-check findings, claim strength/confidence/basis, provenance, and `not_assessed` reasons when a required provider is unavailable.

### 11.2 Recipes

Use a separate semantic family instead of pretending every recipe is an existing transaction primitive:

```text
fusion_recipe(operation="list")
fusion_recipe(operation="describe")
fusion_recipe(operation="plan")
fusion_recipe(operation="run")
```

`plan` is deterministic and returns recipe ID/version, parameter validation, expanded semantic-operation plan, plan hash, required capabilities, expected outputs/proof obligations, and actual supported execution semantics.

`run` exposes exactly one execution semantic:

- `atomic` — only when every action is genuinely supported by the accepted transaction engine;
- `guarded_sequence` — ordered guarded semantic operations with truthful non-atomic behavior;
- `plan_only` — planning exists but safe execution is not currently available.

No raw embedded Python. No second Safe Executor. No false rollback promise across actions the accepted runtime cannot stage atomically.

### 11.3 Print Preparation

Add one small semantic family:

```text
fusion_print(operation="plan")
fusion_print(operation="prepare")
```

`plan` is read-only and resolves qualified profiles, objective, allowlisted candidate dimensions, candidate budget, provider capabilities, and expected artifacts/evidence.

`prepare` may create external files and invoke Orca but **does not mutate/save the Fusion document**. It returns neutral and prepared artifact refs/hashes, effective-settings artifact ref/hash, evaluated candidates/provider metrics, selected candidate+rationale, and provider/provenance warnings/limitations.

If an existing neutral revision-bound 3MF is supplied, `prepare` may reuse it after verifying provenance/hash. Otherwise it obtains a fresh neutral export through the accepted export path.

## 12. Capability and failure semantics

### 12.1 Provider unavailable

If Orca is absent or not qualified, neutral Fusion 3MF export may still succeed. Orca-specific slicer/island/Print Preparation capabilities report `unavailable` or `degraded` truthfully; P2 does not silently emulate Orca.

### 12.2 Profile mismatch / ambiguity

Unknown, ambiguous, incompatible, or unqualified printer/nozzle/filament combinations fail before slicing. No closest-name fallback.

### 12.3 Stale Fusion revision

A stale revision invalidates any request that claims current-model evidence or requests a fresh export. A previously generated artifact remains historical only and carries its original revision/hash.

### 12.4 Provider crash/timeout

Partial provider output does not become a successful prepared project. Diagnostics may be retained, but no prepared result is published unless all required qualification/validation checks completed.

### 12.5 Incomplete candidate search

If the budget expires or some candidates fail, the result states that the search was partial. A candidate may be preferred among completed candidates but is not presented as the complete-set winner.

## 13. Historical P2 requirement disposition

| Historical / new requirement | Canonical disposition |
| --- | --- |
| Printer/process profile | tiny Bridge glue + version/hash |
| Bed fit | Fusion authority + deterministic glue |
| Minimum wall | Trimesh heuristic |
| Minimum feature | narrowly defined heuristic or `not_assessed` |
| Overhang | Trimesh heuristic |
| Bridge candidates | Trimesh heuristic + optional Orca evidence |
| Unsupported islands | optional Orca provider; delete mesh-only claim |
| Print clearance | Fusion/Trimesh + explicit process policy |
| Orientation scoring | tiny glue + Trimesh + optional Orca candidate evidence |
| Joints / rigid groups / grounding | native Fusion/Shimmer; delete from P2 intelligence |
| Named views / sections | native Fusion/Shimmer; delete from P2 intelligence |
| Drawing DXF | deferred/capability-gated while required Autodesk API remains Preview |
| Versioned recipes | tiny declarative Bridge layer using JHK design patterns |
| Recipe rollback | existing transaction semantics only where genuinely supported |
| Packing / nesting | optional Fusion Automation or Orca; no custom solver |
| STL/3MF/STEP neutral export | accepted native/P1 capability, not P2 |
| External 3MF validation/editing | defer lib3mf until proven need |
| Offline oracle | CadQuery test-only |
| Print-ready 3MF with printer/nozzle/filament settings | **optional Orca provider + tiny Print Preparation glue** |
| Automatic “optimal” slicer settings | **bounded objective-driven candidate selection; never global-optimum claim** |
| Old Schedule P2 Golden | deleted/replaced by representative corpus + disposable live Fusion gate |

## 14. Acceptance strategy

### 14.1 Offline representative corpus

Use a versioned corpus covering a planar enclosure, curved shell/housing, bracket/overhang, bridge coupon, thin features, 0.2/0.5/1.0 mm clearances, bed-limit part, and a realistic multi-body arrangement case.

Part of the corpus is deterministic CadQuery ground truth; part must originate from real Fusion-generated/exported geometry so acceptance is not one Python geometry library checking another.

### 14.2 Accuracy semantics

Observed mesh/tessellation error informs uncertainty/bound policy. Threshold-overlap cases become WARN/uncertain rather than false exact GREEN/RED. Controlled-fixture exactness is not evidence of arbitrary-geometry global-minimum correctness.

### 14.3 Performance

Measure analysis cost by triangle/sample budget. Sync/async behavior follows explicit budget because measured research already shows multi-second and 10+ second cases at larger meshes.

### 14.4 Orca provider qualification

For every supported Orca version/profile family used in production-quality preparation:

1. record exact Orca build/version;
2. prove headless load/prepare/slice/export path;
3. export/read back effective settings;
4. verify machine/nozzle/material/process sentinel values;
5. verify a known fixture produces valid provider output;
6. invalidate qualification when Orca version/profile bundle changes materially;
7. retain a regression able to detect inherited-preset/default-fallback failures.

For the owner's first AD5X pilot, compare generated `print-project.3mf` and effective settings against the intended qualified Orca preset combination and manually open the project in Orca once as a release acceptance check. This is provider release acceptance, not a recurring requirement for every run.

### 14.5 Print Preparation candidate acceptance

At least one representative functional part exercises multiple bounded candidates under one objective. Acceptance proves the pinned machine/nozzle/filament base is unchanged, only allowlisted settings vary, provider metrics are retained, deterministic selection is reproducible, and the selected project opens in Orca with expected settings.

### 14.6 Live Fusion safety gate

Use only a fresh disposable unsaved Fusion Design:

```text
Reference rev_N
  -> neutral export/evidence
  -> P2 analysis / optional Print Preparation
  -> authoritative Reference re-read
```

Prove no Fusion document mutation/save occurred for analysis/Print Preparation. Recipe mutation acceptance, when later authorized, also uses disposable geometry and accepted freshness/preview/no-replay boundaries. `Schedule` and `Schedule Task14 Golden 224313` remain untouched.

## 15. Architecture options rejected for P2 v1

### Option B — central JHK-like Command IR / Safe Executor

Rejected as the primary substrate. Its IR/proof/rollback patterns are useful donors, but adopting its executor architecture would duplicate/reopen accepted P1 transaction/Hands machinery.

### Option C — provider-first P2

Rejected as the primary architecture. Orca/Fusion Automation remain valuable optional providers, but making them the epistemic center would weaken the offline baseline and over-couple P2 to provider installation, licensing, latency, and availability.

Option A uses the useful provider pieces without surrendering the evidence/provenance boundary.

## 16. Design freeze and next gate

This document freezes the P2 architecture/design boundary for owner review:

- thin Evidence facade;
- Fusion/Shimmer authority;
- Trimesh local evidence;
- optional Orca/Fusion Automation provider adapters;
- tiny declarative recipe family;
- optional Orca-backed Print Preparation with reproducible settings/provenance;
- no second CAD/executor/slicer/packer/copilot.

**Stop here for this phase.** Do not create an implementation plan, production P2 branch, runtime adapter, recipe implementation, or Orca integration code until the owner separately approves transition from design to implementation planning.
