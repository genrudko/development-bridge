# Fusion CAD Agent API v1 P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the `fusion.cad/v1` semantic and visual foundation: strict domain contract, truthful capabilities, revision-safe reads/mutations, stable refs/selectors, semantic snapshots/inspect, immutable views with pick, transactional metadata/logical text/visibility, model-hygiene validation, and proof that staged transaction semantics are feasible on live Fusion.

**Architecture:** Build P0 in `app/fusion_cad/` above the existing `DesktopNodeService`. Static Bridge-owned Fusion scripts execute through the current local MCP/`fusion_mcp_execute` escape hatch; the agent never supplies raw Python to domain tools. Public MCP adapters stay thin and strict. P0 ends with two live feasibility gates and the Schedule golden acceptance.

**Tech Stack:** Python 3.12, Pydantic v2, MCP Python SDK, Autodesk Fusion Python API through existing outbound relay, pytest/pytest-asyncio, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-04-fusion-cad-agent-api-v1-design.md`

## Global Constraints

- Inherit every constraint in `docs/superpowers/plans/2026-09-04-fusion-cad-agent-api-v1.md`.
- Implementation executor: Antigravity by default; review executor: Codex by default.
- Wake is best-effort only; durable job ID + Git + ledger are authoritative.
- P0 public tools are `fusion_read`, `fusion_inspect`, `fusion_view`, `fusion_metadata`, `fusion_style`, `fusion_validate`, and `fusion_transaction` foundation operations.
- P0 may not begin P1 CRUD work.
- P0 cannot be accepted unless visual pick and transaction preview/abort/replay/commit feasibility both pass live.

---

### Task 1: Core domain models, errors, and strict schemas

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Create: `app/fusion_cad/__init__.py`
- Create: `app/fusion_cad/models.py`
- Create: `app/fusion_cad/requests.py`
- Create: `app/fusion_cad/schemas.py`
- Create: `app/fusion_cad/errors.py`
- Modify: `app/api/errors.py`
- Test: `tests/unit/test_fusion_cad_models.py`
- Test: `tests/contract/test_fusion_cad_schemas.py`

**Interfaces:**
- Produces immutable `CoordinateFrame`, `EntityRef`, `EntitySelector`, `CapabilityRecord`, `DocumentState`, `CadResult`, `ValidationReportRef`, `ViewRefSummary`, request unions, and CAD error mapping.
- Later tasks must import these types rather than redefining dictionaries.

- [ ] **Step 1: Write failing core-type tests**

```python
import pytest
from pydantic import ValidationError

from app.fusion_cad.models import CoordinateFrame, EntityRef


def test_world_frame_rejects_entity_ref():
    with pytest.raises(ValidationError):
        CoordinateFrame(space="world", ref="ent_component")


def test_occurrence_frame_requires_entity_ref():
    with pytest.raises(ValidationError):
        CoordinateFrame(space="occurrence", ref=None)


def test_entity_ref_is_document_scoped():
    value = EntityRef(
        ref="ent_abcd",
        kind="face",
        document_ref="doc_1234",
        stability="persistent",
    )
    assert value.document_ref == "doc_1234"
```

- [ ] **Step 2: Write failing schema tests**

```python
def test_view_schema_is_discriminated_and_forbids_unknown_fields():
    schema = fusion_view_schema()
    assert "oneOf" in schema
    pick = next(branch for branch in schema["oneOf"] if branch["properties"]["operation"].get("const") == "pick")
    assert pick["additionalProperties"] is False
```

Also assert each P0 operation has its own branch and no unrestricted `params` object exists.

- [ ] **Step 3: Run RED**

```bash
pytest -q tests/unit/test_fusion_cad_models.py tests/contract/test_fusion_cad_schemas.py
```

Expected: missing package/types.

- [ ] **Step 4: Implement immutable Pydantic types**

Use `ConfigDict(extra="forbid", frozen=True)`. Validate opaque identifiers with explicit prefixes/patterns and validate `CoordinateFrame` rules. Keep native Fusion entity token out of the public `EntityRef` model.

- [ ] **Step 5: Add CAD error codes**

Add exact design codes to `ErrorCode`, reusing existing `INVALID_ARGUMENT` and `REVISION_CONFLICT`; add a missing `OPERATION_UNCERTAIN` only if it is not already present. Domain mapping must preserve retryable flags deliberately rather than marking mutation conflicts retryable by default.

- [ ] **Step 6: Implement strict P0 discriminated request models**

Expose request unions for the seven P0 tools. Every branch sets a literal `operation` and rejects operation-inapplicable fields.

- [ ] **Step 7: Run GREEN and debug sweep**

```bash
pytest -q tests/unit/test_fusion_cad_models.py tests/contract/test_fusion_cad_schemas.py
git diff --check
git status --short
```

- [ ] **Step 8: Commit and report**

```bash
git add app/fusion_cad app/api/errors.py tests/unit/test_fusion_cad_models.py tests/contract/test_fusion_cad_schemas.py
git commit -m "feat(fusion-cad): add v1 core contract models"
```

Report exact tests, commit SHA, changed files, and concerns for Codex review.

---

### Task 2: Domain service, script bundle, and MCP adapters

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Create: `app/fusion_cad/scripts.py`
- Create: `app/fusion_cad/service.py`
- Create: `app/fusion_cad/fusion_scripts/common.py.txt`
- Modify: `app/container.py`
- Modify: `app/tools/fusion.py`
- Modify: `app/tools/registry.py`
- Modify: `tests/contract/test_tool_surface.py`
- Test: `tests/unit/test_fusion_cad_scripts.py`
- Test: `tests/integration/test_fusion_cad_tools.py`

**Interfaces:**
- Produces `FusionCadScriptBundle.build(group, payload) -> str` and `FusionCadService.execute(request) -> CadResult | external-result`.
- MCP handlers validate strict models, call the service, and render existing artifact resources only.

- [ ] **Step 1: Write RED script-integrity test**

```python
def test_bundle_embeds_utf8_payload_as_json_not_python_source():
    script = bundle.build("read", {"operation": "echo", "text": "ПЫТОК 😈"})
    compile(script, "<fusion-cad>", "exec")
    assert "ПЫТОК 😈" in script
    assert "fusion.cad/v1" in script
```

- [ ] **Step 2: Write RED tool registration test**

Assert exactly one registration of each P0 domain tool while all six existing Fusion infrastructure tools remain registered.

- [ ] **Step 3: Implement script builder**

Read versioned static `.py.txt` fragments and inject only JSON-serialized payload using `json.dumps(..., ensure_ascii=False, separators=(",", ":"))`. Domain requests must never accept arbitrary script source.

- [ ] **Step 4: Implement service boundary**

`FusionCadService` receives `DesktopNodeService`; chooses sync only for fast bounded reads; can call/submit static domain scripts; normalizes retained results through existing external-result handling; does not duplicate the desktop-node operation journal.

- [ ] **Step 5: Construct service in container**

Add one `fusion_cad` service instance. Do not add global singleton state.

- [ ] **Step 6: Add thin MCP adapters**

Keep `app/tools/fusion.py` infrastructure tools intact. Domain handlers do request validation + service call + MCP result rendering; no CAD business logic in tool adapters.

- [ ] **Step 7: Run verification**

```bash
pytest -q tests/unit/test_fusion_cad_scripts.py tests/integration/test_fusion_cad_tools.py tests/contract/test_tool_surface.py
git diff --check
```

- [ ] **Step 8: Commit and report**

```bash
git add app/fusion_cad app/container.py app/tools/fusion.py app/tools/registry.py tests
git commit -m "feat(fusion-cad): add domain service and adapters"
```

---

### Task 3: Runtime capability matrix

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Create: `app/fusion_cad/capabilities.py`
- Create: `app/fusion_cad/fusion_scripts/read.py.txt`
- Modify: `app/fusion_cad/service.py`
- Test: `tests/unit/test_fusion_cad_capabilities.py`
- Test: `tests/integration/test_fusion_cad_service.py`

**Interfaces:**
- Produces `FusionRuntimeIdentity`, `CapabilityMatrix`, `CapabilityMatrix.require(name, allow_degraded=False)`, and `fusion_read(operation="capabilities")`.

- [ ] **Step 1: Write RED capability-state tests**

```python
def test_unavailable_capability_never_falls_back():
    matrix = CapabilityMatrix.from_records([CapabilityRecord(name="view.pick", state="unavailable")])
    with pytest.raises(BridgeError) as exc:
        matrix.require("view.pick")
    assert exc.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
```

Also test degraded requires explicit acceptance.

- [ ] **Step 2: Implement Fusion runtime probe script**

Probe actual application version and object/method availability for P0: entity-token resolver, design/timeline/sketch access, measure APIs, viewport/camera conversion, selection/preselection primitives, command preview hooks, Attributes, SketchText, undo/redo, and document mutation indicators.

- [ ] **Step 3: Build deterministic matrix**

Prefer direct runtime probes over version-number assumptions. Include `implementation`, Fusion version, relay/local-tool facts, and limitations.

- [ ] **Step 4: Enforce capability-first dispatch**

If an operation is unavailable, fail before sending a script. A degraded operation succeeds only when request schema has an explicit opt-in accepted by the spec.

- [ ] **Step 5: Run tests**

```bash
pytest -q tests/unit/test_fusion_cad_capabilities.py tests/integration/test_fusion_cad_service.py
```

- [ ] **Step 6: Commit**

```bash
git add app/fusion_cad tests/unit/test_fusion_cad_capabilities.py tests/integration/test_fusion_cad_service.py
git commit -m "feat(fusion-cad): add runtime capabilities"
```

---

### Task 4: Model revision tracking with manual/external change detection

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Create: `app/fusion_cad/revisions.py`
- Modify: `app/fusion_cad/fusion_scripts/read.py.txt`
- Modify: `app/fusion_cad/service.py`
- Test: `tests/unit/test_fusion_cad_revisions.py`
- Test: `tests/integration/test_fusion_cad_service.py`

**Interfaces:**
- Produces `RevisionTracker.observe(document_ref, fingerprint)`, `current()`, `assert_expected()`, and `FusionCadService.assert_fresh_for_mutation()`.

- [ ] **Step 1: Write RED revision tests**

```python
def test_manual_fingerprint_change_advances_revision():
    tracker = RevisionTracker()
    first = tracker.observe("doc_1", "hash-A")
    second = tracker.observe("doc_1", "hash-B")
    assert second.sequence == first.sequence + 1


def test_stale_expected_revision_blocks_before_executor_call():
    tracker.observe("doc_1", "hash-A")
    tracker.observe("doc_1", "hash-B")
    with pytest.raises(BridgeError) as exc:
        tracker.assert_expected("doc_1", "rev_1")
    assert exc.value.code == ErrorCode.REVISION_CONFLICT
```

- [ ] **Step 2: Define canonical model fingerprint payload**

Fusion script returns sorted mutation-sensitive semantic data: document identity/modified marker, timeline feature identity/health/suppression, component/occurrence identities and transforms, bodies and geometry summary, sketches/constraints, parameter expressions/values, Bridge attributes, and effective-visibility inputs. Serialize deterministically before hashing.

- [ ] **Step 3: Implement external-change observation**

Use strongest runtime change signals as hints, but mandatory pre-mutation freshness is a semantic fingerprint comparison. If required fingerprint data cannot be established reliably, relevant mutation capabilities become degraded/unavailable.

- [ ] **Step 4: Gate a synthetic mutation path**

Integration fake asserts the service reads current fingerprint and returns `REVISION_CONFLICT` without calling mutation executor when baseline changed.

- [ ] **Step 5: Debug edge cases**

Test document switch, active document close/reopen, same document unchanged, external add-in change, and Bridge-owned mutation advancement.

- [ ] **Step 6: Commit**

```bash
git add app/fusion_cad tests/unit/test_fusion_cad_revisions.py tests/integration/test_fusion_cad_service.py
git commit -m "feat(fusion-cad): enforce model revision freshness"
```

---

### Task 5: EntityRef resolver, CoordinateFrame conversions, and semantic selectors

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Create: `app/fusion_cad/refs.py`
- Create: `app/fusion_cad/selectors.py`
- Modify: `app/fusion_cad/fusion_scripts/common.py.txt`
- Modify: `app/fusion_cad/fusion_scripts/read.py.txt`
- Test: `tests/unit/test_fusion_cad_refs.py`
- Test: `tests/unit/test_fusion_cad_selectors.py`

**Interfaces:**
- Produces `EntityRefRegistry.issue`, `resolve`, `resolve_one`; frame conversion helpers; `SelectorEngine.normalize` and selector result/cardinality rules.

- [ ] **Step 1: Write resolver RED cases**

```python
@pytest.mark.parametrize("outcome", ["exact", "split", "stale", "wrong_document", "ambiguous"])
def test_resolver_preserves_outcome(outcome):
    ...
```

Concrete assertions: `resolve_one` accepts only exact; split exposes candidates; stale exposes none; wrong-document fails before native lookup; ambiguous never picks first.

- [ ] **Step 2: Write selector cardinality tests**

Zero target for single-target operation -> `SELECTOR_EMPTY`; more than one -> `SELECTOR_AMBIGUOUS`; multi-target query returns deterministic ordered refs.

- [ ] **Step 3: Implement opaque ref storage**

Persist bounded active/recent-document mapping of public ref to native token, kind, document, stability, component path, and optional contextual geometry signature. Never expose token as the public identity.

- [ ] **Step 4: Implement native resolver script**

Use design entity-token resolution where available and explicit contextual fallback. Return all candidates on topology split.

- [ ] **Step 5: Implement frame conversions**

Support world/component/occurrence/sketch frames. Every returned point/vector/transform/bbox carries an explicit frame. Capability-test the occurrence transform implementation.

- [ ] **Step 6: Implement P0 selector DSL**

Support kind, name/regex, component path, occurrence, feature type, created_by, tag, role, visible, appearance, bbox region, logical object, transaction ID, and recipe fields.

- [ ] **Step 7: Run tests and commit**

```bash
pytest -q tests/unit/test_fusion_cad_refs.py tests/unit/test_fusion_cad_selectors.py
git diff --check
git add app/fusion_cad tests/unit/test_fusion_cad_refs.py tests/unit/test_fusion_cad_selectors.py
git commit -m "feat(fusion-cad): add refs frames and selectors"
```

---

### Task 6: Semantic snapshot, feature tree, sketch read, parameters, selection, query

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Create: `app/fusion_cad/snapshots.py`
- Modify: `app/fusion_cad/fusion_scripts/read.py.txt`
- Modify: `app/fusion_cad/service.py`
- Test: `tests/unit/test_fusion_cad_snapshots.py`
- Test: `tests/integration/test_fusion_cad_service.py`

**Interfaces:**
- Produces `ModelSnapshot`, `SnapshotStore`, structural snapshot hash, and P0 `fusion_read` operations.

- [ ] **Step 1: Write compact snapshot RED test**

```python
def test_default_snapshot_is_semantic_not_topology_dump():
    snapshot = normalize_snapshot(raw_fixture)
    assert snapshot.counts.faces == 240
    assert snapshot.faces is None
    assert snapshot.components
    assert snapshot.bodies
```

- [ ] **Step 2: Implement canonical normalization**

Normalize units/frames/refs, sort unordered Fusion collections, include document/revision/components/occurrences/bodies/sketches/features/parameters/visibility/appearance/health/logical-object summaries, and compute deterministic structural hash.

- [ ] **Step 3: Implement feature tree**

Expose timeline index, suppression, health/diagnostic, outputs, dependencies with `exact|inferred|unknown`; never upgrade inferred to exact.

- [ ] **Step 4: Implement sketch read**

Expose geometry, dimensions, constraints, profiles, fully-constrained state when available, projection/reference state, SketchText, and health. Do not invent unsupported DOF counts.

- [ ] **Step 5: Implement selection and selector query**

Current user selection returns refs plus selection points/frames. `query` invokes Task 5 selector semantics.

- [ ] **Step 6: Test externalization**

Synthetic large snapshot must use existing retained external-result path rather than oversized inline JSON.

- [ ] **Step 7: Commit**

```bash
git add app/fusion_cad tests/unit/test_fusion_cad_snapshots.py tests/integration/test_fusion_cad_service.py
git commit -m "feat(fusion-cad): add semantic model reads"
```

---

### Task 7: P0 inspection operations

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Create: `app/fusion_cad/inspect.py`
- Create: `app/fusion_cad/fusion_scripts/inspect.py.txt`
- Modify: `app/fusion_cad/service.py`
- Test: `tests/unit/test_fusion_cad_inspect.py`
- Test: `tests/integration/test_fusion_cad_service.py`

**Interfaces:**
- Produces normalized describe/bbox/centroid/area/perimeter/volume/distance/min-distance/angle/relation/thickness results.

- [ ] **Step 1: Write unit/coordinate normalization tests**

Ensure length results are mm, angle deg, area mm², volume mm³, and geometric points include frames.

- [ ] **Step 2: Implement exact measures**

Use supported Fusion measure/BRep properties for P0 operations. Unsupported target types return `TYPE_MISMATCH` or `UNSUPPORTED_GEOMETRY`, not guessed values.

- [ ] **Step 3: Implement relation result contract**

Return `matches`, measured deviation, and explicit tolerance for parallel/perpendicular/coplanar/concentric.

- [ ] **Step 4: Implement conservative face-to-face thickness**

Only return exact thickness where target geometry defines it unambiguously. No whole-body min-wall heuristic in P0.

- [ ] **Step 5: Debug sweep and commit**

```bash
pytest -q tests/unit/test_fusion_cad_inspect.py tests/integration/test_fusion_cad_service.py
git diff --check
git add app/fusion_cad tests/unit/test_fusion_cad_inspect.py tests/integration/test_fusion_cad_service.py
git commit -m "feat(fusion-cad): add semantic inspection"
```

---

### Task 8: Camera, screenshot, immutable ViewRef

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Create: `app/fusion_cad/views.py`
- Create: `app/fusion_cad/fusion_scripts/view.py.txt`
- Modify: `app/fusion_cad/service.py`
- Test: `tests/unit/test_fusion_cad_views.py`
- Test: `tests/integration/test_fusion_cad_tools.py`

**Interfaces:**
- Produces camera read/set/fit/zoom/orient/standard-view, screenshot `ViewRef`, and `ViewRefStore.assert_fresh`.

- [ ] **Step 1: Write ViewRef stale tests**

Each of these independently invalidates the ref: model revision, camera hash, effective visibility hash, viewport dimensions, section hash.

```python
with pytest.raises(BridgeError) as exc:
    store.assert_fresh(view_ref, current_context=changed_camera)
assert exc.value.code == ErrorCode.VIEW_STALE
```

- [ ] **Step 2: Implement deterministic camera context**

Canonicalize eye/target/up/projection/viewport and section state. Hash full effective-visibility state, not only local visibility toggles.

- [ ] **Step 3: Wrap screenshot resource path**

Use the already proven image artifact extraction. `fusion_view:screenshot` returns image ResourceLink plus immutable view metadata; no duplicate base64 path.

- [ ] **Step 4: Implement camera operations**

All camera mutations invalidate prior view refs by changed camera revision/context. Camera operations are view state, not document save.

- [ ] **Step 5: Commit**

```bash
pytest -q tests/unit/test_fusion_cad_views.py tests/integration/test_fusion_cad_tools.py
git add app/fusion_cad tests/unit/test_fusion_cad_views.py tests/integration/test_fusion_cad_tools.py
git commit -m "feat(fusion-cad): add immutable view contexts"
```

---

### Task 9: Screen-space pick feasibility spike and implementation

**Executor:** Antigravity implementation/spike; Codex review of implementation and evidence. Coordinator performs final live acceptance.

**Files:**
- Modify: `app/fusion_cad/fusion_scripts/view.py.txt`
- Modify: `app/fusion_cad/views.py`
- Modify: `app/fusion_cad/capabilities.py`
- Test: `tests/unit/test_fusion_cad_views.py`
- Test: `tests/integration/test_fusion_cad_tools.py`
- Create/Modify: `docs/operations/fusion-cad-agent-acceptance.md`

**Interfaces:**
- Produces capability-backed `fusion_view(operation="pick")` returning ordered candidates with refs/depth/world point/distance where available.

- [ ] **Step 1: Implement two internal candidate strategies behind one interface**

Strategy A uses a verified native selection/preselection path. Strategy B constructs a ray from the immutable screenshot camera/viewport and performs verified Fusion geometry intersection. Do not expose two public operations.

- [ ] **Step 2: Write no-guess tests**

A stale view blocks before strategy call; multiple hit candidates return a stack; filter excludes wrong entity kinds; no hit returns `hit=false` rather than a fabricated nearest entity.

- [ ] **Step 3: Prove temporary selection state safety**

If Strategy A touches interactive selection state, capture/restore it and verify the operation leaves no persistent user selection mutation unless explicitly specified.

- [ ] **Step 4: Run offline tests**

```bash
pytest -q tests/unit/test_fusion_cad_views.py tests/integration/test_fusion_cad_tools.py
```

- [ ] **Step 5: Run one live feasibility acceptance on disposable model**

Sequence:

```text
fit/orient -> screenshot -> choose obvious face pixel -> pick -> inspect returned face
rotate camera -> pick old view_ref -> VIEW_STALE
new screenshot -> isolate/hide -> pick old view_ref -> VIEW_STALE
```

Record exact implementation selected and limitations in capability output.

- [ ] **Step 6: Stop condition**

If neither strategy satisfies immutable-view + correct-hit semantics, set `view.pick=unavailable`, record blocker/evidence, and STOP before P1. Do not weaken the public contract.

- [ ] **Step 7: Commit**

```bash
git add app/fusion_cad tests docs/operations/fusion-cad-agent-acceptance.md
git commit -m "feat(fusion-cad): add screen-space visual pick"
```

---

### Task 10: Transactional metadata, roles, tags, provenance

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Create: `app/fusion_cad/metadata.py`
- Create: `app/fusion_cad/fusion_scripts/mutate.py.txt`
- Modify: `app/fusion_cad/selectors.py`
- Modify: `app/fusion_cad/service.py`
- Test: `tests/unit/test_fusion_cad_metadata.py`
- Test: `tests/integration/test_fusion_cad_service.py`

**Interfaces:**
- Produces metadata get/set/remove/query/tag/untag/set_role/clear_role/provenance and reserved namespace `bridge.cad/v1`.

- [ ] **Step 1: Write no-hidden-post-commit test**

```python
def test_geometry_and_provenance_use_one_mutation_command(fake_desktop):
    service.execute(create_with_provenance_request)
    assert fake_desktop.mutation_calls == 1
```

- [ ] **Step 2: Implement reserved namespace rules**

Read/write only Bridge-owned group keys; preserve unrelated attributes. Explicit user metadata operations are normal mutations and require expected revision.

- [ ] **Step 3: Implement provenance payload**

Record creator tool/operation, operation ID, transaction ID, recipe, logical object ref, created revision, role/tags inside same mutation script that creates/changes geometry.

- [ ] **Step 4: Connect selector engine**

Role/tag/provenance selectors read model attributes, not only transient Bridge memory.

- [ ] **Step 5: Commit**

```bash
pytest -q tests/unit/test_fusion_cad_metadata.py tests/integration/test_fusion_cad_service.py
git add app/fusion_cad tests/unit/test_fusion_cad_metadata.py tests/integration/test_fusion_cad_service.py
git commit -m "feat(fusion-cad): add transactional metadata"
```

---

### Task 11: Logical Unicode text and visibility

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Modify: `app/fusion_cad/models.py`
- Modify: `app/fusion_cad/requests.py`
- Modify: `app/fusion_cad/fusion_scripts/mutate.py.txt`
- Modify: `app/fusion_cad/service.py`
- Test: `tests/unit/test_fusion_cad_text.py`
- Test: `tests/unit/test_fusion_cad_visibility.py`
- Test: `tests/integration/test_fusion_cad_service.py`

**Interfaces:**
- Produces opaque `TextRef`, text create/read/update/delete/extrude/cut, and visibility show/hide/set/show_only/isolate/restore.

- [ ] **Step 1: Write logical lineage tests**

Create result relates `TextRef -> sketch -> SketchText -> feature -> outputs`; update points logical current generation at new outputs and does not leave multiple current generations.

- [ ] **Step 2: Write Unicode/font tests**

Use `РАСПИСАНИЕ ПЫТОК 😈`. Verify UTF-8 survives request/script/result, requested/used font fields exist, and fallback reason is explicit when fallback occurs.

- [ ] **Step 3: Implement text operations**

Generated sketch/text/features/bodies get same-transaction provenance. Validate source profiles/counters where Fusion can expose them. Never silently delete unrelated legacy geometry.

- [ ] **Step 4: Implement effective visibility**

Read local and effective visibility through component/occurrence hierarchy. `isolate/show_only/restore` stores only enough reversible state for its own mutation.

- [ ] **Step 5: Enforce freshness on standalone mutations**

Mutation path calls Task 4 freshness check before execute and returns new revision after success.

- [ ] **Step 6: Commit**

```bash
pytest -q tests/unit/test_fusion_cad_text.py tests/unit/test_fusion_cad_visibility.py tests/integration/test_fusion_cad_service.py
git add app/fusion_cad tests
git commit -m "feat(fusion-cad): add logical text and visibility"
```

---

### Task 12: P0 validation profiles and model hygiene

**Executor:** Antigravity implementation; Codex task review.

**Files:**
- Create: `app/fusion_cad/validation.py`
- Create: `app/fusion_cad/fusion_scripts/validate.py.txt`
- Modify: `app/fusion_cad/service.py`
- Test: `tests/unit/test_fusion_cad_validation.py`
- Test: `tests/integration/test_fusion_cad_service.py`

**Interfaces:**
- Produces P0 profiles `parametric_health`, `model_hygiene`, `reference_integrity`, `text_integrity`, `pre_mutation` and GREEN/WARN/RED findings.

- [ ] **Step 1: Write policy tests**

Unconstrained sketch is profile-dependent and not globally RED. Open profile inventory is contextual. Broken feature/reference can be RED when policy says mutation unsafe.

- [ ] **Step 2: Implement exact health checks**

Collect feature/sketch diagnostics, ref integrity, invalid/empty/zero-volume body sanity, constraint/profile inventory, timeline state.

- [ ] **Step 3: Implement hygiene heuristics**

Detect repeated logical generations, orphaned Bridge-generated outputs, role/provenance inconsistencies, near-identical bbox/volume candidates, legacy generated bodies, dangling text outputs. Findings provide evidence/refs only; no repair/delete.

- [ ] **Step 4: Add AZURE legacy regression fixture**

Represent `AZURE_LEFT_TEXT_01..47` with one current generation; validator must flag stale generations without deleting them.

- [ ] **Step 5: Commit**

```bash
pytest -q tests/unit/test_fusion_cad_validation.py tests/integration/test_fusion_cad_service.py
git add app/fusion_cad tests/unit/test_fusion_cad_validation.py tests/integration/test_fusion_cad_service.py
git commit -m "feat(fusion-cad): add P0 validation profiles"
```

---

### Task 13: Transaction preview/abort/replay feasibility engine

**Executor:** Antigravity implementation/spike; Codex review; coordinator live acceptance authority.

**Files:**
- Create: `app/fusion_cad/transactions.py`
- Create: `app/fusion_cad/fusion_scripts/transaction.py.txt`
- Modify: `app/fusion_cad/fusion_scripts/mutate.py.txt`
- Modify: `app/fusion_cad/service.py`
- Modify: `app/fusion_cad/capabilities.py`
- Test: `tests/unit/test_fusion_cad_transactions.py`
- Test: `tests/integration/test_fusion_cad_service.py`
- Modify: `docs/operations/fusion-cad-agent-acceptance.md`

**Interfaces:**
- Produces P0 transaction state store and `begin/stage/preview/rollback/commit` sufficient to prove the accepted staged semantics before P1 CRUD.

- [ ] **Step 1: Write transaction state-machine tests**

Allow `NEW -> STAGED -> PREVIEWED -> STAGED -> COMMITTED` and rollback from nonterminal states. Block stale baseline, second commit, and stage after terminal state.

- [ ] **Step 2: Define one deterministic spike plan**

Use an existing P0 logical text or similarly safe mutation that generates geometry plus Bridge metadata. The plan must exercise generated refs/provenance; a pure visibility toggle is insufficient.

- [ ] **Step 3: Implement preview wrapper**

Execute staged declarative plan inside verified Fusion preview transaction, collect preview semantic snapshot/refs, then abort. Preview metadata is created inside preview and disappears with it.

- [ ] **Step 4: Implement replay commit wrapper**

Recheck baseline fingerprint/revision, replay exact plan in one final Fusion transaction/command, and keep metadata inside that same transaction.

- [ ] **Step 5: Offline tests**

Fake runtime proves command ordering and prevents hidden post-commit metadata command. Unit state store persists enough evidence for conflict detection.

- [ ] **Step 6: Mandatory live feasibility sequence**

On disposable model:

```text
capture A
begin + stage
preview -> capture B + refs + metadata + validation
abort -> capture A2 and prove A2 == semantic A
resolve pre-existing refs after abort
replay plan -> commit C and compare accepted preview semantics
undo once -> capture A3 and prove A3 == semantic A
begin again -> user/manual model edit -> commit -> REVISION_CONFLICT
prove preview-only refs/metadata absent after abort
```

- [ ] **Step 7: Stop condition**

Only set `transaction.preview_replay=supported` if all invariants pass. If not, record exact failing invariant and STOP before P1. Do not fake dry-run by “planning only”.

- [ ] **Step 8: Commit**

```bash
git add app/fusion_cad tests docs/operations/fusion-cad-agent-acceptance.md
git commit -m "feat(fusion-cad): prove transaction preview replay"
```

---

### Task 14: P0 whole-phase review and Schedule golden acceptance

**Executor:** Whole-phase independent review primarily Codex if Antigravity implemented P0; use Antigravity as cross-review if Codex performed substantial fallback implementation. Coordinator performs live Schedule acceptance.

**Files:**
- Modify: `docs/operations/fusion-cad-agent-acceptance.md`
- Modify: `tests/contract/test_fusion_cad_tool_surface.py`
- Modify: `tests/integration/test_fusion_cad_tools.py`

**Interfaces:**
- Produces evidence that all P0 contract/invariants hold on real Schedule copy and authorization to begin P1.

- [ ] **Step 1: Run full offline gate**

```bash
pytest -q
git diff --name-only --diff-filter=ACMR "$PHASE_BASE"..HEAD -- '*.py' | xargs -r ruff check --ignore RUF012,TRY004
git diff --check
git status --short
```

- [ ] **Step 2: Dispatch whole-phase reviewer**

Review package covers P0 branch base..HEAD, spec, P0 plan, ledger rulings/deferred minors. Reviewer must check: schema strictness, service/tool separation, no hidden save, revision truth, metadata transaction semantics, view immutability, capability truth, no agent-authored raw Python path in P0 domain operations.

- [ ] **Step 3: Resolve review findings through executor fix/re-review**

No coordinator hand-edit shortcut. One bounded fix wave per master review policy.

- [ ] **Step 4: Run Schedule copy acceptance**

Without agent-authored raw Python:

```text
open/confirm disposable Schedule copy
snapshot + feature/sketch read
find suspicious legacy generated bodies
read Unicode logical text
semantic selector by role/tag
inspect geometry
validate P0 profiles
update logical text with expected_revision
visibility/isolate
camera orient/fit
screenshot -> view_ref
visual pick -> face ref -> semantic inspect
undo mutation
verify active document was not saved
```

- [ ] **Step 5: Explicitly test four invariants**

1. Make one manual Fusion change after snapshot; stale mutation must return `REVISION_CONFLICT` before apply.
2. Preview/rollback provenance must leave no hidden Bridge attributes.
3. Change camera and effective visibility after screenshot; old `view_ref` pick must return `VIEW_STALE` in both cases.
4. Query capability matrix and deliberately call one known unavailable/degraded test capability fixture/path; behavior must match declared state without hidden fallback.

- [ ] **Step 6: Record phase verdict**

P0 is complete only if both load-bearing feasibility capabilities `view.pick` and `transaction.preview_replay` are exactly `supported`, Schedule gate passes, full suite passes, and no load-bearing reviewer finding remains. `degraded` does not unlock P1 for either gate.

- [ ] **Step 7: Documentation commit if acceptance runbook/evidence changed**

```bash
git add docs/operations/fusion-cad-agent-acceptance.md tests
git commit -m "docs(fusion-cad): record P0 acceptance gate"
```

Do not merge/push/deploy unless explicitly authorized at that execution point.
