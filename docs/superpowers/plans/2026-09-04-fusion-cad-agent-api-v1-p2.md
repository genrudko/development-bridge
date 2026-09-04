# Fusion CAD Agent API v1 P2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the advanced engineering layer to the accepted `fusion.cad/v1` foundation: FDM printability analysis, assembly joints/rigid groups/grounding, advanced view/DXF capabilities where the runtime supports them, versioned parametric recipes, and final Schedule golden acceptance.

**Architecture:** P2 composes P0 semantic perception and P1 safe mutation/transaction/export primitives. Printability is explicitly heuristic where Fusion alone cannot guarantee slicer behavior. Assembly/view/export extensions remain capability-declared. Recipes are declarative orchestration over existing CAD tools and inherit transactions, revision safety, diff, validation, provenance, and rollback.

**Tech Stack:** Existing `app/fusion_cad/` P0/P1 domain services, Autodesk Fusion Python API through versioned Bridge-owned scripts, pytest/pytest-asyncio, Ruff, Development Bridge Antigravity/Codex executors.

**Spec:** `docs/superpowers/specs/2026-09-04-fusion-cad-agent-api-v1-design.md`

## Global Constraints

- Inherit master plan and canonical spec.
- Hard precondition: P1 Schedule golden gate accepted.
- Implementation executor: Antigravity by default; Codex independent review after each task.
- Printability findings expose method, assumptions, and confidence; never claim slicer-equivalent certainty from geometry-only analysis.
- Assembly and DXF/view operations are capability-gated; unavailable means deterministic capability error, not silent fallback.
- Recipes reuse existing CAD domain operations; no second modeling engine and no agent-authored raw Python.
- Wake remains best-effort only; durable job IDs/ledger/Git are authoritative.

---

### Task 1: FDM printability profile and bed/orientation analysis

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Extend: `app/fusion_cad/validation.py`
- Create: `app/fusion_cad/printability.py`
- Create/Extend: `app/fusion_cad/fusion_scripts/validate.py.txt`
- Extend: `app/fusion_cad/requests.py`
- Create: `tests/unit/test_fusion_cad_printability.py`
- Test: `tests/integration/test_fusion_cad_service.py`

**Interfaces:**
- Produces `fdm_printability` validation profile with bed fit, min wall/feature, overhang, bridge candidates, unsupported islands, print clearance, and orientation scoring.

- [ ] **Step 1: Write printer-profile schema tests**

```python
def test_fdm_profile_requires_positive_bed_and_nozzle():
    with pytest.raises(ValidationError):
        FdmPrintProfile(bed=[220, 220, 0], nozzle=0.4, layer_height=0.2)
```

Also validate explicit units/default angle thresholds and bounded sampling/resolution options.

- [ ] **Step 2: Implement exact bed-fit and geometric clearance checks**

Compute oriented/current bbox against printer bed volume in explicit frame. Report exact excess per axis and recommended rotations where a simple deterministic fit exists.

- [ ] **Step 3: Implement minimum wall/feature analysis with method labels**

Use available BRep/measure sampling methods; return measured candidates plus `analysis_method`, sample resolution, and confidence. If an exact global minimum cannot be guaranteed, label result heuristic.

- [ ] **Step 4: Implement overhang/bridge/island heuristics**

Classify faces relative to build direction, detect bridge-like opposing supports and disconnected unsupported regions with documented assumptions. Do not claim slicer support-generation equivalence.

- [ ] **Step 5: Implement orientation scoring**

Score candidate orientations using weighted bed-fit, overhang area, support risk, footprint/contact, and height. Return component scores and assumptions, not only a magic total.

- [ ] **Step 6: Test deterministic fixtures**

Fixtures: simple box, thin wall, 60° overhang wedge, bridge bar, disconnected island, too-large bed part. Assert expected finding classes and confidence/method fields.

- [ ] **Step 7: Commit**

```bash
pytest -q tests/unit/test_fusion_cad_printability.py tests/integration/test_fusion_cad_service.py
git add app/fusion_cad tests
git commit -m "feat(fusion-cad): add FDM printability analysis"
```

---

### Task 2: Assembly joints, rigid groups, grounding

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Extend: `app/fusion_cad/requests.py`
- Extend/Create: `app/fusion_cad/fusion_scripts/component.py.txt`
- Modify: `app/fusion_cad/service.py`
- Create: `tests/unit/test_fusion_cad_assembly.py`
- Test: `tests/integration/test_fusion_cad_service.py`

**Interfaces:**
- Adds `fusion_component` joint_create/update/delete, rigid_group_create/delete, ground/unground.

- [ ] **Step 1: Write capability/schema RED tests**

Every assembly operation has strict input kind/frame requirements and checks a specific capability record before Fusion dispatch.

- [ ] **Step 2: Implement joint geometry resolution**

Resolve occurrence/component refs plus joint origins/geometry in explicit coordinate frames. Reject ambiguous contextual geometry rather than silently converting.

- [ ] **Step 3: Implement joint CRUD**

Return joint refs, participating occurrence refs, normalized motion/type parameters, and structural diff. All mutations participate in transaction/revision/provenance semantics.

- [ ] **Step 4: Implement rigid-group and ground operations**

Grounding and rigid groups are explicit model mutations requiring expected revision or transaction context; validation reports broken/missing members.

- [ ] **Step 5: Transaction rollback tests**

Preview/abort must leave no joint/rigid-group/provenance residue; committed group must be one logical transaction where runtime supports it.

- [ ] **Step 6: Commit**

```bash
pytest -q tests/unit/test_fusion_cad_assembly.py tests/integration/test_fusion_cad_service.py
git add app/fusion_cad tests
git commit -m "feat(fusion-cad): add assembly operations"
```

---

### Task 3: Advanced view capabilities and capability-gated DXF

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Extend: `app/fusion_cad/views.py`
- Extend: `app/fusion_cad/fusion_scripts/view.py.txt`
- Extend: `app/fusion_cad/fusion_scripts/export.py.txt`
- Extend: `app/fusion_cad/capabilities.py`
- Extend: `app/fusion_cad/requests.py`
- Extend: `tests/unit/test_fusion_cad_views.py`
- Create: `tests/unit/test_fusion_cad_dxf.py`

**Interfaces:**
- Completes runtime-supported advanced sections/named views and adds `fusion_export:dxf` when contract semantics are available.

- [ ] **Step 1: Re-probe runtime APIs rather than assuming earlier version facts**

Capability mapping uses current installed Fusion methods/preview status. Record limitations explicitly.

- [ ] **Step 2: Implement advanced section lifecycle where supported**

Create/move/disable section state with explicit frame/plane, update section hash, and invalidate old ViewRefs deterministically.

- [ ] **Step 3: Implement named-view semantics where supported**

Read/create/apply named view only if runtime API satisfies contract without UI automation. Applying named view changes camera/view context but does not save document implicitly.

- [ ] **Step 4: Implement DXF export only behind supported capability**

Scope and semantics follow the public export family. Unsupported/preview-inadequate runtime returns `CAPABILITY_UNAVAILABLE` with limitations; no legacy/unsafe silent substitute.

- [ ] **Step 5: Test artifact/no-save behavior**

Supported fake runtime returns DXF resource bytes; unavailable fake runtime sends no export command. Neither path invokes save.

- [ ] **Step 6: Commit**

```bash
pytest -q tests/unit/test_fusion_cad_views.py tests/unit/test_fusion_cad_dxf.py
git add app/fusion_cad tests
git commit -m "feat(fusion-cad): add advanced views and DXF capability"
```

---

### Task 4: Versioned parametric recipes

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Create: `app/fusion_cad/recipes.py`
- Extend: `app/fusion_cad/requests.py`
- Extend: `app/fusion_cad/transactions.py`
- Create: `tests/unit/test_fusion_cad_recipes.py`
- Test: `tests/integration/test_fusion_cad_service.py`

**Interfaces:**
- Produces recipe registry and `fusion_transaction:run_recipe`; initial recipes: `magnet_pocket/v1`, `dovetail_joint/v1`, `name_plate/v1`, `vent_slot_array/v1`.

- [ ] **Step 1: Write recipe registry/version tests**

```python
def test_recipe_ids_are_explicitly_versioned():
    assert registry.get("name_plate/v1").id == "name_plate/v1"
    with pytest.raises(RecipeNotFound):
        registry.get("name_plate")
```

- [ ] **Step 2: Define recipes as declarative CAD operation graphs**

Each recipe expands to strict existing `fusion_sketch`/`fusion_feature`/`fusion_style`/`fusion_transform` operations. No embedded arbitrary Python source.

- [ ] **Step 3: Inherit transaction semantics**

`run_recipe` stages expanded operations into one transaction; preview/diff/validation/provenance/rollback behave exactly like manually staged actions.

- [ ] **Step 4: Add recipe-specific provenance**

Generated objects record recipe ID/version plus logical object roles in same geometry transaction.

- [ ] **Step 5: Test deterministic recipe expansion**

Same normalized inputs produce same declarative plan/hash; unsupported operation capability blocks before partial application.

- [ ] **Step 6: Commit**

```bash
pytest -q tests/unit/test_fusion_cad_recipes.py tests/integration/test_fusion_cad_service.py
git add app/fusion_cad tests
git commit -m "feat(fusion-cad): add versioned parametric recipes"
```

---

### Task 5: P2 whole-phase review and final Schedule golden acceptance

**Executor:** Independent whole-phase review according to master executor strategy; coordinator owns final live acceptance.

**Files:**
- Modify: `docs/operations/fusion-cad-agent-acceptance.md`
- Modify contract/integration tests only for real acceptance gaps.

**Interfaces:**
- Produces final `fusion.cad/v1` release evidence.

- [ ] **Step 1: Run full offline gate**

```bash
pytest -q
git diff --name-only --diff-filter=ACMR "$PHASE_BASE"..HEAD -- '*.py' | xargs -r ruff check --ignore RUF012,TRY004
git diff --check
git status --short
```

- [ ] **Step 2: Dispatch whole-phase/final v1 reviewer**

Review complete v1 branch against canonical spec and all phase ledgers. Explicit focus: four invariants, capability truth, transaction safety, coordinate frames, selectors/refs, heuristic honesty in printability, recipe reuse, no hidden save, no raw-agent-script regression.

- [ ] **Step 3: Resolve findings with one bounded executor fix wave and scoped re-review**

No coordinator hand-edit bypass.

- [ ] **Step 4: Run Schedule 220 x 220 printability gate**

Apply printer profile `{bed:[220,220,220], nozzle:0.4, layer_height:0.2}` in canonical units. Record bed-fit, minimum wall/feature candidates, overhang/bridge/island findings, print clearance, orientation score with methods/confidence.

- [ ] **Step 5: Exercise advanced assembly/view capability on disposable appropriate geometry**

If Schedule itself has no meaningful assembly joint target, use a disposable companion assembly fixture for the assembly-specific operation while keeping Schedule as the release model for all applicable workflows. Capability evidence must remain explicit; do not mutate original Schedule.

- [ ] **Step 6: Run at least one real recipe on disposable Schedule-derived/companion target**

Prefer `name_plate/v1` or another workflow-relevant recipe. Use transaction preview -> validation/diff -> commit or rollback according to acceptance scenario; verify recipe provenance.

- [ ] **Step 7: Produce final validated artifacts**

Export applicable STL/3MF/STEP and DXF only if capability supported. Verify resource MIME/type, nonzero bytes, validation evidence, and no save side effect.

- [ ] **Step 8: Recheck four implementation invariants live**

Manual/external change -> revision conflict; metadata rollback atomicity; stale camera/visibility view -> `VIEW_STALE`; capability output matches actual supported/degraded/unavailable behavior.

- [ ] **Step 9: Final verdict**

`fusion.cad/v1` is complete only when P0/P1/P2 gates, full suite, independent reviews, live capability evidence, and Schedule acceptance are all green with no unresolved load-bearing finding. Merge/push/deploy remains a separate explicitly authorized action.
