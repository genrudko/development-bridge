# Blender Bridge / Hub v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows-first Blender MCP Hub that aggregates multiple Blender/print providers, supports same-turn operator interaction, serializes mutations, and carries a validated 3D-print pipeline through 3MF and OrcaSlicer.

**Architecture:** Development Bridge remains the remotely reachable VPS control plane. A Windows Blender Hub supervises upstream MCP providers and exposes their tool catalogs through stable namespaces. The core stays provider-agnostic: reads may overlap, writes share one global mutation gate, and `operator.ask` keeps one MCP request pending until the Windows operator answers so the model continues the same turn.

**Tech Stack:** Python 3.12+, asyncio, Development Bridge MCP 2.0 stack, existing DesktopNode transport patterns, Windows Python GUI/add-on integration, upstream Blender/3MF/Orca MCP providers.

**Spec:** `docs/superpowers/specs/2026-09-13-blender-bridge-hub-v1-design.md`

## Global Constraints

- Do not port the Fusion semantic facade into Blender.
- Upstream provider functionality is reused before custom Blender-domain code is written.
- Provider versions are pinned and updates are explicit.
- Reads may overlap; all mutating provider calls share one global write lock.
- Unknown mutation classification defaults conservatively to mutating.
- `operator.ask` must return the operator answer to the same pending MCP tool call/turn.
- Windows connectivity is outbound toward the VPS; no arbitrary inbound shell surface.
- Transport disconnect during an ambiguous mutation must never trigger automatic replay.
- Print settings are based on real printer/nozzle/filament preset and calibration context; unknown values remain unknown.
- Geometry 3MF and slicer-owned print project are separate artifacts.
- No production deployment or systemd modification without explicit owner authorization.

---

### Task 1: Provider catalog and global mutation gate

**Files:**
- Create: `app/blender_bridge/__init__.py`
- Create: `app/blender_bridge/models.py`
- Create: `app/blender_bridge/service.py`
- Test: `tests/unit/test_blender_bridge_core.py`

**Interfaces:**
- Produces: `ToolSpec`, `ProviderClient`, `ProviderSpec`, `PublicTool`, `BlenderBridgeService.refresh_catalog()`, `BlenderBridgeService.resolve_tool()`, `BlenderBridgeService.call_tool()`.
- Public tool naming: `<provider_namespace>.<upstream_tool_name>`.

- [ ] Write failing tests proving two providers with overlapping upstream names become distinct public names.
- [ ] Run the focused tests and confirm failure because `app.blender_bridge` does not exist.
- [ ] Implement immutable provider/tool models and dynamic catalog discovery.
- [ ] Implement a single asyncio mutation lock shared by all mutating tools while read-only calls bypass it.
- [ ] Run focused tests proving cross-provider writes serialize and reads can overlap.
- [ ] Run `git diff --check` and commit `feat: add Blender Hub provider core`.

### Task 2: Blocking same-turn operator broker

**Files:**
- Create: `app/blender_bridge/operator.py`
- Modify: `app/blender_bridge/models.py`
- Test: `tests/unit/test_blender_bridge_operator.py`

**Interfaces:**
- Produces: `OperatorPrompt`, `OperatorAnswer`, `OperatorBroker.ask()`, `OperatorBroker.answer()`, `OperatorBroker.pending_prompt_ids()`.
- `ask()` does not complete until `answer()` resolves the matching prompt, timeout occurs, or cancellation propagates.

- [ ] Write a failing asyncio test that starts `ask()` as a task and proves it remains pending after publish.
- [ ] Add a reply with the exact prompt id and prove the original task returns that reply.
- [ ] Add tests for unknown/duplicate answer rejection.
- [ ] Add timeout and cancellation tests and verify pending state is cleaned up.
- [ ] Implement only the broker state/future correlation required by those tests.
- [ ] Run focused tests plus Task 1 regression and commit `feat: add same-turn Blender operator broker`.

### Task 3: Print context and optimization input contract

**Files:**
- Create: `app/blender_bridge/printing.py`
- Test: `tests/unit/test_blender_bridge_printing.py`

**Interfaces:**
- Produces: `PrinterContext`, `NozzleContext`, `FilamentContext`, `PrintContext`, `PrintGoal`.
- `PrintContext.to_provider_payload()` is the stable provider-neutral payload for slicer adapters.

- [ ] Write failing tests carrying real printer preset, nozzle diameter/material, filament preset/material, flow ratio, pressure advance, max volumetric speed, and temperatures.
- [ ] Write failing validation tests for non-physical nozzle and flow values.
- [ ] Implement dataclasses with `None` for unknown calibration rather than inferred defaults.
- [ ] Add goals: `balanced`, `dimensional_accuracy`, `strength`, `surface_quality`, `fastest_safe`.
- [ ] Run focused tests and commit `feat: add Blender print context`.

### Task 4: Provider adapter and reconnect contract

**Files:**
- Create: `app/blender_bridge/provider_transport.py`
- Modify: `app/blender_bridge/models.py`
- Test: `tests/unit/test_blender_bridge_provider_transport.py`

**Interfaces:**
- Produces: a provider adapter protocol that can `list_tools`, `call_tool`, report health/version/pin, and classify tool mutation behavior.
- Produces explicit terminal states for `completed`, `failed`, and `uncertain` provider calls.

- [ ] Write failing tests for provider health and catalog refresh after reconnect.
- [ ] Write a failing test proving a transport drop during a mutating call becomes `uncertain` and is not replayed.
- [ ] Write a read-only retry/reconnect test only where the operation is explicitly idempotent.
- [ ] Implement the smallest transport abstraction that satisfies the contract without binding the core to one upstream MCP implementation.
- [ ] Run Task 1-4 unit tests and commit `feat: add Blender provider transport contract`.

### Task 5: Development Bridge service/container/tool integration

**Files:**
- Modify: `app/container.py`
- Create: `app/tools/blender.py`
- Modify: `app/tools/registry.py`
- Add/modify settings only if required after transport shape is proven.
- Test: `tests/contract/test_blender_bridge_tools.py`
- Test: `tests/integration/test_blender_bridge_tools.py`

**Interfaces:**
- Produces a Development Bridge `blender_*` control surface for Hub status/catalog/call plus same-turn operator APIs.
- Under compact tool surface, Blender tools must remain discoverable through existing guide/compact mechanisms.

- [ ] Write contract tests for tool names and JSON schemas before registration.
- [ ] Add `BlenderBridgeService` to `ApplicationContainer` with dependency injection for tests.
- [ ] Register Blender tools in `build_tool_registry()` without changing existing Fusion behavior.
- [ ] Add integration tests with fake providers and same-turn answer correlation.
- [ ] Run closest registry/core/startup tests and commit `feat: expose Blender Hub through Development Bridge`.

### Task 6: Windows Hub transport and supervisor

**Files:**
- Create: `agents/blender_hub_runtime.py`
- Create: `agents/START_BLENDER_HUB.ps1`
- Create: `agents/START_BLENDER_HUB.cmd`
- Test: `tests/unit/test_blender_hub_runtime.py`

**Interfaces:**
- Windows initiates the persistent outbound connection to Development Bridge.
- Hub reports providers, pins, Blender/Orca availability, active calls, write-lock state, and operator messages.

- [ ] Write tests for provider process configuration and namespacing.
- [ ] Write transport heartbeat/reconnect tests that preserve in-flight mutation uncertainty.
- [ ] Implement supervisor startup/shutdown/restart with per-provider failure isolation.
- [ ] Add pinned provider configuration rather than implicit latest pulls.
- [ ] Run offline tests and commit `feat: add Windows Blender Hub runtime`.

### Task 7: Operator GUI and Blender-side inbox

**Files:**
- Create: `agents/blender_hub_gui.pyw`
- Create: `ops/blender_bridge_addon/__init__.py`
- Create focused UI tests/static contract tests where practical.

**Interfaces:**
- One backend operator inbox is rendered in Hub GUI and optionally Blender N-panel.
- Supports text, confirm/reject, finite choice, and non-blocking notify.

- [ ] Add a deterministic UI state model separate from widgets.
- [ ] Implement pending prompt rendering and reply submission.
- [ ] Show provider health/pins, Blender/Orca state, write lock, active calls, and logs.
- [ ] Add viewport-pick request protocol after text/choice flow is green.
- [ ] Implement object/face pick response without making the model wait for a new ChatGPT turn.
- [ ] Run UI state tests and commit `feat: add Blender Hub operator UI`.

### Task 8: Blender providers and live dual-provider bake-off

**Files:**
- Create: `ops/blender_bridge/providers.yaml` or equivalent configuration.
- Create installer/update scripts under `ops/blender_bridge/` or `agents/` following existing Windows patterns.
- Add acceptance documentation under `docs/operations/`.

**Interfaces:**
- Initial namespaces: `dcc`, `research`.
- Research provider remains external/unchanged while license status is unresolved.

- [ ] Pin exact upstream revisions selected during installation.
- [ ] Bring both providers online against one Blender session.
- [ ] Verify provider A mutation is visible to provider B read/inspection.
- [ ] Verify one global write lock prevents overlapping provider mutations.
- [ ] Perform a same-turn `operator.ask`, answer in Hub, and continue the same ChatGPT turn with another Blender call.
- [ ] Record bounded acceptance evidence and commit `test: qualify Blender dual-provider hub`.

### Task 9: 3MF preflight and validation providers

**Files:**
- Add provider configuration/pins for Blender print-prep and 3MF validation providers.
- Create: `app/blender_bridge/print_pipeline.py`
- Test: `tests/unit/test_blender_bridge_print_pipeline.py`

**Interfaces:**
- Produces explicit stages/results for `mesh_preflight`, `geometry_3mf`, and `validate_3mf`.
- Validation failure prevents the pipeline from pretending the geometry artifact is print-ready.

- [ ] Write failing orchestration tests for preflight -> export -> validate ordering.
- [ ] Add a failure-path test proving validation errors stop the pipeline before slicer handoff.
- [ ] Keep repair opt-in rather than silently mutating geometry.
- [ ] Preserve geometry 3MF as its own retained artifact.
- [ ] Run focused tests and commit `feat: add Blender 3MF print pipeline`.

### Task 10: OrcaSlicer provider integration and profile physics gate

**Files:**
- Add/pin OrcaSlicer MCP provider configuration.
- Modify: `app/blender_bridge/print_pipeline.py`
- Test: `tests/unit/test_blender_bridge_orca.py`

**Interfaces:**
- Consumes: validated geometry 3MF plus `PrintContext`.
- Produces: profile application result, physics validation result, slice result, warnings, timing/material metrics, and final project/export artifact references.

- [ ] Write tests proving printer/nozzle/filament presets and known calibration are passed unchanged to the slicer adapter.
- [ ] Add a blocked-physics test that forbids slicing/export as success.
- [ ] Add variant-comparison tests returning measurements/warnings without asserting a universal winner.
- [ ] Add explicit final-project save/export handling; no implicit save.
- [ ] Run focused tests and commit `feat: integrate OrcaSlicer print optimization`.

### Task 11: Full offline gate and one deliberate live acceptance

**Files:**
- Update: `docs/operations/blender-bridge-hub.md`
- Update plan/spec only if implementation evidence requires a documented contract correction.

**Interfaces:**
- Acceptance covers Blender, same-turn operator interaction, 3MF, and Orca end-to-end.

- [ ] Run all Blender Hub unit/contract/integration tests.
- [ ] Run the closest existing DesktopNode/tool-registry/startup regressions.
- [ ] Run `git diff --check` and inspect final status/diff.
- [ ] Perform one live Blender acceptance only after offline green.
- [ ] Export geometry 3MF, validate it, load it in Orca with the actual printer/nozzle/filament context, compare at least two process variants, and save a final project artifact explicitly.
- [ ] Document exact pins, limitations, and live evidence.
- [ ] Do not merge/deploy automatically; hand the verified branch to the owner for the next decision.
