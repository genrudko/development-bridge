# Blender Bridge / Hub v1 Continuation Plan and Successor Handoff

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development. Work task-by-task with TDD, frequent bounded commits, and evidence before claims.

**Goal:** Continue the existing Blender Bridge / Hub v1 implementation from the verified feature-branch checkpoint, finish local provider transports and print-provider integration, expose a real Orca project-3MF export capability instead of faking it, then qualify the complete Blender -> geometry 3MF -> validation -> Orca optimization -> project 3MF path offline and live.

**Architecture:** Development Bridge remains the VPS control plane. A Windows Blender Hub multiplexes local providers through stable namespaces and one conservative global mutation gate. Blender-domain breadth comes from reusable upstream providers; Development Bridge owns orchestration, uncertainty/no-replay handling, operator continuity, retained evidence, and the provider-neutral print pipeline.

**Tech Stack:** Python 3.12+, asyncio, MCP, Development Bridge DesktopNode transport, Windows Hub/GUI, `dcc-mcp-blender`, 3MF Consortium MCP/lib3mf, OrcaSlicer MCP + its OrcaSlicer fork.

**Primary spec:** `docs/superpowers/specs/2026-09-13-blender-bridge-hub-v1-design.md`

**Original implementation plan:** `docs/superpowers/plans/2026-09-13-blender-bridge-hub-v1.md`

## 0. Source-of-truth checkpoint

Do not trust this document over actual Git state. At the start of every successor session, inspect `main`, `origin/main`, feature branch HEAD/upstream/status/worktree and continue from the actual repository state.

Checkpoint at handoff creation:

- Repository: `genrudko/development-bridge`
- Feature branch: `feature/blender-bridge-hub-v1`
- Base/main checkpoint: `c4cfba1232c47325e52cd3f9852aa60c7db8ac43`
- Feature HEAD before this handoff commit: `b914393c1a8dafb5079ee0cca2daba27ba6bf3b6` — `feat: add 3MF and Orca print adapters`
- Compared with `main`: ahead by 8 implementation/design commits, behind by 0 at that checkpoint.
- No merge/deploy was authorized or performed.

After this handoff file is committed, the branch HEAD will naturally be one documentation commit newer. Treat Git as authoritative.

## 1. Read these first, in order

1. `docs/superpowers/specs/2026-09-13-blender-bridge-hub-v1-design.md`
2. `docs/superpowers/plans/2026-09-13-blender-bridge-hub-v1.md`
3. This continuation file.
4. `app/blender_bridge/models.py`
5. `app/blender_bridge/service.py`
6. `app/blender_bridge/provider_transport.py`
7. `app/blender_bridge/operator.py`
8. `app/blender_bridge/operator_inbox.py`
9. `agents/blender_hub_runtime.py`
10. `agents/blender_hub_gui.pyw`
11. `app/blender_bridge/printing.py`
12. `app/blender_bridge/print_pipeline.py`
13. `app/blender_bridge/print_adapters.py`
14. Matching `tests/unit/test_blender_*` and `tests/contract/test_blender_tools.py`.

Do not start by redesigning the architecture. The feature already has substantial implementation and tests.

## 2. Global constraints that must survive

- Do not port the Fusion semantic facade wholesale into Blender.
- Reuse upstream Blender/3MF/Orca functionality before writing custom domain code.
- Provider versions/revisions are pinned; updates are explicit.
- Reads may overlap. Unknown mutation classification is conservative and all mutating provider calls share one global write lock.
- Transport loss during an ambiguous mutation becomes `uncertain`; never auto-replay it.
- `operator.ask` is same-turn interaction: the original pending model tool call must receive the operator answer.
- Windows initiates outbound connectivity to the VPS. Do not add an arbitrary inbound shell surface.
- Geometry 3MF and slicer-owned project 3MF are different artifacts and must stay distinguishable.
- Unknown printer/nozzle/filament calibration remains unknown. Never invent defaults to make the pipeline look complete.
- No implicit save/print/start-job side effect.
- Do not touch Fusion runtime behavior while implementing Blender work.
- Do not merge, deploy, or modify production/systemd without owner authorization.

## 3. Implemented progress and exact commits

The feature branch contains these Blender-specific commits in order:

1. `d4a8c1c89cffa251089269890c41dbf18b37a7f8` — `docs: define Blender Bridge Hub v1`
   - Added the design spec and original implementation plan.

2. `29b8e83f932e183e22ad43aa79f9f4185dfb0d4c` — `feat: add Blender Hub core`
   - Added provider/tool models, namespaced catalog, global mutation serialization and same-turn operator primitives.

3. `8f2c13efd9e6795ec429d75048fd32fdc08ea4d8` — `feat: add Blender provider transport contract`
   - Added managed provider transport behavior, health/catalog refresh, uncertainty/no-replay handling and focused tests.

4. `e2c2139e3b863df72ce3bef52c567e59bcf62e84` — `feat: expose Blender Hub control tools`
   - Added `app/tools/blender.py`, registry wiring, contract tests and Development Bridge control surface.

5. `010a7c89322b7773566627e664ab925b53e48e63` — `feat: add Windows Blender Hub runtime`
   - Added `agents/blender_hub_runtime.py`, launcher scripts and provider JSON.
   - Current initial provider config contains `dcc` at `http://127.0.0.1:9765/mcp`, pin `v0.2.4`.
   - Runtime reuses qualified outbound DesktopNode registration/claim/result-delivery patterns.

6. `61db346ef0e52e6fb3986674047ed2679a80f715` — `feat: add Blender Hub operator GUI`
   - Added GUI/inbox/journal components and associated tests.

7. `8b6179af2094157453d0e73de5a8505b07b62005` — `feat: add Blender print pipeline orchestration`
   - Added provider-neutral print orchestration and tests.
   - Before this commit, the focused print-pipeline regression set was observed green at **37/37**. Re-run it; do not treat old chat evidence as a substitute for a fresh gate.

8. `b914393c1a8dafb5079ee0cca2daba27ba6bf3b6` — `feat: add 3MF and Orca print adapters`
   - Added `app/blender_bridge/print_adapters.py` and `tests/unit/test_blender_print_adapters.py`.
   - This is the last implementation commit before this handoff.

At `b914393`, the branch differs from `main` by the Blender Hub/runtime/GUI/print files plus tests/spec/plan. There is no evidence yet of a fresh full-repository gate after the final adapters commit.

## 4. What the current implementation does

### 4.1 Hub/provider core

- Public tool names are namespaced as `<provider>.<tool>`.
- Provider tool metadata is discovered dynamically.
- Unknown mutability is treated conservatively.
- Mutations serialize globally across providers.
- Read-only calls can overlap.
- Provider reconnect/catalog refresh is modeled explicitly.
- Ambiguous mutation disconnects become terminal uncertainty rather than transparent replay.

### 4.2 Windows Hub runtime

- `agents/blender_hub_runtime.py` connects local MCP providers and exposes their tools through the existing DesktopNode command loop.
- Local provider URLs are restricted to loopback HTTP(S) in the current implementation.
- `operator.ask` is exposed as a Hub tool.
- Result outbox/retry logic is reused from the already-qualified DesktopNode/Fusion transport layer.
- Current provider transport is Streamable HTTP. **There is no generic local stdio MCP provider transport yet.**

### 4.3 Operator UX

- GUI/inbox/journal code exists.
- Same-turn question/answer behavior is part of the architecture and unit-level implementation.
- It has not yet been re-qualified in a real Blender + provider live run in this branch.

### 4.4 Print context

`app/blender_bridge/printing.py` defines provider-neutral context objects:

- `PrinterContext(preset, model)`
- `NozzleContext(diameter_mm, material)`
- `FilamentContext(preset, material, flow_ratio, pressure_advance, max_volumetric_speed_mm3_s, nozzle_temperature_c, bed_temperature_c)`
- `PrintContext(..., goal)`
- Goals: `balanced`, `dimensional_accuracy`, `strength`, `surface_quality`, `fastest_safe`.

Unknown calibration is represented as `None`, not guessed.

### 4.5 Print pipeline

`app/blender_bridge/print_pipeline.py` treats stages explicitly and fails closed. Geometry validation cannot be silently skipped and geometry/project artifacts are distinct.

The intended logical flow is:

`mesh preflight -> geometry 3MF -> 3MF compliance/preflight -> Orca import -> print context -> physics gate -> slice/compare -> explicit final project export`

### 4.6 3MF adapter

`ThreeMfMcpAdapter` currently uses the official 3MF Consortium MCP `check_compliance` contract with a local `path`.

It requires:

- parseable report,
- structured validation object,
- strict/non-strict validation flags,
- deterministic preflight findings,
- fail/blocked result if compliance or preflight is not acceptable.

It never converts a provider failure into a pass.

### 4.7 Orca adapter

`OrcaMcpAdapter` currently supports:

- model import through `load_model(path)`;
- printer and filament preset selection;
- nozzle-diameter readback and exact requested-diameter verification;
- calibrated overrides only for confirmed Orca keys:
  - `filament_flow_ratio`
  - `filament_max_volumetric_speed`
  - `nozzle_temperature`
- physics gate through `check_profile_physics`;
- slicing through `slice_and_wait`;
- variant comparison through `compare_slices`;
- explicit propagation of warnings/failures.

It intentionally does **not** auto-apply:

- `pressure_advance`: upstream knowledge explicitly notes common Klipper PA as firmware-side calibration rather than one universal Orca profile mapping;
- `bed_temperature_c`: a single value is insufficient to choose the correct Orca plate-surface key (`hot_plate`, textured plate, etc.);
- nozzle material: retained as evidence because current verified upstream contract exposes nozzle diameter, not a safe universal material rewrite.

`save_project()` currently raises `PrintCapabilityUnavailable`. This is deliberate and tested: the current Orca MCP exposes model/config/slice/G-code functionality but **does not expose project 3MF save/export**.

## 5. Upstream research decisions that must not be rediscovered from scratch

### Blender providers

- `dcc-mcp/dcc-mcp-blender` is the preferred rich Hands-like provider.
  - Source license: MIT.
  - Selected current pin for initial Hub work: `v0.2.4`.
  - 200+ typed tools, Streamable HTTP inside Blender, real Blender CI, mesh revision guards in parts of the API.

- `Haiyang-Bian/blender-research-mcp` is the closest architectural analogue to Fusion safety semantics and has strong scene/mesh revisions, transactions, rollback, SelectionSet/SurfaceRef/ComponentMap and viewport evidence.
  - **Do not copy/vendor code:** no license was found during research.
  - Use as architecture/reference only unless licensing changes.

- `newo-ether/blender-mcp` is MIT and a good safe-node-workflow donor (revision-safe declarative node patches, dry-run/rollback), not a complete Blender provider.

- `seehiong/blender-mcp-bridge` is MIT and useful as UX/session replay inspiration.

- `RFingAdam/mcp-blender` has broad capabilities but actual repository license is AGPL-3.0 despite a README claim of MIT. Treat as external/benchmark unless licensing is explicitly accepted.

- Official Blender Foundation MCP is useful as reference/escape hatch but its own page warns that it executes LLM-generated Blender code without guards. It is not the default safe autonomous provider.

### 3MF provider

- Repository: `3MFConsortium/3mf-mcp`.
- Package observed: `@3mfconsortium/mcp` `0.1.0-alpha.1`.
- License: BSD-2-Clause.
- Key tools include `load_model`, `check_compliance`, `inspect_model`, `validate_model`, object/build/material/package inspection.
- `check_compliance` accepts exactly one of model id, local path, or base64 input.
- Local paths are explicitly most natural with stdio transport.

### Orca provider

- Repository: `MaxEllis/orcaslicer-mcp`.
- Package observed: `orcaslicer-mcp` `0.1.12`.
- License: **AGPL-3.0-only**.
- Keep it outside Development Bridge as a separate provider process; do not import/vendor its Python code into our MIT/permissive core without a deliberate licensing decision.
- Confirmed MCP capabilities include status/config, `load_model`, preset selection/editing, `check_profile_physics`, object/placement tools, `slice_and_wait`, `compare_slices`, G-code retrieval/save and outcome/knowledge helpers.
- The associated OrcaSlicer fork contains an internal `Plater::export_3mf()` path, but the current remote API/MCP surface does **not** expose project-3MF export.

## 6. Critical capability gap: final slicer-owned project 3MF

The user explicitly wants the exported print project to carry the optimal slicer setup for the actual printer/nozzle/filament context. Do not redefine that requirement down to “G-code exists”.

Current state:

- Geometry 3MF: supported conceptually and validated through the 3MF provider.
- Orca load/config/physics/slice/compare: adapter implemented.
- Orca G-code: upstream supports it.
- Orca project 3MF with slicer settings: **not exposed by upstream MCP today**.

Therefore the correct next architecture is a bounded extension of the external Orca provider/fork, not a fake success in Development Bridge.

Requirements for that extension:

1. Inspect actual current `MaxEllis/OrcaSlicer` remote-api branch/fork and `orcaslicer-mcp` client/server before changing anything.
2. Reuse the existing internal `export_3mf()` path.
3. Add one minimal explicit remote capability to save/export the current Orca project to a caller-supplied local path.
4. Add the matching MCP tool in `orcaslicer-mcp`.
5. Make the operation explicit and non-implicit; no autosave.
6. Validate path/error behavior and prove the exported file exists and is non-empty.
7. Preserve AGPL separation: changes belong in the Orca fork/provider repositories, not copied into Development Bridge.
8. Only after that contract is real, replace `OrcaMcpAdapter.save_project()` unavailable behavior with the real call and tests.

Do not invent an endpoint name before reading the fork's existing remote API conventions.

## 7. Exact continuation plan

### Task A — Re-establish branch and run fresh focused gates

- [ ] Inspect actual branch/HEAD/status/upstream and compare with `main`.
- [ ] Confirm this handoff document is present and no newer implementation supersedes it.
- [ ] Run the focused Blender core/runtime/GUI/printing/pipeline/adapter tests.
- [ ] At minimum include `tests/unit/test_blender_print_pipeline.py` and `tests/unit/test_blender_print_adapters.py`.
- [ ] Run `git diff --check`.
- [ ] If anything is red, repair only proven failures with TDD before adding functionality.

### Task B — Add generic local stdio MCP provider transport

**Why:** current Hub provider config accepts loopback HTTP(S) only, while the official 3MF MCP's local-path workflow and Orca MCP are naturally launched as local stdio processes.

- [ ] Write failing tests for a provider config using `transport: "stdio"`, command, args and bounded environment.
- [ ] Keep current Streamable HTTP config backward compatible.
- [ ] Add a stdio MCP transport using the MCP Python client primitives rather than custom JSON-RPC framing.
- [ ] Prove tool discovery/call results normalize exactly like HTTP providers.
- [ ] Prove child-process disconnect during a mutating tool still yields `uncertain` and never auto-replays.
- [ ] Prove clean shutdown terminates only the provider process owned by the Hub.
- [ ] Commit this as one bounded transport slice.

Recommended config shape is conceptual only; match existing code style after inspection:

```json
{
  "namespace": "3mf",
  "transport": "stdio",
  "command": "...",
  "args": ["..."],
  "pin": "0.1.0-alpha.1"
}
```

Do not add arbitrary shell command execution. Provider executable/args come from the local trusted config, not from model tool arguments.

### Task C — Configure and pin real 3MF and Orca providers

- [ ] Install/resolve exact local executables without changing production service configuration.
- [ ] Add `3mf` provider with exact package/revision pin.
- [ ] Add `orca` provider with exact package/revision pin.
- [ ] Keep Orca as an external AGPL process.
- [ ] Start the Hub and prove catalog discovery for `dcc`, `3mf`, and `orca` independently; one provider failure must not take the others down.
- [ ] Record exact versions/pins in operations docs.

### Task D — Bind real providers to `PrintPipeline`

- [ ] Add a thin caller/runtime adapter that lets `ThreeMfMcpAdapter` and `OrcaMcpAdapter` invoke the Hub provider namespaces without bypassing the Hub mutation/uncertainty semantics.
- [ ] Write integration tests with fake provider transports before live providers.
- [ ] Prove 3MF compliance failure prevents Orca handoff.
- [ ] Prove physics `blocked` prevents slice/export.
- [ ] Prove warnings remain warnings and are retained in pipeline evidence.
- [ ] Prove the geometry artifact remains separate from later slicer artifacts.

### Task E — Expose Orca project-3MF export in the external Orca stack

This is a separate repository/fork slice and must have its own TDD/review evidence.

- [ ] Inspect current `MaxEllis/OrcaSlicer` remote API implementation and locate the already-confirmed internal `export_3mf()` path.
- [ ] Add failing remote-api tests for explicit current-project export to a local path.
- [ ] Implement the smallest remote endpoint following existing API conventions.
- [ ] Add failing `orcaslicer-mcp` tests for a `save_project`/equivalent MCP tool using that remote capability.
- [ ] Implement the MCP tool and client call.
- [ ] Prove export failure is visible and does not masquerade as success.
- [ ] Pin the exact fork/provider commits used by Blender Hub.
- [ ] Return to Development Bridge and replace `PrintCapabilityUnavailable` with the real provider call behind tests.

### Task F — Dual Blender provider live bake-off

- [ ] Bring `dcc` online against a real Blender session.
- [ ] Bring the research provider online only if it can be used legally as an unchanged external provider; otherwise leave it out rather than weakening the license boundary.
- [ ] Verify mutation from provider A is visible to provider B read/inspection if both are used.
- [ ] Verify global mutation serialization across providers.
- [ ] Perform one real same-turn `operator.ask` and continue with another Blender call in that same model turn.
- [ ] Record exact evidence/screenshots/artifacts without touching Fusion documents.

### Task G — Full offline regression gate

- [ ] Run all Blender Hub unit + contract + integration tests.
- [ ] Run closest existing DesktopNode/tool registry/startup regressions because Blender reuses those surfaces.
- [ ] Run print pipeline/adapters separately so their result is visible.
- [ ] Run `git diff --check`.
- [ ] Inspect final feature diff against `main` for accidental Fusion/runtime changes.
- [ ] Do not call the phase green without recording exact test counts/results.

### Task H — One deliberate end-to-end live print acceptance

Only after Task G is green:

- [ ] Use a disposable/simple Blender model, never a protected user production asset.
- [ ] Perform Blender mesh preflight.
- [ ] Export a geometry 3MF.
- [ ] Validate it through the 3MF provider/lib3mf.
- [ ] Load it in Orca.
- [ ] Apply the actual requested printer preset, filament preset and verified nozzle diameter.
- [ ] Apply only known calibration values; leave unknowns unknown.
- [ ] Run physics gate.
- [ ] Slice a baseline and at least one alternative process variant.
- [ ] Select/recommend according to the declared `PrintGoal` using measured warnings/time/material tradeoffs; do not pretend there is a universal winner.
- [ ] Explicitly export/save the slicer-owned project 3MF through the new Orca capability.
- [ ] Verify the project file exists, is non-empty, and can be inspected/validated as appropriate.
- [ ] Do **not** start a physical print unless the owner separately authorizes it.
- [ ] Record exact provider pins, context, slice metrics, warnings and artifact paths in operations acceptance docs.

### Task I — Final review and owner handoff

- [ ] Review the whole feature against the design spec and this continuation plan.
- [ ] Document deviations as explicit design corrections, not silent drift.
- [ ] Update `docs/operations/blender-bridge-hub.md` (create if still absent) with install/start/stop/provider pin/update/acceptance instructions.
- [ ] Produce a concise final branch summary with test evidence and remaining limitations.
- [ ] Stop before merge/deploy unless the owner explicitly authorizes it.

## 8. What is NOT complete at this checkpoint

Do not claim any of the following yet:

- Full Blender Hub v1 acceptance.
- Real multi-provider live Blender qualification.
- Fresh full-repository regression gate after `b914393`.
- Installed/qualified 3MF provider in the Windows Hub.
- Installed/qualified Orca provider in the Windows Hub.
- Generic stdio provider supervision.
- Final slicer-owned project 3MF export through Orca MCP.
- End-to-end Blender -> 3MF -> Orca project artifact live proof.
- Merge/deployment to `main`.

## 9. Known risks / traps

- **Stale original plan checkboxes:** the original plan still reads like a greenfield task list. Use the commit map and this checkpoint, not unchecked boxes, to determine progress.
- **Tool-count fallacy:** 200+ Blender tools do not replace mutation safety, evidence, continuity and uncertainty handling.
- **AGPL boundary:** Orca MCP is AGPL-3.0-only. Keep it as an external process/provider; do not paste its implementation into Development Bridge.
- **Research MCP license:** absence of a license means no code reuse/vendor assumption.
- **3MF meaning:** a geometry 3MF is not automatically an Orca project containing slicer configuration.
- **Nozzle mismatch:** current Orca adapter blocks if selected preset nozzle diameter differs from requested context.
- **Bed temperature:** do not guess a plate-surface key from one scalar temperature.
- **Pressure advance:** do not map firmware PA to an arbitrary Orca setting.
- **Provider errors:** MCP `isError`, structured `error`, malformed/incomplete validation payloads and transport failure must stay fail-closed.
- **No auto replay:** especially around load/config/export/mutation operations.
- **No premature live mutation:** offline tests first; disposable live asset second.

## 10. Success definition

Blender Bridge / Hub v1 is ready for owner review when all of the following are true:

1. Actual feature branch is clean and based on current main without unresolved drift.
2. Hub can supervise the selected Blender provider plus 3MF and Orca providers with exact pins.
3. Same-turn operator loop is proven live.
4. Mutation uncertainty/no-replay and global serialization are preserved.
5. Geometry 3MF is exported and validated before slicer handoff.
6. Actual printer/nozzle/filament context is applied without invented calibration.
7. Orca physics gate and measured variant comparison work.
8. Orca exports an explicit slicer-owned project 3MF through a real remote/MCP capability.
9. Offline regressions are green with recorded counts.
10. One disposable end-to-end live acceptance is recorded.
11. Operations documentation is sufficient for a new executor/operator to install, start, diagnose and update the stack.
12. Nothing is merged/deployed until the owner says so.
