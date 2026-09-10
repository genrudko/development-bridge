# Fusion CAD Agent post-P0 reuse landscape — 2026-09-10

**Status:** research decision after web, code-level, test-suite, live-Fusion, and MCP-protocol qualification. It supersedes the old greenfield implementation assumptions, but the canonical P0.5/P1/P2 phase files must still be rewritten before phase implementation starts.

**Purpose:** before implementing P0.5/P1/P2, determine how much of the planned work can be deleted, delegated to Autodesk, wrapped from stable Fusion APIs, harvested from permissively licensed OSS, or moved to existing geometry/slicer tooling. The goal is minimum custom code while preserving the P0 safety invariants.

## Executive conclusion

Do **not** implement the current P1/P2 plans literally. The 2026 Fusion ecosystem now covers a large fraction of the raw CAD operations that the original plans expected Development Bridge to write from scratch.

Keep the P0 `fusion.cad/v1` semantic/safety facade as the only normal public CAD contract. Keep the official Autodesk Fusion MCP because P0 read/view/control paths are already deployed and accepted, but do **not** make its generic Python script executor the sole P1 modeling substrate. Live qualification on Fusion `2704.1.53` exposed repeatable script-proxy failures around document creation and sketch constraints. The cheapest current architecture is therefore a dual-provider design: official Autodesk MCP for the proven P0 substrate, plus a pinned Shimmer sidecar MCP/add-in as the leading rich-modeling provider behind a second instance of the existing Windows Relay. Faust remains the primary implementation/reference donor when a Shimmer operation needs replacement or hardening.

Keep custom code concentrated in the parts that are actually distinctive: revision freshness, stable refs/selectors, transaction semantics, capability honesty, provider routing, operator control, evidence normalization, policy, and integration.

Working engineering estimate after this audit, not a measured schedule commitment:

- P0.5 custom implementation can likely shrink by roughly **65–80%** versus a greenfield operator-control subsystem because Bridge already owns durable jobs, operation journals, cancellation, coordinator ACK/wake, and authenticated SSE.
- P1 custom implementation can likely shrink by roughly **50–70%** versus the existing plan by harvesting Fusion operations and wrapping stable native APIs.
- P2 custom implementation can likely shrink by roughly **60–80%** by moving assembly/view work earlier, using mesh/slicer libraries for printability, and adopting a declarative IR/recipe layer rather than a new geometry engine.

These percentages are directional estimates and must be replaced by task-level estimates after a donor spike.

## Non-negotiable architecture after research

1. **`fusion.cad/v1` remains the public safety/domain facade.** No provider replaces P0 revision guards, transaction safety, capability truth, stable refs, `VIEW_STALE`, uncertain-mutation handling, or no-save policy.
2. **Official Autodesk Fusion MCP remains the P0 provider, not necessarily the only provider.** Its deployed read/view/control path stays intact. Its generic script executor is diagnostic/compatibility infrastructure and is not promoted to the default P1 mutation engine after the live failures recorded below.
3. **Shimmer is the leading P1 runtime-provider candidate.** Prefer pinning its MIT sidecar/add-in and connecting it through a second instance of the existing Windows Relay over copying its whole transport stack into Development Bridge. Adoption remains gated on one live sidecar spike against the installed Fusion version.
4. **Faust is the primary implementation/reference donor.** Harvest or adapt individual permissively licensed operations/tests when they are better than Shimmer's implementation or when the pinned sidecar needs a replacement operation.
5. **Do not ship Autodesk Preview APIs as mandatory core behavior.** Capability-gate them and use stable alternatives where available.
6. **Do not build a slicer, B-Rep kernel, nesting optimizer, new outbound Relay, second job queue, or second durable orchestration system.** Existing products/libraries already solve those layers better.

## P0.5 working scope used for this research

P0.5 is not currently represented by a canonical phase file in this repository. The working scope recovered from the project discussion is human-in-the-loop/operator control rather than new CAD modeling capability:

- dockable Fusion Palette;
- durable operator inbox/state;
- atomic CAD actions with a check between actions;
- Pause / Resume;
- Stop after current action;
- Abort pending plan;
- natural-language correction/acknowledgement between actions;
- reconnect durability and max-once action semantics;
- preserve all P0 safety invariants.

This working definition should be canonicalized only after the reuse decision is accepted.

## Existing Development Bridge reuse for P0.5

Development Bridge already contains most of the hard backend primitives:

- `JobService` durable queued/running lifecycle, cancellation, timeout and restart recovery;
- desktop-node durable operation journal and `uncertain_operations`;
- coordinator durable wake/ACK/batched-message lifecycle;
- authenticated operator dashboard SSE (`/ops/api/events`) and snapshot flow;
- route generations and cancellation semantics.

Therefore P0.5 should **not** introduce Temporal, Celery, a new scheduler, another WebSocket control plane, or another durable job database.

The remaining custom P0.5 work should be a thin operator-plan/inbox state machine, action-boundary protocol, correction/ack messages, and Fusion Palette presentation.

### Official Palette API is sufficient

Fusion's Palette API already provides docked/floating HTML UI, JavaScript↔add-in events, and add-in→HTML messages. September 2026 added `Palette.isDockedInCanvas`; setting it false lets an API palette occupy the window edge while Fusion resizes the canvas, matching Autodesk Assistant behavior.

Recommended P0.5 UI: small HTML/CSS/JS Palette using official API directly. Borrow UX/reconnect patterns from existing Fusion copilots, but do not import their backend/auth/orchestration stacks.

## Official Autodesk stack

### Autodesk Fusion MCP — RETAIN as the proven P0 provider

Current status: **General Availability**. It runs locally with Fusion and exposes dynamic tools for live modeling/command execution.

Decision: retain it for the already accepted P0 semantic/read/view/control path and as an escape hatch. Do not discard or rewrite that integration. However, current live qualification shows that the generic `fusion_mcp_execute` script path is not robust enough to be the sole rich-modeling provider for P1; provider routing is now required.

Sources:
- https://help.autodesk.com/view/ADSKMCP/ENU/
- https://help.autodesk.com/view/fusion360/ENU/?guid=FMCP-OVERVIEW
- https://www.autodesk.com/products/fusion-360/blog/introducing-the-fusion-mcp-opening-fusion-to-ai-powered-workflows/

### Fusion Data MCP — OPTIONAL future data-management provider

Current status: **General Availability**. It handles Fusion cloud data such as hubs/projects/folders/items and collaboration/admin workflows without requiring the desktop session.

Decision: not needed for P1 modeling, but use it later instead of writing our own Fusion-project data management layer if that scope appears.

Sources:
- https://help.autodesk.com/view/fusion360/ENU/?guid=FMCP-OVERVIEW
- https://www.autodesk.com/products/fusion-360/blog/introducing-the-autodesk-fusion-data-mcp-server/

### Fusion Automation API — OPTIONAL cloud/headless provider

Current status: GA. It runs Fusion automation in the cloud and exposes advanced manufacturing algorithms including TrueShape packing. Pricing is 3.0 Fusion Flex tokens per processing hour. Autodesk has also announced a limited Fusion Automation MCP beta; access is not guaranteed.

Decision: introduce only as an optional provider for headless/batch work and high-quality packing/nesting. Do not make interactive desktop P1 depend on it.

Sources:
- https://aps.autodesk.com/blog/design-automation-api-fusion-now-generally-available
- https://feedback.autodesk.com/key/FusionAutomationMCP

### Autodesk Assistant — BENCHMARK / user-product alternative

Autodesk Assistant moved out of Tech Preview into the generally available Fusion experience in the September 2026 release. It is worth testing for repetitive user-facing workflows before duplicating those workflows in our own UI.

Community evidence is mixed: users report genuine wins for repetitive bulk operations, but there are also reports of destructive or poorly recoverable changes. This reinforces rather than removes the need for our P0 safety facade for autonomous work.

Sources:
- https://www.autodesk.com/products/fusion-360/blog/september-2026-major-product-update-whats-new/
- https://www.reddit.com/r/Fusion360/comments/1sumoqf/first_time_i_found_autodesk_assistant_useful/
- https://www.reddit.com/r/Fusion360/comments/1tozubh/autodesk_assistant_deleted_all_sketches_in/

## Stable Fusion APIs that make planned work cheap

The following areas should be wrappers around Autodesk APIs, not new algorithms:

- **3MF/STL/STEP export:** `ExportManager` already exposes stable export options; `createC3MFExportOptions` exists since September 2021.
- **Named views:** stable `NamedViews` collection supports creation/access since September 2023; `NamedView.apply` changes the viewport.
- **Section analyses:** `SectionAnalyses` supports creating/accessing sections and is available since January 2023.
- **Interference:** native design/working-model interference APIs exist; do not implement collision volume ourselves.
- **Minimum distance/clearance:** native measurement APIs exist; our work is normalization, selectors and policy.
- **Joints/rigid groups/grounding:** long-standing Fusion APIs exist; this should not remain a large P2 subsystem.
- **Occurrences/transforms:** use current `transform2`, not retired `transform`.

Preview exceptions:

- `Features.arrangeFeatures` remains **Preview**. Autodesk explicitly says distributed programs should not rely on Preview capabilities. Do not make it the P1 packing foundation.
- September 2026 Drawing DXF export API is **Preview** and carries the same warning. Keep DXF capability-gated. Existing stable sketch/flat-pattern DXF paths may still cover narrower use cases and must be qualified separately.

Sources:
- https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_ExportManager_createC3MFExportOptions.htm
- https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_NamedViews.htm
- https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/SectionAnalyses.htm
- https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_Occurrence.htm
- https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Features_arrangeFeatures.htm
- https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/drawing_DXFExportOptions.htm

## OSS Fusion donor qualification

This audit cloned candidates on 2026-09-10 and inspected current code, licenses, file/test structure, and key Fusion API implementations. The strongest candidates were also run through their own offline suites where practical.

| Candidate | License / practical evidence | Best use | Decision |
|---|---|---|---|
| `faust-machines/fusion360-mcp-server` | MIT; current clone updated 2026-09-10; 9 test files; **351/351 PASS** locally | broad sketch/feature/assembly/inspection/export/appearance operations; MCP annotations; mutation snapshots; Undo safety | **Primary implementation/reference donor; fallback operation source** |
| `jhk-a1/cad-copilot` | MIT; 21 test files; **447/447 PASS** with declared optional test deps | typed Command IR, Safe Executor, one-command/one-undo patterns, rollback, proof-of-fitness, DFM, persistent feature identity | **Primary IR/validation/P2 donor** |
| `shimmerjordan/self-host-fusion360-MCP` | MIT; 80 Python files; 6 test files; **28/28 PASS**; production Relay-client protocol spike exposed **103 safe-default tools** and completed `call_tool` successfully | mm-first rich Fusion operations; constraints/dimensions, sweep/loft, assemblies, interference, appearances, export, CAM; token-authenticated local HTTP add-in bridge; main-thread CustomEvent dispatch | **Primary P1 runtime-provider candidate, pinned sidecar; live current-Fusion add-in gate still required** |
| `er-fo/CADAgent` | MIT; 353 Python files; 30 test files; active 2026 product | Fusion Palette UX, Windows/Mac add-in patterns, feature snapshot/edit/rollback, identity checks, camera/thread utilities | **P0.5 UI + practical P1 donor** |
| `ncmlabs/fusion360_mcp` | MIT; 59 Python files; rich typed sketch/feature/assembly code; current suite fails collection on MCP SDK 2.x because it imports old `FastMCP` | sketch constraints/dimensions, typed models, validation code | **Harvest individual operations only; no dependency** |
| `Bhooorya/text-to-cad` | MIT; 28 typed CAD endpoints; validated JSON feature plan; mock backend; sparse tests | declarative feature-plan/registry ideas | **Architecture donor only** |
| `ignaciomolini/mcp-fusion360` | MIT; small; no test files in audit | parameter snapshot/rollback and JSON-RPC patterns | **Reference snippets only** |
| `prim-design/fusion-mcp` | MIT; only 3 Python files; no tests in audit | examples of broad tool exposure | **Reference only** |
| `zkbkb/fusion-mcp` | CC BY-NC 4.0; 13 test files; broad feature set | technical comparison | **Do not copy into project** due noncommercial restriction |
| `JustusBraitinger/Autodesk-Fusion-360-MCP-Server` | MIT; no tests in audit | examples | **Low-priority reference** |
| `dterracino/f360mcp` | MIT; 2 Python files; no tests | generic Fusion API patterns | **Low-priority reference** |
| `fozzfut/FusionMCP` | no license found in audit | examples only | **Do not copy** |
| `imranduratbegovic/fusion-mcp` | no license found in audit | examples only | **Do not copy** |

Important qualification rule: donor README claims are not accepted as API truth. Example: one active donor states that Fusion has no 3MF API, while current Autodesk documentation exposes stable `createC3MFExportOptions`. Every harvested adapter must be reconciled against the installed Fusion runtime and official current API docs.

Primary donor URLs:
- https://github.com/faust-machines/fusion360-mcp-server
- https://github.com/jhk-a1/cad-copilot
- https://github.com/shimmerjordan/self-host-fusion360-MCP
- https://github.com/er-fo/CADAgent
- https://github.com/ncmlabs/fusion360_mcp
- https://github.com/Bhooorya/text-to-cad

## Live qualification findings — 2026-09-10

The code audit was followed by bounded live and protocol qualification. These findings materially change the provider decision.

### Shimmer-style core modeling works on live Fusion

On a blank disposable document, a Shimmer-style sequence created a named sketch, driving diameter dimension, extrusion and fillet. The subsequent `fusion.cad/v1` snapshot reported a healthy parametric timeline, one 30×30×10 mm body, a 1 mm fillet, one sketch and the expected model revision advance. This is positive evidence for the operation implementations themselves.

### Autodesk generic script execution is not a safe P1 foundation

On Fusion `2704.1.53`, a minimal script consisting only of a sketch, two lines, `addHorizontal`, and `addPerpendicular` repeatedly failed inside Autodesk's script wrapper with recursive `__getattr__` calls and `RecursionError: Stack overflow` (roughly 364 repeated frames). Subsequent script calls can remain unhealthy until document context is reset or the disposable document is closed.

A control script that creates a sketch and lines without geometric constraints can itself succeed, yet subsequent semantic script-backed reads on the large Task14 document can still fail. `documents.add()` also showed a repeatable post-create failure mode: the document can be created successfully while the generic script executor becomes unhealthy for the next script call. Native document/read MCP operations remain available.

These failures are upstream/provider behavior, not evidence that Shimmer or Faust CAD algorithms are wrong. They are evidence that Development Bridge should not route all future P1 mutations through raw Autodesk `fusion_mcp_execute`.

### Existing Windows Relay can talk to Shimmer without code changes

Shimmer was started in safe-default mock **streamable HTTP MCP** mode and connected using the exact `mcp.ClientSession` / `streamable_http_client` stack imported by `agents/windows_fusion_agent.py`. The production client:

- initialized successfully;
- discovered **103 tools**;
- found `fusion_sketch_constrain`, `fusion_sketch_dimension`, `fusion_extrude`, `fusion_joint`, `fusion_rigid_group`, `fusion_interference`, and `fusion_export_step`;
- did **not** expose `fusion_run_script` with arbitrary-code support disabled;
- successfully called `fusion_document_info`.

`windows_fusion_agent.py` already accepts independent `--node-id` and `--fusion-url` values. Therefore a second Relay process can target a pinned Shimmer HTTP MCP endpoint under a distinct node ID while the current `fusion-workstation` continues to target Autodesk MCP. This avoids a Relay rewrite.

### Trimesh is sufficient as the first P2 geometry engine

Trimesh `5.1.0` was exercised locally with its current proximity API. On a watertight 30×20×4 mm control box, ray-based thickness returned exactly 4.0 mm at the test points and closest-surface distance from the center returned 2.0 mm. This is enough to reject a custom thickness/proximity engine; real-part accuracy/performance remains a later bounded P2 qualification task.

### Test-stand note

The historical P0 Task14 acceptance used an unsaved state of `Schedule Task14 Golden 224313` with authoritative fingerprint `248783b462f770f57d12ccbea18080e410ef03b7acd946d81dfb57362f90e0d5`. During this post-P0 research, a recovery step closed that disposable document without saving while it was dirty, intentionally discarding its then-current unsaved state but inadvertently making the historical golden fingerprint no longer present in the reopened cloud-saved file. The reopened saved F41 copy is healthy but has fingerprint `bda887acc9636b14d1a472ff572cb0f7d0c13c2aca8566ab24ae08c546574fa5`; the secondary Task14-folder copy has fingerprint `a033306c12f19df5f9d60343ca01bf3d96fcea62e9c172a2e904f0a9bffac8a6`.

This does **not** invalidate the retained historical acceptance evidence and did not mutate or save the protected original `Schedule`. It means only that the current F41 cloud file must no longer be treated as a reproducible copy of the historical `248783…` golden state.

## User-facing Fusion copilots worth benchmarking when they can delete scope

### Adam AI CAD Copilot — TRIAL FIRST

Available free from the Autodesk App Store as a docked Fusion Palette. It advertises prompt-driven native editing, selected-geometry context, feature creation, sketch constraints, variables, feature-tree cleanup and parameterization while keeping results editable.

Decision: strongest ready-made user-facing candidate to test. If it already handles common interactive tasks well, do not reproduce those workflows in P0.5/P1 UI; build only the autonomous/remote/deterministic capabilities Adam does not provide.

Sources:
- https://marketplace.autodesk.com/apps/ada81435-7335-4dcc-913f-30936f9ae0a1
- https://adam.new/copilot

### CADAgent — TRIAL + CODE DONOR

Open-source Fusion add-in with conversational model creation/editing and a real Palette/backend product. Self-hostable.

Decision: trial it as a product and harvest its Fusion UI/operation patterns, but do not adopt its backend/auth/WebSocket architecture because Development Bridge already owns those responsibilities.

Sources:
- https://cadagent.co/
- https://github.com/er-fo/CADAgent

### Bevell — TRIAL ONLY

Commercial Fusion copilot advertising 79 CAD tools, natural-language multi-step operations, image-to-DXF, enclosure/DFM helpers, and $19/$39 monthly tiers. The same current site contains both “Available now” and waitlist/call-to-action language, so maturity/availability should be verified by an actual trial rather than assumed.

Source:
- https://bevell.app/

### Autodesk Assistant — TRIAL / baseline comparison

Already built into Fusion and now GA. Use it as the zero-install benchmark for repetitive operations, but do not treat it as a safe autonomous executor without our external safeguards.

## Structural diff: reuse generic machinery, keep CAD semantics

`DeepDiff` is a mature Python object-diff/hash/delta library (current repository describes v9.1.0). It can likely eliminate generic recursive comparison plumbing.

Decision: spike it behind normalized Fusion snapshots. Keep our public `StructuralDiff` schema and CAD-specific interpretation (created/deleted/changed features, refs, geometry metrics, health) custom. Do not expose raw DeepDiff paths as the public contract.

Source:
- https://github.com/qlustered/deepdiff

License must be confirmed from the exact selected release before vendoring or pinning; this audit did not base the recommendation on a license claim.

## P2 printability: do not build a mini slicer

### Trimesh — preferred permissive geometry-analysis dependency

Trimesh already supplies proximity/signed-distance/thickness primitives suitable for mesh-based minimum-wall and clearance evidence.

Decision: likely core P2 analysis dependency after a bounded accuracy/performance spike. Use it for evidence generation, while our code owns printer profiles, thresholds, confidence/method labels and result normalization.

Source:
- https://trimesh.org/trimesh.proximity.html

### OrcaSlicer CLI — optional external provider, not copied code

OrcaSlicer supports headless CLI operation and model transforms/arrangement. It is AGPL-3.0.

Decision: do not copy/link Orca code into Development Bridge without a deliberate licensing decision. Consider calling a separately installed Orca executable as an optional provider for orientation/arrangement/slicing validation. Treat its output as evidence, and independently verify bed-fit/constraints rather than trusting auto-orient blindly.

Sources:
- https://www.orcaslicer.com/wiki/cli/cli_mode
- https://www.orcaslicer.com/wiki/cli/cli_transform
- https://github.com/OrcaSlicer/OrcaSlicer

### lib3mf — use only for 3MF post-processing/validation

Official 3MF Consortium library, BSD licensed, with reading/writing/validation bindings.

Decision: no need for it just to export 3MF because Fusion already exports 3MF. Use it only if later workflows need to inspect/modify/validate 3MF packages outside Fusion.

Source:
- https://github.com/3MFConsortium/lib3mf

### build123d / CadQuery — offline oracle, not primary editor

Both are Apache-2.0 OpenCascade-based parametric CAD libraries. `build123d` is active and has a modern Python modeling API.

Decision: choose at most one as an optional offline geometry oracle/test-fixture generator for recipes and validation. Do not migrate the project away from Fusion or maintain duplicate authoring models unless a later decision changes the product goal.

Sources:
- https://github.com/gumyr/build123d
- https://github.com/CadQuery/cadquery

## Recommended rewrite of the phase boundaries

### P0.5 — thin operator shell, not another agent platform

Keep P0.5, but make it very small:

- official Fusion Palette UI;
- reuse Bridge jobs/journal/SSE/coordinator state;
- add only durable operator-plan/inbox state, Pause/Resume, Stop-after-current, Abort-pending, correction/ack, and max-once atomic-action semantics;
- borrow Palette/reconnect patterns from `er-fo/CADAgent`;
- no new CAD modeling capability and no second backend/transport stack.

### P1 — provider adoption and facade-wrapping phase

Refactor P1 from “write CAD features” to “qualify a rich provider, then wrap only what the public facade needs”:

- first gate: run the pinned Shimmer add-in/server live on the installed Fusion `2704.1.53` and prove representative sketch/constraint, feature, assembly and export operations through its own main-thread bridge;
- if green, run a **second instance of the existing Windows Relay** with a distinct node ID and Shimmer's local streamable-HTTP MCP URL; keep `fusion-workstation` on official Autodesk MCP for P0;
- add a small server-side provider mapping so callers still address the logical workstation while P1 mutations can route to the rich provider and P0 verification remains on the accepted provider;
- expose selected Shimmer operations only through our `fusion.cad/v1` safety/revision/transaction facade, not as the normal executor API;
- use `faust` as the primary donor/reference for stronger individual operations/tests or as fallback if a Shimmer operation is unsuitable;
- use `ncmlabs` for selected sketch/constraint implementation ideas and `er-fo/CADAgent` for practical feature-edit/Palette patterns;
- use official stable Fusion APIs for interference, clearance, named views, sections, joints, rigid groups, grounding and STL/STEP/3MF behavior, regardless of which donor supplied the adapter code;
- evaluate `DeepDiff` only as internal comparison machinery;
- simple deterministic move/align/distribute/grid/lay-flat can remain local;
- serious packing/nesting should be a provider interface, with Fusion Automation TrueShape as an optional high-quality cloud provider rather than a custom optimizer.

Do not make raw Autodesk `fusion_mcp_execute` the default P1 mutation backend unless Autodesk fixes the live script-proxy failures and a new acceptance gate proves the fix. Joints/rigid groups/grounding and named/section views should no longer be treated as major P2 inventions; they belong in P1.

### P2 — evidence/DFM/recipes phase

Shrink P2 to genuinely higher-level value:

- printer profile + evidence normalization;
- mesh-based wall/clearance/overhang/island heuristics using Trimesh rather than a new geometry kernel;
- optional Orca/headless or Fusion Automation providers for slicer-grade orientation/arrangement evidence;
- capability-gated DXF while Autodesk's relevant new API remains Preview;
- versioned declarative recipes using ideas from `jhk-a1/cad-copilot` Command IR/proof layer and `text-to-cad` feature-plan registry;
- optional build123d offline oracle for deterministic recipe fixtures;
- final live acceptance.

## Product bake-off is useful but no longer a P1 blocker

Autodesk Assistant, Adam AI CAD Copilot, CADAgent and Bevell remain useful benchmarks for operator UX and repetitive interactive workflows. Trial them when a specific P0.5/P1 user-facing feature could plausibly be deleted from our roadmap. They are **not** a blocking prerequisite for provider work because none currently replaces Development Bridge's remote execution, durable orchestration, revision/transaction safety and evidence contract as a single system.

## Adoption order

The remaining pre-implementation work is now narrow and ordered:

1. live-install a **pinned Shimmer sidecar** on the current Fusion runtime and prove representative operations through its own add-in bridge;
2. if green, prove a second unchanged Windows Relay instance can register that provider under a distinct node ID and coexist with `fusion-workstation`;
3. spike only the facade/provider-routing seam plus representative transaction/revision verification — do not build the full P1 tool set;
4. spike `jhk` Command IR/proof concepts against our transaction planner;
5. spike Fusion Palette using only existing Bridge durable state;
6. run Trimesh on representative exported real parts for accuracy/performance, not API existence;
7. rewrite the canonical P0.5/P1/P2 phase files with measured reuse and delete superseded greenfield tasks.

No P0.5/P1/P2 phase implementation should start before steps 1–7 complete or are explicitly waived.

## Things explicitly rejected

- replacing the proven official Autodesk P0 provider wholesale;
- using raw Autodesk `fusion_mcp_execute` as the only rich-modeling P1 backend despite the live proxy failures;
- rewriting Windows Relay merely to add the Shimmer provider; a second existing Relay instance is the preferred first approach;
- adding a second durable job/orchestration system for P0.5;
- treating raw Python/generic API execution as the primary public CAD contract;
- copying noncommercial or unlicensed repositories;
- shipping Autodesk Preview Arrange/DXF as mandatory functionality;
- writing our own B-Rep kernel, slicer, sophisticated nesting solver or 3MF exporter;
- implementing every old P1/P2 task merely because it exists in the 2026-09-04 plan.

## Research limitations

This is a broad landscape audit, not a mathematical proof that every private/commercial Fusion add-in on the internet was found. The audit intentionally prioritizes official Autodesk capabilities, discoverable current OSS, major user-facing Fusion copilots, and mature adjacent geometry/slicer libraries. Product marketing claims were not treated as implementation evidence; OSS candidates were code-inspected, license-qualified, and where practical test-executed.

The next revision should incorporate results of actual product trials and live donor spikes. Those results may reduce the roadmap further.
