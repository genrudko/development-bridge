# Fusion CAD Agent API v1 P1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build safe high-level parametric modeling on the proven P0 foundation: full staged transactions and structural diff, Sketch/Feature CRUD, component/occurrence and layout operations, appearances, mechanical interference/clearance, checkpoints/section views, and STL/3MF/STEP artifact export.

**Architecture:** Every P1 mutator compiles a strict declarative request into the transaction plan proven in P0. Standalone mutations still use expected-revision safety; dry-run is an implicit preview transaction; provenance stays in the same transaction as geometry. P1 adds no second state engine and no raw agent-authored Python path.

**Tech Stack:** P0 `app/fusion_cad/` services, Autodesk Fusion Python API through versioned Bridge-owned scripts, pytest/pytest-asyncio, Ruff, Development Bridge Antigravity/Codex executors.

**Spec:** `docs/superpowers/specs/2026-09-04-fusion-cad-agent-api-v1-design.md`

## Global Constraints

- Inherit the master plan and canonical spec.
- Hard precondition: P0 Schedule gate accepted and both `view.pick` and `transaction.preview_replay` capabilities satisfy the accepted contract.
- Implementation executor: Antigravity by default; Codex independent review after each task.
- Authoritative revision freshness guard runs Fusion-side inside the same execution/command as mutation/preview/commit with no return to UI between guard and apply, closing TOCTOU races; Bridge precheck is an optimization only. If atomicity cannot be guaranteed, mutation capability is degraded/unavailable.
- Every P1 mutator supports transaction staging; direct execution requires `expected_revision`.
- Every added or extended public operation requires strict discriminated `oneOf`/`additionalProperties:false` schema contract tests in `tests/contract/test_fusion_cad_schemas.py`.
- Explicitly register, adapt, and test all five new P1 public tool families: `fusion_sketch`, `fusion_feature`, `fusion_component`, `fusion_transform`, and `fusion_export`.
- `dry_run=true` performs real preview/abort and returns diff/validation without persistent change.
- Metadata/provenance is part of the same transaction as generated/modified geometry.
- Export returns retained artifacts and never implies document save.
- Wake is best-effort only; durable job IDs/ledger/Git are authoritative.

---

### Task 1: Full transaction engine and structural diff

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Expand: `app/fusion_cad/transactions.py`
- Expand: `app/fusion_cad/diff.py`
- Expand: `app/fusion_cad/fusion_scripts/transaction.py.txt`
- Modify: `app/fusion_cad/service.py`
- Modify: `tests/contract/test_fusion_cad_schemas.py`
- Test: `tests/unit/test_fusion_cad_transactions.py`
- Create: `tests/unit/test_fusion_cad_diff.py`
- Test: `tests/integration/test_fusion_cad_service.py`

**Interfaces:**
- Expands P0 minimal preview-diff into full reusable `StructuralDiff.compare(before, after)`. Produces durable-enough in-process/disk-backed staged transaction records for Bridge restart policy chosen by P0 findings, `begin/stage/preview/commit/rollback`, and implicit dry-run.

- [ ] **Step 1: Write RED diff and schema contract tests**

```python
def test_structural_diff_reports_semantic_changes_not_mesh_noise():
    diff = StructuralDiff.compare(before, after)
    assert [x.ref for x in diff.created["features"]] == ["ent_feature_2"]
    assert diff.modified["parameters"][0].delta["expression"] == ["10 mm", "12 mm"]
    assert "mesh_vertices" not in diff.model_dump_json()
```

Also assert strict discriminated `oneOf` and `additionalProperties: false` on transaction request schemas in `tests/contract/test_fusion_cad_schemas.py`. Cover components, occurrences, features, bodies, sketches, parameters, logical text, metadata, visibility, appearances, bbox/area/volume, health, ref resolution.

- [ ] **Step 2: Write full transaction state/recovery tests**

Test begin/stage/preview/commit/rollback; stale baseline; repeated preview; commit after preview; rollback before commit; no commit after terminal state; dry-run persistence zero; one logical operation journal entry per commit.

- [ ] **Step 3: Implement structural diff engine**

Compare normalized P0 snapshots and stable refs. Do not diff raw mesh topology by default. Unknown/unresolved refs become explicit diff warnings.

- [ ] **Step 4: Complete transaction store with Fusion-side freshness guard**

Persist declarative plan, baseline revision/hash, requested validations, preview evidence, commit operation ID, and safe-head information sufficient for checkpoint logic. Recheck baseline via authoritative Fusion-side freshness guard inside commit execution with no return to UI between guard and apply.

- [ ] **Step 5: Implement implicit dry-run**

`dry_run=true` maps to begin -> stage -> preview -> diff -> validate -> abort and returns no persistent revision advance.

- [ ] **Step 6: Run tests/debug sweep**

```bash
pytest -q tests/unit/test_fusion_cad_transactions.py tests/unit/test_fusion_cad_diff.py tests/integration/test_fusion_cad_service.py tests/contract/test_fusion_cad_schemas.py
git diff --check
```

- [ ] **Step 7: Commit**

```bash
git add app/fusion_cad tests
git commit -m "feat(fusion-cad): complete staged transactions and diff"
```

---

### Task 2: Parametric Sketch CRUD batch DSL

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Extend: `app/fusion_cad/requests.py`
- Create/Extend: `app/fusion_cad/fusion_scripts/sketch.py.txt`
- Modify: `app/fusion_cad/service.py`
- Modify: `app/tools/fusion.py`
- Modify: `app/tools/registry.py`
- Modify: `tests/contract/test_fusion_cad_schemas.py`
- Modify: `tests/contract/test_tool_surface.py`
- Create: `tests/unit/test_fusion_cad_sketch.py`
- Test: `tests/integration/test_fusion_cad_service.py`

**Interfaces:**
- Produces `fusion_sketch` strict operations for create/read/update/delete and batch actions: line, arc, circle, rectangle, slot, spline, point, project, offset, trim, construction/reference, dimension, constraints. Registers and adapts `fusion_sketch` on the public tool surface.

- [ ] **Step 1: Write RED schema/action dependency tests**

```python
def test_batch_action_can_reference_prior_action_id_only():
    req = SketchMutateRequest(... actions=[LineAction(id="a1", ...), CoincidentAction(entities=["a1.start", "existing:ent_x"])])
    assert req.actions[1].entities[0] == "a1.start"
```

Also assert strict discriminated `oneOf` and `additionalProperties: false` for all sketch operations in `tests/contract/test_fusion_cad_schemas.py`. Unknown future action IDs and duplicate IDs must fail validation before Fusion call.

- [ ] **Step 2: Implement strict action models**

Each action has a discriminator `type`; dimensions/constraints have kind-specific required fields. No free-form geometry dict.

- [ ] **Step 3: Implement Fusion sketch dispatcher**

Resolve refs/frames, create primitives, then resolve intra-batch action IDs. Return created entity refs and resulting sketch health/profile/constraint summary.

- [ ] **Step 4: Register and adapt tool on public surface**

Register `fusion_sketch` in `app/tools/registry.py`, add thin MCP adapter in `app/tools/fusion.py`, and assert contract surface in `tests/contract/test_tool_surface.py`.

- [ ] **Step 5: Integrate transaction semantics and Fusion-side freshness guard**

Transaction request stores declarative actions unchanged enough for deterministic replay. Standalone mutation executes authoritative Fusion-side freshness guard in the mutation script with no return to UI between guard and apply.

- [ ] **Step 6: Test failure edges**

Invalid profile/plane, bad entity kind, unsupported constraint, stale ref, and transaction rollback leave no geometry/provenance.

- [ ] **Step 7: Commit**

```bash
pytest -q tests/unit/test_fusion_cad_sketch.py tests/integration/test_fusion_cad_service.py tests/contract/test_fusion_cad_schemas.py tests/contract/test_tool_surface.py
git add app/fusion_cad app/tools tests
git commit -m "feat(fusion-cad): add parametric sketch CRUD"
```

---

### Task 3: Feature CRUD

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Extend: `app/fusion_cad/requests.py`
- Create: `app/fusion_cad/fusion_scripts/feature.py.txt`
- Modify: `app/fusion_cad/service.py`
- Modify: `app/tools/fusion.py`
- Modify: `app/tools/registry.py`
- Modify: `tests/contract/test_fusion_cad_schemas.py`
- Modify: `tests/contract/test_tool_surface.py`
- Create: `tests/unit/test_fusion_cad_feature.py`
- Test: `tests/integration/test_fusion_cad_service.py`

**Interfaces:**
- Produces `fusion_feature` create/update/delete/suppress/unsuppress/batch for extrude, revolve, sweep, loft, hole, fillet, chamfer, shell, draft, pattern, mirror, combine, split. Registers and adapts `fusion_feature` on the public tool surface.

- [ ] **Step 1: Write strict feature-schema RED contract tests**

Assert strict discriminated `oneOf` and `additionalProperties: false` for all feature operations in `tests/contract/test_fusion_cad_schemas.py`. Example: extrude requires profile target + extent + boolean operation; fillet requires edge refs/radius; cross-feature fields rejected.

- [ ] **Step 2: Map capabilities per feature kind**

Before dispatch, `feature.<kind>.<operation>` capability must be supported/degraded-accepted. No generic script fallback if a feature adapter is unavailable.

- [ ] **Step 3: Implement create adapters**

Return feature ref plus output body/face refs. Normalize length/angle units and all input geometry frames.

- [ ] **Step 4: Implement update/delete/suppress semantics**

Use stable refs and capture before/after structural diff. Delete updates provenance/logical references in the same transaction or reports dangling references for validation; never hidden-clean later.

- [ ] **Step 5: Register and adapt tool on public surface**

Register `fusion_feature` in `app/tools/registry.py`, add thin MCP adapter in `app/tools/fusion.py`, and assert contract surface in `tests/contract/test_tool_surface.py`.

- [ ] **Step 6: Transaction replay tests and Fusion-side freshness guard**

At minimum extrude + fillet batch preview/abort/replay must produce semantically equivalent diff on fake/integration runtime. Standalone mutations enforce Fusion-side freshness guard inside the mutation script.

- [ ] **Step 7: Commit**

```bash
pytest -q tests/unit/test_fusion_cad_feature.py tests/integration/test_fusion_cad_service.py tests/contract/test_fusion_cad_schemas.py tests/contract/test_tool_surface.py
git add app/fusion_cad app/tools tests
git commit -m "feat(fusion-cad): add feature CRUD"
```

---

### Task 4: Components, occurrences, transforms, and layout/pack

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Extend: `app/fusion_cad/requests.py`
- Create: `app/fusion_cad/fusion_scripts/component.py.txt`
- Create: `app/fusion_cad/fusion_scripts/transform.py.txt`
- Modify: `app/fusion_cad/service.py`
- Modify: `app/tools/fusion.py`
- Modify: `app/tools/registry.py`
- Modify: `tests/contract/test_fusion_cad_schemas.py`
- Modify: `tests/contract/test_tool_surface.py`
- Create: `tests/unit/test_fusion_cad_component.py`
- Create: `tests/unit/test_fusion_cad_transform.py`
- Test: `tests/integration/test_fusion_cad_service.py`

**Interfaces:**
- Produces component create/delete, occurrence create/copy/rename/replace/set-active where supported; move/rotate/align/distribute/grid/pack/copy_n/orient-face-to-plane/lay-flat. Registers and adapts `fusion_component` and `fusion_transform` on the public tool surface.

- [ ] **Step 1: Write CoordinateFrame/occurrence-context and schema contract tests**

Assert strict discriminated `oneOf` and `additionalProperties: false` for all component and transform operations in `tests/contract/test_fusion_cad_schemas.py`. Moving an occurrence in world vs occurrence frame must produce distinct normalized transforms. Reject ambiguous implicit frame inputs.

- [ ] **Step 2: Implement component/occurrence adapters**

Use runtime-supported occurrence transform API identified in capabilities. Return new occurrence/component refs and updated revision/diff.

- [ ] **Step 3: Implement alignment/distribution helpers**

Inputs are refs/selectors plus explicit axis/plane/frame and spacing. Results report transforms applied per target.

- [ ] **Step 4: Implement deterministic pack**

Input: target refs/selectors, rectangular region/bed frame, spacing, allowed rotations, optional preserve-groups. Output: placed/unplaced refs, per-part transform, used bounds, spacing, reason for unplaced.

- [ ] **Step 5: Register and adapt tool families on public surface**

Register `fusion_component` and `fusion_transform` in `app/tools/registry.py`, add thin MCP adapters in `app/tools/fusion.py`, and assert contract surface in `tests/contract/test_tool_surface.py`.

- [ ] **Step 6: Add 36-part synthetic pack regression**

Verify stable deterministic layout with no overlaps under configured spacing; same input/revision yields same plan/diff.

- [ ] **Step 7: Commit**

```bash
pytest -q tests/unit/test_fusion_cad_component.py tests/unit/test_fusion_cad_transform.py tests/integration/test_fusion_cad_service.py tests/contract/test_fusion_cad_schemas.py tests/contract/test_tool_surface.py
git add app/fusion_cad app/tools tests
git commit -m "feat(fusion-cad): add components transforms and layout"
```

---

### Task 5: Appearance operations

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Extend: `app/fusion_cad/requests.py`
- Extend: `app/fusion_cad/fusion_scripts/mutate.py.txt`
- Modify: `app/fusion_cad/service.py`
- Modify: `tests/contract/test_fusion_cad_schemas.py`
- Create: `tests/unit/test_fusion_cad_appearance.py`

**Interfaces:**
- Adds `fusion_style` appearance read/assign/clone/create_rgb/clear with effective inheritance reporting.

- [ ] **Step 1: Write inheritance and schema contract tests**

Assert strict discriminated `oneOf` and `additionalProperties: false` for style appearance operations in `tests/contract/test_fusion_cad_schemas.py`. Read must distinguish locally assigned appearance from inherited component/occurrence appearance and report source ref.

- [ ] **Step 2: Implement appearance lookup/clone/RGB creation**

Capability-test material/appearance APIs. Names and RGB values are explicit; do not mutate library originals unintentionally.

- [ ] **Step 3: Make appearance mutation transactional/revisioned**

Preview/abort restores appearance; commit advances revision and diff via Fusion-side freshness guard; no hidden follow-up.

- [ ] **Step 4: Commit**

```bash
pytest -q tests/unit/test_fusion_cad_appearance.py tests/contract/test_fusion_cad_schemas.py
git add app/fusion_cad tests/unit/test_fusion_cad_appearance.py tests/contract/test_fusion_cad_schemas.py
git commit -m "feat(fusion-cad): add appearance operations"
```

---

### Task 6: Mechanical interference and clearance

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Extend: `app/fusion_cad/inspect.py`
- Extend: `app/fusion_cad/fusion_scripts/inspect.py.txt`
- Extend: `app/fusion_cad/validation.py`
- Modify: `tests/contract/test_fusion_cad_schemas.py`
- Create: `tests/unit/test_fusion_cad_interference.py`
- Test: `tests/integration/test_fusion_cad_service.py`

**Interfaces:**
- Adds `interference` and `clearance_report`; P1 validation profile `mechanical_clearance`.

- [ ] **Step 1: Write selector exclusion and schema contract tests**

```python
def test_interference_excludes_decorative_text_role():
    targets = selector_engine.resolve(include=main_selector, exclude=EntitySelector(role=["decorative_text"]))
    assert all("decorative_text" not in x.roles for x in targets)
```

Assert strict discriminated `oneOf` and `additionalProperties: false` for extended inspect operations in `tests/contract/test_fusion_cad_schemas.py`.

- [ ] **Step 2: Implement native interference adapter**

Use supported bodies/occurrences only; map results back to stable refs and exact overlap evidence.

- [ ] **Step 3: Implement clearance report**

Compute min-distance pairs under explicit threshold; include pair refs, measured clearance, threshold, and geometry points/frames where available.

- [ ] **Step 4: Avoid false positives from roles**

Role/tag exclusion happens before geometry analysis and is reflected in normalized query evidence.

- [ ] **Step 5: Commit**

```bash
pytest -q tests/unit/test_fusion_cad_interference.py tests/integration/test_fusion_cad_service.py tests/contract/test_fusion_cad_schemas.py
git add app/fusion_cad tests
git commit -m "feat(fusion-cad): add interference and clearance"
```

---

### Task 7: Pre-commit validation profile and commit-blocking policy

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Modify: `app/fusion_cad/validation.py`
- Modify: `app/fusion_cad/transactions.py`
- Modify: `app/fusion_cad/service.py`
- Modify: `app/fusion_cad/fusion_scripts/validate.py.txt`
- Modify: `app/fusion_cad/requests.py`
- Modify: `tests/contract/test_fusion_cad_schemas.py`
- Create: `tests/unit/test_fusion_cad_pre_commit.py`
- Test: `tests/unit/test_fusion_cad_validation.py`
- Test: `tests/unit/test_fusion_cad_transactions.py`
- Test: `tests/integration/test_fusion_cad_service.py`

**Interfaces:**
- Produces `pre_commit` validation profile, commit-blocking policy evaluation, and transaction commit guard that blocks commit with `VALIDATION_FAILED` or `TRANSACTION_CONFLICT` when staged validations fail.

- [ ] **Step 1: Write RED tests for pre_commit profile and commit-blocking policy**

Test that RED findings in `pre_commit` profile block transaction commit before final script apply; test that GREEN/WARN findings allow commit according to configured policy threshold; test schema validation options.

- [ ] **Step 2: Implement pre_commit validation profile aggregator**

In `app/fusion_cad/validation.py`, compose parametric health, reference integrity, model hygiene, and geometry sanity checks against staged preview state.

- [ ] **Step 3: Implement commit-blocking policy in transaction pipeline**

In `app/fusion_cad/transactions.py` and `service.py`, evaluate configured `pre_commit` validations prior to executing the commit script. If policy fails, abort commit and return `VALIDATION_FAILED` without persisting invalid changes.

- [ ] **Step 4: Strict discriminated oneOf and additionalProperties: false schema contract tests**

Assert `pre_commit` request options and validation response structures in `tests/contract/test_fusion_cad_schemas.py`.

- [ ] **Step 5: Test failure edges**

Broken feature references, invalid/empty bodies, unconstrained sketch policy, and commit abort leaving no persistent model modification.

- [ ] **Step 6: Commit**

```bash
pytest -q tests/unit/test_fusion_cad_pre_commit.py tests/unit/test_fusion_cad_validation.py tests/unit/test_fusion_cad_transactions.py tests/integration/test_fusion_cad_service.py tests/contract/test_fusion_cad_schemas.py
git diff --check
git add app/fusion_cad tests
git commit -m "feat(fusion-cad): add pre-commit validation profile and blocking policy"
```

---

### Task 8: Checkpoints plus section/named-view workflow

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Extend: `app/fusion_cad/transactions.py`
- Extend: `app/fusion_cad/views.py`
- Extend: `app/fusion_cad/fusion_scripts/view.py.txt`
- Modify: `tests/contract/test_fusion_cad_schemas.py`
- Create: `tests/unit/test_fusion_cad_checkpoints.py`
- Extend: `tests/unit/test_fusion_cad_views.py`

**Interfaces:**
- Adds checkpoint_create/list/restore and capability-backed section_create/move/disable/named_view.

- [ ] **Step 1: Write safe-head checkpoint and schema contract tests**

Assert strict discriminated `oneOf` and `additionalProperties: false` for checkpoint and section operations in `tests/contract/test_fusion_cad_schemas.py`. Restore succeeds only when all mutations since checkpoint are known consecutive Bridge-owned transactions. Manual/external divergence -> `CHECKPOINT_DIVERGED` before Undo.

- [ ] **Step 2: Implement checkpoint records**

Store checkpoint ID, document/ref revision, structural hash, transaction-chain head, and enough safe Undo lineage evidence; do not snapshot entire Fusion file as hidden save.

- [ ] **Step 3: Implement guarded restore**

Recheck current fingerprint and transaction head before any Undo sequence. Stop at first unknown/manual divergence.

- [ ] **Step 4: Implement section/named view behind capabilities**

Section changes invalidate prior ViewRefs through section hash. Unavailable native section/named-view semantics return capability error; no UI automation fallback.

- [ ] **Step 5: Commit**

```bash
pytest -q tests/unit/test_fusion_cad_checkpoints.py tests/unit/test_fusion_cad_views.py tests/contract/test_fusion_cad_schemas.py
git add app/fusion_cad tests
git commit -m "feat(fusion-cad): add checkpoints and section views"
```

---

### Task 9: STL, 3MF, STEP export artifacts and pre-export validation

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Create: `app/fusion_cad/fusion_scripts/export.py.txt`
- Extend: `app/fusion_cad/requests.py`
- Extend: `app/fusion_cad/service.py`
- Extend: `app/fusion_cad/validation.py`
- Modify: `app/tools/fusion.py`
- Modify: `app/tools/registry.py`
- Modify: `tests/contract/test_fusion_cad_schemas.py`
- Modify: `tests/contract/test_tool_surface.py`
- Create: `tests/unit/test_fusion_cad_export.py`
- Test: `tests/integration/test_fusion_cad_tools.py`

**Interfaces:**
- Produces `fusion_export` operations `stl`, `3mf`, `step`, scopes document/component/occurrence/body/bodies/layout, retained file resources, and `pre_export` validation policy. Registers and adapts `fusion_export` on the public tool surface.

- [ ] **Step 1: Write strict export schema contract tests**

Assert strict discriminated `oneOf` and `additionalProperties: false` for all export operations in `tests/contract/test_fusion_cad_schemas.py`. Reject DXF in P1 execution unless capability-backed branch is explicitly allowed later. Validate per-format options, scopes, grouped/per-body, refinement, validate_before, fail_on_validation.

- [ ] **Step 2: Implement export to controlled Windows temp/output path**

Generate collision-safe file names, export through Fusion API, then return bytes through the existing Windows result/artifact upload channel. The model sees resource links, not only `C:\...` paths.

- [ ] **Step 3: Register and adapt tool on public surface**

Register `fusion_export` in `app/tools/registry.py`, add thin MCP adapter in `app/tools/fusion.py`, and assert contract surface in `tests/contract/test_tool_surface.py`.

- [ ] **Step 4: Run pre-export validation and test no-save invariant**

If `fail_on_validation=true` and configured profile returns RED, do not execute export. Export does not call document save/saveAs. Mock/integration call log must prove no save command occurs.

- [ ] **Step 5: Commit**

```bash
pytest -q tests/unit/test_fusion_cad_export.py tests/integration/test_fusion_cad_tools.py tests/contract/test_fusion_cad_schemas.py tests/contract/test_tool_surface.py
git add app/fusion_cad app/tools tests
git commit -m "feat(fusion-cad): add validated export artifacts"
```

---

### Task 10: P1 whole-phase review and Schedule golden acceptance

**Executor:** Independent whole-phase review per master executor strategy; coordinator owns live Schedule acceptance.

**Files:**
- Modify: `docs/operations/fusion-cad-agent-acceptance.md`
- Modify: `tests/contract/test_tool_surface.py`
- Modify relevant contract/integration tests only if acceptance exposes a real gap.

**Interfaces:**
- Produces P1 acceptance evidence and authorization to begin P2.

- [ ] **Step 1: Run full offline gate**

```bash
pytest -q
git diff --name-only --diff-filter=ACMR "$PHASE_BASE"..HEAD -- '*.py' | xargs -r ruff check --ignore RUF012,TRY004
git diff --check
git status --short
```

- [ ] **Step 2: Dispatch whole-phase reviewer**

Review branch base..HEAD against canonical spec, P1 plan, and ledger. Explicitly inspect tool family registration and surface tests, transaction replay, metadata-in-transaction, ref/frame correctness, strict schemas (`oneOf`/`additionalProperties:false`), pre-commit validation policy, no raw model-authored script path, no save side effect, and artifact security/bounds.

- [ ] **Step 3: Resolve review findings through one bounded executor fix wave and scoped re-review**

No coordinator hand-edit bypass.

- [ ] **Step 4: Run Schedule transaction preview/rollback**

```text
begin on disposable Schedule copy
stage a real parametric change
preview -> structural diff + validate + screenshot
rollback -> prove semantic baseline restored
```

- [ ] **Step 5: Replay and commit**

Replay exact plan, commit, prove commit semantics match accepted preview, then one Undo restores baseline.

- [ ] **Step 6: Pack 36 name plates**

Use high-level `fusion_transform:pack`, not raw Python. Verify deterministic placement, bounds/spacing, and no unexpected overlap.

- [ ] **Step 7: Targeted mechanical interference**

Check main mechanical bodies while excluding `role=decorative_text`; verify returned query evidence and clearance/interference report.

- [ ] **Step 8: Export grouped artifacts**

Produce grouped 3MF, STL, and STEP resources for the accepted layout/scope with pre-export validation. Verify actual resource bytes/type and no document save.

- [ ] **Step 9: Accept/stop**

P1 completes only if Schedule gate passes, full suite/review are clean, checkpoint safety is proven, and no capability claim contradicts live runtime. Otherwise P2 stays blocked.
