# Fusion CAD Agent API v1 — Canonical Design Spec

**Status:** accepted Release Candidate; canonical architecture for P0/P1/P2 implementation.

**Contract version:** `fusion.cad/v1`

**Accepted:** 2026-09-04

## 1. Purpose

Development Bridge already provides a durable outbound Windows Fusion relay, async operation lifecycle, result retention, image artifacts, undo/redo access, and a raw Autodesk Fusion Python escape hatch. The remaining problem is semantic: an agent can technically drive Fusion, but much of the work still resembles using a Python console plus screenshots.

`fusion.cad/v1` turns Fusion into an agent-oriented CAD workstation. The intended loop is:

```text
semantic read -> understand -> high-level change -> structural diff -> validation -> visual inspection -> commit/rollback
```

The API is designed around the working practices of an experienced CAD operator rather than a one-to-one wrapping of Autodesk API methods.

## 2. Design principles

1. **Semantic boundaries, not micro-tools.** Public tools represent coherent CAD activities. Tool count is not itself a contract.
2. **High-level by default, raw API as escape hatch.** Existing `fusion_mcp_execute(script)` remains available for exceptional cases but is not the normal agent workflow.
3. **Read before write.** Every mutation is revision-aware and can be checked against current model state.
4. **Structured identity.** Agents address known geometry through opaque references and discover unknown geometry through semantic selectors.
5. **Explicit coordinate frames.** Points, vectors, transforms, rays, planes, and bounding boxes never rely on implicit component/world/sketch space.
6. **Validation is part of mutation lifecycle.** Diff and validation are first-class outputs, not optional post-processing.
7. **Visual and semantic perception are peers.** Screenshot, camera, and screen-space pick are part of P0, not a late UI convenience.
8. **Capability truthfulness.** Version-dependent behavior is declared as supported/degraded/unavailable; the server never silently substitutes incompatible semantics.
9. **No hidden save.** A mutation, transaction commit, checkpoint, export, preview, or validation operation never implies document save.
10. **No silent metadata pollution.** Bridge metadata is transactional model state, not out-of-band bookkeeping.
11. **Bounded model context.** Large semantic reads and binary outputs externalize through retained artifacts instead of flooding MCP context.
12. **Golden-model acceptance.** Toy geometry is sufficient for unit tests, but release acceptance uses the real Schedule model copy.

## 3. Existing infrastructure retained

The following existing Bridge tools remain infrastructure and are not replaced by the domain API:

- `fusion_node_status`
- `fusion_tools`
- `fusion_call`
- `fusion_submit`
- `fusion_operation_status`
- `fusion_operation_result`

The Windows relay remains outbound-only. The local Fusion MCP remains the transport/escape-hatch layer. `fusion.cad/v1` is implemented as a stable domain facade above that substrate.

The existing async lifecycle remains authoritative:

```text
queued -> running -> succeeded | failed
```

Mutating commands are never automatically replayed after an uncertain transport result.

## 4. Public CAD tool surface

The v1 domain surface consists of semantic tool families. New operations may be added compatibly inside these families; breaking changes require a new contract version.

| Tool | Responsibility | First phase |
| --- | --- | --- |
| `fusion_read` | Semantic model reads, snapshots, feature/sketch reads, revisions, selectors | P0 |
| `fusion_inspect` | Measurements, geometric relations, interference/clearance | P0 |
| `fusion_view` | Camera, screenshots, visual pick, sections, named views | P0 |
| `fusion_metadata` | Tags, roles, provenance, semantic metadata | P0 |
| `fusion_style` | Logical text, visibility, appearances | P0 |
| `fusion_validate` | Model health, hygiene, mechanical and printability checks | P0 |
| `fusion_transaction` | Staging, preview, dry-run, commit, rollback, checkpoints, recipes | P0 foundation / P1 full |
| `fusion_sketch` | Parametric Sketch CRUD | P1 |
| `fusion_feature` | Feature CRUD | P1 |
| `fusion_component` | Components, occurrences, assembly operations | P1 |
| `fusion_transform` | Placement, alignment, layout, packing | P1 |
| `fusion_export` | STL/3MF/STEP and capability-gated DXF exports | P1 |

The number is intentionally not a hard limit. Future additions require a new semantic responsibility that cannot be expressed coherently through an existing family; micro-tools remain prohibited.

## 5. Strict request schemas

The logical envelope is shared:

```json
{
  "api_version": "fusion.cad/v1",
  "node_id": "fusion-workstation",
  "operation": "...",
  "target": {},
  "options": {},
  "expected_revision": "rev_...",
  "transaction_id": null
}
```

This is a conceptual envelope, not permission for free-form JSON. Each public MCP tool exposes a strict discriminated `oneOf` schema keyed by `operation`. `additionalProperties: false` is used wherever practical.

Examples:

```text
fusion_feature + operation=extrude -> ExtrudeRequest
fusion_feature + operation=fillet  -> FilletRequest
fusion_view    + operation=pick    -> PickRequest
fusion_export  + operation=step    -> StepExportRequest
```

An operation cannot accept parameters from another operation merely because they happen to be present in a generic `params` object.

## 6. Common result envelope

All domain operations return the same top-level shape where fields are applicable:

```json
{
  "api_version": "fusion.cad/v1",
  "status": "succeeded",
  "operation_id": "op_...",
  "document": {
    "document_ref": "doc_...",
    "model_revision": "rev_..."
  },
  "summary": "...",
  "data": {},
  "changed_refs": [],
  "warnings": [],
  "artifacts": [],
  "diff": null,
  "validation": null,
  "capabilities": null
}
```

Large results are retained as external JSON artifacts. Binary images and exports are exposed as dedicated resources. Base64 is not returned in ordinary model context.

## 7. Units and numeric representation

The domain facade normalizes Autodesk internal units.

| Quantity | Canonical unit |
| --- | --- |
| Length and coordinates | `mm` |
| Area | `mm^2` |
| Volume | `mm^3` |
| Angle | `deg` |
| Mass | `g` |
| Density | `g/cm^3` |

Engineering values may additionally include a Fusion expression when useful:

```json
{"value": 25.4, "unit": "mm", "expression": "1 in"}
```

Inputs accept canonical numeric values and, for operations backed by Fusion expressions, explicit expression strings such as `"Width / 2"` or `"45 deg"`.

## 8. Core type: CoordinateFrame

Every geometric value whose interpretation depends on coordinate space has an explicit frame.

```json
{
  "space": "world",
  "ref": null
}
```

Allowed spaces:

- `world` — root design/world coordinates; `ref` must be null.
- `component` — native component space; `ref` identifies the component.
- `occurrence` — assembly occurrence context; `ref` identifies the occurrence.
- `sketch` — sketch local coordinates; `ref` identifies the sketch.

The following values always carry a frame or inherit one from an explicitly documented enclosing object:

- `Point3`
- `Vector3`
- `Transform`
- `BoundingBox`
- `Ray`
- `Plane`

No operation may rely on an undocumented implicit frame.

## 9. Core type: EntityRef

Known Fusion entities are addressed through opaque Bridge references:

```json
{
  "ref": "ent_...",
  "kind": "face",
  "document_ref": "doc_...",
  "stability": "persistent",
  "native_type": "adsk::fusion::BRepFace",
  "name": null,
  "component_path": ["Root", "Panel:1"]
}
```

The public `ref` is not the Autodesk entity token. Bridge stores the native token plus resolver hints internally.

Supported stability classes:

- `persistent` — native persistent token available.
- `contextual` — restored through parent/context plus a geometry signature.
- `transient` — valid only for a specific snapshot/revision.

Resolution outcomes:

- `exact` — exactly one entity resolves.
- `split` — a former entity resolves to multiple current entities.
- `stale` — no current entity resolves.
- `wrong_document` — reference belongs to another document.
- `ambiguous` — contextual resolution has multiple plausible candidates.

`split` and `ambiguous` never silently select the first candidate.

## 10. Semantic selectors

`EntityRef` answers “how do I find a thing again?”; selectors answer “how do I find the right thing the first time?”.

Selector fields may include:

```json
{
  "kind": ["body"],
  "name": {"regex": "^AZURE_"},
  "component_path": ["Root", "LEFT"],
  "occurrence": null,
  "feature_type": null,
  "created_by": {"tool": "fusion_style", "operation": "text.create"},
  "tag": {"group": "bridge.cad/v1", "name": "layout", "value": "schedule"},
  "role": ["decorative_text"],
  "visible": true,
  "appearance": null,
  "bbox_region": null,
  "logical_object": null,
  "transaction_id": null,
  "recipe": null
}
```

Selector results always report `matched_count`, the normalized selector, and refs. Operations that require exactly one target fail with `SELECTOR_EMPTY` or `SELECTOR_AMBIGUOUS` instead of guessing.

## 11. Model revision model

Every active design has:

- `document_ref`
- `model_revision`
- zero or more `snapshot_id` values
- structural hashes for snapshot/diff use

`model_revision` changes on every observable model mutation, including:

1. Bridge-owned mutations.
2. Bridge metadata/provenance writes.
3. User changes made manually in Fusion.
4. Mutations from other add-ins or automation visible to the active design.

### 11.1 External-change detection invariant

`expected_revision` is useful only if manual model changes are observed before a new mutation or commit. Therefore the CAD service maintains an external-change detector using the strongest available Fusion signals for the installed runtime, with a deterministic fingerprint fallback.

Before any mutation or transaction commit, Bridge performs a revision freshness check. If the active model fingerprint no longer matches the revision baseline, it advances the model revision and returns `REVISION_CONFLICT` before applying the requested mutation.

A false-safe revision is prohibited: if the runtime cannot reliably establish freshness, the relevant mutation capability is reported `degraded` or `unavailable` rather than pretending revision safety exists.

## 12. Mutation revision safety

Every standalone mutation requires:

```json
{"expected_revision": "rev_17"}
```

If the current revision differs, the mutation is not started.

Inside a transaction, all staged work is bound to the transaction `baseline_revision`. Commit and preview re-check model freshness against that baseline.

## 13. Runtime capabilities

Capability truthfulness is part of the v1 foundation.

A capability has one of:

- `supported` — contract semantics are available and verified for this runtime.
- `degraded` — operation is available with explicitly reported semantic limitations.
- `unavailable` — operation cannot satisfy the contract on this runtime.

Capability records include:

```json
{
  "name": "view.pick",
  "state": "supported",
  "implementation": "native-preselect",
  "fusion_version": "...",
  "relay_version": "...",
  "limitations": []
}
```

Capabilities cover, at minimum:

- visual pick implementation
- transaction preview/abort/replay support
- supported feature operations
- sketch operation support
- DXF export support
- section-view support
- assembly/joint operations
- revision external-change detection quality

The schema may advertise an operation whose capability is `unavailable`, but invoking it must deterministically return a capability error. It must never silently switch to different semantics.

## 14. Snapshots

`fusion_read:model_snapshot` is the primary semantic “eyes” operation.

Default compact snapshot includes:

- document/design identity
- current revision
- components
- occurrences
- bodies
- sketches
- features/timeline
- user/model parameters
- visibility summary
- appearance summary
- bounding boxes
- health summary
- logical objects and roles summary
- counts and structural hashes

Faces and edges are not enumerated by default. Targeted reads or full-detail external artifacts expose topology when needed.

## 15. `fusion_read` P0 operations

P0 operations:

- `model_snapshot`
- `entity`
- `feature_tree`
- `sketch`
- `parameters`
- `visibility`
- `selection`
- `query` using semantic selectors
- `capabilities`

### 15.1 Feature tree

Feature records include:

- ref
- type
- name
- timeline index
- suppressed state
- health state
- diagnostic message
- inputs/dependencies where known
- outputs
- parent/children where known

Dependency edges are marked `exact`, `inferred`, or `unknown`. The API never fabricates exact dependency data unavailable from Fusion.

### 15.2 Sketch reads

Sketch reads include:

- sketch geometry
- dimensions
- constraints
- profiles
- fully-constrained state where the API exposes it
- linked/projected/reference state
- text objects
- health/diagnostics

The API does not invent a numeric degree-of-freedom count if the runtime cannot provide one reliably.

## 16. `fusion_inspect`

P0 operations:

- `describe`
- `bounding_box`
- `oriented_bbox`
- `centroid`
- `area`
- `perimeter`
- `volume`
- `distance`
- `minimum_distance`
- `angle`
- `parallel`
- `perpendicular`
- `coplanar`
- `concentric`
- `face_to_face_thickness`

Relation results include measured deviation and tolerance, not only a boolean.

P1 adds:

- `interference`
- `clearance_report`

Targets may use refs or selectors. Interference/clearance can include explicit role/tag filters so decoration and text are excluded without enumerating every body manually.

## 17. `fusion_view`

Visual perception is a P0 responsibility.

### 17.1 P0 operations

- `camera_read`
- `camera_set`
- `fit`
- `zoom_entity`
- `orient_to_face`
- `standard_view`
- `screenshot`
- `pick`

P1 adds:

- `section_create`
- `section_move`
- `section_disable`
- `named_view`

### 17.2 ViewRef

Every screenshot returns an immutable context object:

```json
{
  "view_ref": "view_...",
  "model_revision": "rev_...",
  "camera_revision": "cam_...",
  "visibility_revision": "vis_...",
  "width": 1920,
  "height": 1080,
  "image": "resource://..."
}
```

`view_ref` binds the image to:

- model revision
- complete camera state
- viewport dimensions
- effective visibility state
- section state if applicable

### 17.3 Immutable view invariant

Before `pick`, Bridge verifies that the active model, camera, and effective visibility still match the referenced view. If any changed, `VIEW_STALE` is returned. Bridge does not reinterpret old screenshot coordinates against a new view.

### 17.4 Screen-space pick

`fusion_view:pick` accepts normalized screenshot coordinates by default:

```json
{
  "operation": "pick",
  "view_ref": "view_123",
  "x": 0.63,
  "y": 0.41,
  "coordinate_space": "normalized",
  "filters": ["face", "edge", "body"]
}
```

It returns an ordered candidate stack with refs, kind, depth/order, world hit point where available, and camera distance where meaningful.

P0 contains a mandatory feasibility spike because Fusion does not expose a simple documented static `hitTest(x,y)` API. The implementation may use a native preselection/selection mechanism or a verified custom ray-picking implementation. The public contract is fixed; the capability record exposes the chosen implementation and limitations.

## 18. `fusion_metadata`

Operations:

- `get`
- `set`
- `remove`
- `query`
- `tag`
- `untag`
- `set_role`
- `clear_role`
- `provenance`

Reserved Bridge namespace:

```text
bridge.cad/v1
```

Roles include project-defined semantic values such as:

- `main_panel`
- `decorative_text`
- `name_plate`
- `print_layout`
- `mounting_hardware`

### 18.1 Transactional metadata invariant

Automatic Bridge attributes created for provenance/roles are written only inside the same Fusion transaction that creates or modifies the corresponding geometry.

Metadata writes:

- count as model mutations;
- advance model revision;
- participate in preview/abort/commit;
- disappear when the owning object or transaction is rolled back;
- are never written as a hidden post-commit follow-up.

No successful geometry commit is followed by an untracked metadata mutation.

### 18.2 Provenance

Bridge-created geometry records provenance sufficient for semantic discovery and cleanup:

- creating CAD tool
- operation
- operation ID
- transaction ID where applicable
- recipe where applicable
- logical object ref
- created revision
- role/tags

## 19. Logical text objects

Text is not represented to the agent as an unstructured collection of bodies.

`fusion_style:text.create` returns an opaque `TextRef` that relates:

```text
logical text
  -> source sketch
  -> SketchText
  -> generated profiles
  -> extrude/cut feature(s)
  -> current output bodies/faces
```

P0 text operations:

- `text_create`
- `text_read`
- `text_update`
- `text_delete`
- `text_extrude`
- `text_cut`

Inputs include Unicode text, font, height, alignment, orientation, position, flip, operation depth, target body/component, and boolean mode where applicable.

Outputs include `font_requested`, `font_used`, any fallback reason, profile diagnostics, provenance, logical current-generation outputs, and text revision.

An update replaces or rebinds the logical object's current generation; it must not silently accumulate disconnected legacy generations.

## 20. Visibility

P0 `fusion_style` visibility operations:

- `show`
- `hide`
- `set`
- `show_only`
- `isolate`
- `restore`

Results report both requested/local state and effective visibility through parent occurrence/component hierarchy.

Visibility changes are mutations and require revision safety unless performed inside a transaction.

## 21. Validation model

`fusion_validate` returns:

```text
verdict: GREEN | WARN | RED
profiles
checks_run
findings[]
summary
snapshot_id
model_revision
```

Each finding contains:

- check ID
- severity
- message
- entity refs
- evidence
- suggested action

Validation never silently repairs the model.

### 21.1 P0 profiles

- `parametric_health`
- `model_hygiene`
- `reference_integrity`
- `text_integrity`
- `pre_mutation`

P0 checks include:

- feature health
- sketch health
- reference integrity
- invalid/empty/zero-volume body sanity
- constraint state
- open/closed profile inventory
- timeline health
- duplicate/suspicious body detection
- orphaned generated geometry
- repeated logical generations
- role/provenance inconsistencies
- near-identical bbox/volume candidates
- legacy generated bodies
- dangling text outputs

An unconstrained sketch or open profile is policy-dependent; it is not globally RED.

### 21.2 P1 profiles

- `pre_commit`
- `mechanical_clearance`
- `pre_export`

### 21.3 P2 profile

- `fdm_printability`

P2 checks include bed fit, minimum wall/feature, overhang, bridges, unsupported islands, print clearance, and orientation scoring. Heuristic checks report analysis method, assumptions, and confidence.

## 22. Transaction model

The public staged-transaction contract is fixed, but its live feasibility is a P0 gate before P1 CRUD is built.

### 22.1 Begin

`fusion_transaction:begin` records:

- transaction ID
- document ref
- baseline revision
- baseline snapshot/hash
- capability state

### 22.2 Stage

Mutations supplied with `transaction_id` are stored as a declarative plan and are not permanently applied immediately.

### 22.3 Preview

`preview` temporarily applies the plan, then produces:

- preview snapshot
- structural diff
- requested validations
- optional screenshot/view ref
- generated preview refs

The preview state is aborted before returning to normal model state.

### 22.4 Commit

`commit` re-checks the baseline revision and runtime state, replays the declarative plan in one Fusion command/transaction, writes provenance inside that same transaction, produces final diff/validation, and becomes one logical Undo operation where the runtime supports the contract.

### 22.5 Rollback

Before commit, rollback discards the staged plan. After commit, automatic rollback/undo is permitted only when the Bridge transaction remains the current safe head; otherwise `TRANSACTION_CONFLICT` is returned.

### 22.6 Dry-run

A mutator with `dry_run=true` behaves as an implicit transaction:

```text
begin -> stage -> preview -> diff -> validate -> abort
```

The persistent model remains unchanged.

### 22.7 P0 transaction feasibility gate

Before P1 Sketch/Feature CRUD implementation, live Fusion acceptance must prove:

1. baseline A;
2. preview plan;
3. snapshot/diff/validation of preview B;
4. abort and proof that model returns to A;
5. ref resolution after abort;
6. replay of the same declarative plan;
7. commit result equivalent to accepted preview semantics;
8. one Undo returns to A;
9. manual edit between begin and commit produces conflict;
10. generated refs/topology and metadata do not leak from preview;
11. preview abort leaves no hidden side state relevant to subsequent operations.

If this gate fails, P1 does not proceed on top of a fake transaction abstraction. Internal implementation is redesigned while preserving the public v1 contract where feasible.

## 23. Structural diff

P1 diff compares semantic state, not raw meshes by default.

Tracked categories:

- components
- occurrences
- features
- bodies
- sketches
- parameters
- logical text objects
- metadata/roles
- visibility
- appearances
- bounding boxes
- area/volume
- health
- entity resolution status

Results include `created`, `deleted`, `modified`, and unchanged counts. Modified records include before/after/delta fields appropriate to their kind.

## 24. P1 Sketch CRUD

`fusion_sketch` uses a batch action DSL rather than one MCP tool per sketch primitive.

Operations support:

- create/read/update/delete sketch
- line
- arc
- circle
- rectangle
- slot
- spline
- point
- project
- offset
- trim
- construction/reference geometry
- dimensions
- geometric constraints

Batch action IDs allow later actions in one request to refer to geometry created earlier in the same plan.

## 25. P1 Feature CRUD

`fusion_feature` operations:

- `create`
- `update`
- `delete`
- `suppress`
- `unsuppress`
- `batch`

Feature kinds v1:

- extrude
- revolve
- sweep
- loft
- hole
- fillet
- chamfer
- shell
- draft
- pattern
- mirror
- combine
- split

Every feature mutation returns created/changed refs and participates in transaction/revision/provenance semantics.

## 26. P1 components and transforms

`fusion_component` P1 operations:

- create/delete component
- create/copy occurrence
- rename
- replace where supported
- set active

`fusion_transform` P1 operations:

- move
- rotate
- align
- distribute
- grid
- pack
- copy N
- orient face to plane
- lay flat

`pack` returns placed/unplaced refs, bounds, spacing, rotations, and bed/region constraints.

## 27. P1 appearances

`fusion_style` P1 adds:

- appearance read
- appearance assign
- appearance clone
- appearance create RGB
- appearance clear

Results identify effective appearance and inheritance source.

## 28. P1 interference and clearance

`fusion_inspect` P1 supports explicit bodies/occurrences or selectors, exclusion by semantic role/tag, and minimum-clearance reporting.

Decorative text can therefore be excluded from mechanical interference analysis without manually listing every text body.

## 29. P1 checkpoints

`fusion_transaction` adds:

- `checkpoint_create`
- `checkpoint_restore`
- `checkpoint_list`

Checkpoint state includes snapshot/revision, transaction-chain position, refs, and structural hash.

Checkpoint restore can automatically unwind only known consecutive Bridge-owned mutations. If manual/external model changes occurred, restore fails `CHECKPOINT_DIVERGED` instead of undoing user work.

## 30. Export

STL, 3MF, and STEP move to P1 so the high-level modeling workflow is complete without raw Python.

P1 operations:

- `stl`
- `3mf`
- `step`

Scopes:

- document
- component
- occurrence
- body
- bodies
- layout

Options include refinement, per-body/grouped behavior, names, pre-export validation, and fail-on-validation policy.

Exports return retained artifacts/resources, not only local Windows paths.

DXF is part of the public family but remains runtime capability-gated until the installed Fusion API can satisfy the required semantics. Unsupported DXF returns a capability result rather than falling back silently.

## 31. P2 advanced assembly and views

`fusion_component` P2 adds:

- joint create/update/delete
- rigid group create/delete
- ground/unground

`fusion_view` advanced support includes stable section workflows and runtime-supported named views not completed in P1.

## 32. P2 printability

`fusion_validate:fdm_printability` accepts a printer/process profile such as:

```json
{
  "bed": [220, 220, 220],
  "nozzle": 0.4,
  "layer_height": 0.2
}
```

Checks include:

- bed fit
- minimum wall
- minimum feature
- overhang
- bridge candidates
- unsupported islands
- print clearance
- orientation scoring

Heuristic results expose confidence, method, and assumptions. The API does not claim slicer-equivalent certainty when only geometric analysis was performed.

## 33. P2 recipes

Recipes are versioned declarative orchestration over the same v1 tools, not a second modeling engine.

Examples:

- `magnet_pocket/v1`
- `dovetail_joint/v1`
- `name_plate/v1`
- `vent_slot_array/v1`

Recipes execute through `fusion_transaction:run_recipe` and inherit revision, preview, validation, diff, provenance, and rollback semantics.

## 34. Save safety invariant

No CAD domain operation saves the Fusion document unless the user explicitly requests save through the existing document save pathway or a future explicitly confirmed domain save operation.

Specifically, these do **not** imply save:

- mutation
- transaction commit
- rollback
- checkpoint
- preview
- validation
- screenshot
- export

Attempted save without explicit confirmation returns `SAVE_CONFIRMATION_REQUIRED`.

## 35. Error model

Required v1 error codes include:

| Code | Meaning |
| --- | --- |
| `NO_ACTIVE_DESIGN` | No active Fusion design |
| `WRONG_DOCUMENT` | Ref belongs to another document |
| `REF_STALE` | Entity no longer resolves |
| `REF_SPLIT` | Entity resolves to multiple descendants |
| `REF_AMBIGUOUS` | Resolver cannot choose a unique entity |
| `TYPE_MISMATCH` | Target kind is invalid for operation |
| `SELECTOR_EMPTY` | Selector matched nothing where a target is required |
| `SELECTOR_AMBIGUOUS` | Selector matched multiple entities where exactly one is required |
| `INVALID_ARGUMENT` | Request violates strict operation schema or semantic constraints |
| `PRECONDITION_FAILED` | Current geometry/state cannot satisfy operation |
| `UNSUPPORTED_GEOMETRY` | Algorithm does not support supplied geometry |
| `CAPABILITY_UNAVAILABLE` | Runtime cannot provide required v1 semantics |
| `CAPABILITY_DEGRADED` | Operation requires explicit acceptance of reported limitation |
| `REVISION_CONFLICT` | Model changed since caller baseline |
| `VIEW_STALE` | Screenshot context no longer matches model/camera/visibility |
| `FUSION_API_ERROR` | Native Fusion API operation failed |
| `VALIDATION_FAILED` | Validation policy blocked commit/export |
| `TRANSACTION_CONFLICT` | Safe transaction commit/rollback cannot proceed |
| `CHECKPOINT_DIVERGED` | Safe restore is impossible after external divergence |
| `SAVE_CONFIRMATION_REQUIRED` | Save attempted without explicit permission |
| `OPERATION_UNCERTAIN` | Transport lost reliable terminal confirmation |

## 36. Async execution policy

`execution=auto` selects sync only for bounded fast reads. Expensive snapshots/validation may use async. Mutations, transaction preview/commit, and exports default to async operation tracking.

A synchronous timeout never authorizes replay. If an operation continues beyond the synchronous window, its durable `operation_id` remains authoritative.

## 37. Golden acceptance model: Schedule

The release acceptance model is a disposable copy of the real Schedule design, not a toy cube.

The golden model intentionally exercises:

- Unicode text
- many bodies
- previous/legacy generated bodies
- layout
- visibility hierarchy
- appearances
- text provenance
- interference filtering
- export
- real camera/screenshot behavior

The original model is not modified or saved during acceptance.

### 37.1 P0 golden gate

Without agent-authored raw Python:

1. open a Schedule copy;
2. obtain semantic snapshot;
3. understand components/bodies/features;
4. detect suspicious/legacy generated bodies;
5. find/read Unicode logical text;
6. discover targets using selector roles/tags;
7. inspect geometry;
8. validate model health/hygiene;
9. update logical text with revision safety;
10. change visibility/isolate;
11. orient/fit camera;
12. obtain screenshot artifact/view ref;
13. pick a visible face from screenshot coordinates;
14. resolve returned ref semantically;
15. undo mutation safely;
16. prove no save occurred.

### 37.2 P0 feasibility gates

Two feasibility gates are mandatory before P1 implementation:

- screen-space pick on real Fusion with immutable `view_ref` semantics;
- transaction preview -> abort -> replay -> commit -> single Undo determinism.

### 37.3 P1 golden gate

1. begin transaction on Schedule copy;
2. stage parametric change;
3. preview;
4. inspect structural diff;
5. validate;
6. inspect screenshot;
7. rollback and prove baseline restored;
8. replay and commit;
9. prove one Undo restores baseline;
10. high-level pack 36 name plates;
11. run targeted interference excluding decorative text;
12. export grouped 3MF/STL/STEP artifacts;
13. prove original source file remains unsaved unless explicitly authorized.

### 37.4 P2 golden gate

1. apply 220 x 220 printer profile;
2. bed-fit validation;
3. minimum wall/feature analysis;
4. bridge/overhang/unsupported-island analysis;
5. orientation scoring;
6. assembly/advanced view checks;
7. run at least one versioned recipe;
8. produce final validated export artifacts.

## 38. Phase scope freeze

The architecture and P0/P1/P2 boundaries are frozen by this spec. New feature ideas do not enter v1 unless implementation discovers a concrete architectural blocker that prevents an accepted invariant or acceptance gate from being satisfied.

### P0 — semantic and visual foundation

- strict domain schemas/result envelope
- EntityRef/resolver
- CoordinateFrame
- model revision including manual/external-change detection
- runtime capabilities
- snapshots/read/query/selectors
- inspect
- view/camera/screenshot/pick
- metadata/tags/roles/provenance
- logical Unicode text
- visibility
- validation profiles/model hygiene
- transaction feasibility engine/spike
- Schedule P0 acceptance

### P1 — safe high-level modeling

- full staged transaction engine
- structural diff
- Sketch CRUD
- Feature CRUD
- components/occurrences
- transforms/layout/pack
- appearances
- interference/clearance
- checkpoints
- section/named-view workflow where supported
- STL/3MF/STEP export
- Schedule P1 acceptance

### P2 — advanced engineering workflows

- FDM printability
- assembly joints/rigid groups/grounding
- advanced view/section capabilities not completed in P1
- capability-gated DXF
- versioned parametric recipes
- Schedule P2 acceptance

## 39. Implementation invariants

These four invariants are normative and must be tested explicitly:

1. **Revision truth:** `model_revision` detects manual/external model changes before a later mutation/commit. `expected_revision` may never provide false safety.
2. **Transactional metadata:** automatic `bridge.cad/v1` metadata/provenance is written only within the same transaction as geometry; metadata mutation is revisioned and rolls back with its object. No hidden post-commit metadata writes.
3. **Immutable view context:** `view_ref` binds model revision, camera, effective visibility, viewport dimensions, and section state. Any mismatch before pick yields `VIEW_STALE`.
4. **Capability truth:** Fusion-version-dependent functions explicitly report supported/degraded/unavailable. No operation silently switches to materially different behavior.

## 40. Non-goals

- No attempt to expose every Autodesk class/method as an MCP tool.
- No replacement of raw Python escape hatch for rare unsupported work.
- No UI automation when a reliable Fusion API path exists.
- No silent healing/deletion of suspicious geometry during validation.
- No global promise that topology refs survive arbitrary destructive edits.
- No slicer-equivalent guarantee from P2 geometric printability heuristics.
- No automatic document save.

## 41. Release criteria

A phase is complete only after all of:

1. contract/unit tests;
2. targeted integration tests;
3. VPS full test suite;
4. `ruff`/repository lint gate;
5. `git diff --check`;
6. independent code review;
7. live Fusion acceptance for that phase;
8. golden Schedule acceptance for that phase;
9. no unresolved capability claims that contradict observed runtime behavior.

The next phase does not begin before the current phase gate is accepted.
