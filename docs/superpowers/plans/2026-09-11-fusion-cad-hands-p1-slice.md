# Fusion CAD Hands P1 Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the offline, testable first Shimmer-backed `fusion_sketch`/`fusion_feature` slice while preserving P0 revision/ref/transaction invariants.

**Architecture:** `fusion.cad/v1` keeps the logical workstation contract. A small provider router chooses reference/rich/eyes nodes; Bridge-side adapters compile strict sketch/feature requests into a source-controlled, allow-listed Shimmer overlay envelope that performs the private provider guard and PTransaction commit/abort on Fusion's main thread. Public refs and `rev_N` remain Bridge-owned.

**Tech Stack:** Python 3.12+, Pydantic v2, MCP/FastMCP, existing `DesktopNodeService`, existing `FusionCadService`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-11-fusion-cad-hands-p1-slice-design.md`

## Global Constraints

- Preserve every accepted P0 `fusion.cad/v1` safety invariant.
- Do not route normal modeling through raw Autodesk `fusion_mcp_execute` or raw agent-authored Python.
- Do not expose Shimmer indices, names-as-identity, native tokens, or provider node ids in public domain results.
- Shimmer arbitrary-code capability stays disabled.
- No save/close side effect.
- No live Fusion or protected `Schedule` mutation during this offline plan.
- No push, merge, deploy, or production-service changes.
- TDD: every production behavior starts with a failing test observed before implementation.

---

### Task 1: Provider role routing and configuration

**Files:**
- Modify: `app/settings.py`
- Create: `app/fusion_cad/providers.py`
- Modify: `app/container.py`
- Test: `tests/unit/test_fusion_cad_providers.py`
- Test: `tests/unit/test_settings.py`

**Interfaces:**
- Produces `FusionCadProviderRoute(reference_node: str, rich_node: str | None, eyes_node: str | None)`.
- Produces `FusionCadProviderRouter.route(logical_node: str) -> FusionCadProviderRoute`.
- `FusionCadService` receives the router by dependency injection; absence of a rich role fails closed for Hands operations.

- [x] Write RED tests proving logical nodes map to explicit roles, unknown logical nodes fall back to reference-only, invalid node ids are rejected, and no literal `fusion-workstation -> fusion-shimmer` rule exists in router code.
- [x] Run the focused tests and confirm the expected missing-type/settings failures.
- [x] Add the minimal frozen Pydantic settings and router implementation; wire it through `ApplicationContainer` construction without changing existing P0 behavior.
- [x] Run focused tests GREEN plus existing settings/container regressions.
- [x] Review diff and commit this milestone.

### Task 2: Source-controlled Shimmer guarded overlay

**Files:**
- Create: `ops/fusion_shimmer_overlay/README.md`
- Create: `ops/fusion_shimmer_overlay/manifest.json`
- Create: `ops/fusion_shimmer_overlay/addin_bridge_cad.py`
- Create: `ops/fusion_shimmer_overlay/server_bridge_cad.py`
- Create: `ops/fusion_shimmer_overlay/install.py`
- Test: `tests/unit/test_fusion_shimmer_overlay.py`

**Interfaces:**
- Pinned upstream SHA: `97a06e76c289420a721590ddcab334f5f3dc3178`.
- Add-in ops: `bridge.cad_guard`, `bridge.cad_apply`.
- Sidecar MCP tools: `_bridge_cad_guard`, `_bridge_cad_apply`.
- Apply payload includes `expected_guard`, `mode` (`commit` or `preview`), and an allow-listed declarative operation list.
- Apply result includes private `guard_before`, `guard_after`, `effects`, and created/changed entity-token evidence; it never saves/closes a document.

- [x] Write RED tests using a fake Shimmer module/registry that prove disallowed ops are rejected before delegation, guard mismatch performs zero mutations, commit uses exactly Start then Commit, preview uses exactly Start then Abort and requires restored guard, and an exception after Start attempts Abort.
- [x] Write RED installer tests proving a wrong upstream SHA or unexpected target file hash fails closed and no files are modified.
- [x] Run tests and verify RED for missing overlay modules.
- [x] Implement the smallest overlay helpers around the existing Shimmer registry; do not reimplement sketch/feature geometry algorithms.
- [x] Implement the pinned overlay installer as an offline file transform/copy with backup-free fail-closed semantics; actual Windows deployment is out of scope here.
- [x] Run overlay tests GREEN, compile the overlay modules, and scan for arbitrary-code dispatch or save/close calls.
- [x] Review diff and commit this milestone.

### Task 3: Strict public Hands request schemas and tool surface

**Files:**
- Modify: `app/fusion_cad/requests.py`
- Modify: `app/fusion_cad/schemas.py`
- Modify: `app/tools/fusion.py`
- Test: `tests/contract/test_fusion_cad_schemas.py`
- Test: `tests/contract/test_tool_surface.py`

**Interfaces:**
- Produces `FusionSketchRequest` with `create` and `batch` operations.
- Produces `FusionFeatureRequest` with `create` and nested kinds `extrude`, `hole`, `fillet`, `chamfer`.
- Committed requests require `expected_revision`; `dry_run=true` may still require a known baseline revision so preview is bound to explicit model state.
- Sketch geometry actions have stable `id`; constraint/dimension entity operands accept prior action ids/subrefs or opaque `ent_*` refs.

- [x] Write RED schema tests for valid create/batch/feature examples, `additionalProperties:false`, finite dimensions, duplicate/forward action refs, illegal dimension `entity_two` combinations, and missing `expected_revision`.
- [x] Write RED surface tests requiring `fusion_sketch` and `fusion_feature` and their strict schemas.
- [x] Run RED and confirm failures are caused only by absent Hands schemas/tools.
- [x] Implement minimal Pydantic discriminated unions and JSON schema adapters.
- [x] Register thin MCP handlers through the existing `make_domain_handler`; business logic remains in `FusionCadService`/provider adapters.
- [x] Run contract tests GREEN plus the existing P0 schema/tool-surface suite.
- [x] Review diff and commit this milestone.

### Task 4: Bridge-side Shimmer adapter, guard binding, and opaque refs

**Files:**
- Create: `app/fusion_cad/shimmer.py`
- Modify: `app/fusion_cad/service.py`
- Modify: `app/fusion_cad/refs.py` only if a small provider-token helper is required
- Test: `tests/unit/test_fusion_cad_shimmer.py`
- Test: `tests/integration/test_fusion_cad_hands.py`

**Interfaces:**
- Produces `ShimmerHandsAdapter.guard(logical_node, document_ref) -> ProviderGuardEvidence`.
- Produces `ShimmerHandsAdapter.apply(..., mode, expected_guard, operations) -> HandsApplyEvidence`.
- Produces service-owned `(document_ref, model_revision) -> provider_guard` binding only after the `guard A -> authoritative observation -> guard B` coherence check.
- Converts public `ent_*` inputs to private tokens; registers token-backed public refs only after proven commit.

- [ ] Write RED tests for rich-node absence, A/B guard mismatch, stale expected revision, token kind mismatch, provider error mapping, preview ref non-registration, and commit ref registration.
- [ ] Run RED and confirm the missing adapter/service path is the cause.
- [ ] Implement the minimal adapter using `DesktopNodeService.call` against `_bridge_cad_guard`/`_bridge_cad_apply`; keep raw provider payloads private.
- [ ] Add coherence binding using the existing P0 revision tracker and authoritative observation path without creating a second public revision sequence.
- [ ] Add result normalization into existing `CadResult`/opaque refs with strict provider error translation.
- [ ] Run unit/integration GREEN plus P0 revision/ref regressions.
- [x] Review diff and commit this milestone.

### Task 5: Standalone sketch/feature execution and dry-run

**Files:**
- Modify: `app/fusion_cad/service.py`
- Modify: `app/fusion_cad/capabilities.py`
- Test: `tests/integration/test_fusion_cad_hands.py`
- Test: `tests/unit/test_fusion_cad_capabilities.py`

**Interfaces:**
- `fusion_sketch`/`fusion_feature` route to the rich role but keep the logical node/document context.
- `dry_run=true` dispatches preview envelope and returns diff/effect evidence without revision advancement/ref registration.
- Commit dispatch returns only after proven provider commit evidence is normalized; uncertain outcomes are not replayed.
- Hands capability remains `degraded`/not runtime-verified until the later live gate.

- [ ] Write RED end-to-end service tests for sketch create, symbolic batch compile, extrude, fillet, dry-run baseline restoration, stale guard refusal, and uncertain provider outcome.
- [ ] Run RED and verify exact missing execution behavior.
- [ ] Implement classification/capability dispatch and minimal compilation to the Shimmer allow-listed envelope.
- [ ] Run GREEN focused Hands integration tests and all existing Fusion service/capability regressions.
- [ ] Run a falsification sweep: malformed symbolic refs, dimension contract mismatch, wrong document, provider reconnect/session generation change, guard mismatch, preview abort mismatch, and provider error after Start.
- [x] Review diff and commit this milestone.

### Task 6: Offline phase gate and independent review

**Files:**
- Modify: `docs/operations/fusion-cad-executor-guide.md`
- Modify: `docs/research/fusion-cad-agent-operational-roadmap-2026-09-11.md`

**Interfaces:**
- Documents exact offline-supported Hands surface and clearly marks live runtime verification pending.
- Does not claim explicit `fusion_transaction` sketch/feature replay support yet.

- [ ] Add bounded operator/developer documentation for provider roles, overlay installation boundary, Hands tools, and live-gate requirements.
- [ ] Run `git diff --check`, overlay compile checks, focused Hands tests, the complete Fusion regression suite, then the repository's full offline test gate if time permits.
- [ ] Inspect final `git status`, `git diff --stat`, and load-bearing diff sections for accidental P0 changes or token leakage.
- [ ] Dispatch one independent Codex review against base `6bdda8b0d03fba8fb9fa5118c0fc07cf01b1e9d7..HEAD`; fix only proven Critical/Important findings via new RED tests.
- [ ] Re-run affected tests plus the full Fusion gate after repairs.
- [ ] Stop before live Fusion, push, merge, deploy, or explicit transaction-plan expansion and report the exact remaining live gate.
