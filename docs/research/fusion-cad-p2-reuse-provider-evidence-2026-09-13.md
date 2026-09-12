# Fusion CAD Agent P2 — Fresh Reuse / Provider Evidence

**Date:** 2026-09-13
**Status:** research evidence; Option A owner-approved 2026-09-13; canonical design: `docs/superpowers/specs/2026-09-13-fusion-cad-agent-api-v1-p2-reuse-design.md`
**Branch:** `research/fusion-cad-p2-reuse-design`
**Baseline:** `c4cfba1232c47325e52cd3f9852aa60c7db8ac43`

## 1. Boundary

This document refreshes the evidence behind P2 design. It does **not** authorize P2 implementation and does not reopen accepted P0/P0.5/P1 infrastructure.

Inherited invariants remain normative: revision freshness / external-change guard, opaque `ent_*`, authoritative Reference readback, capability honesty, `VIEW_STALE`, uncertain/no-replay mutation semantics, preview isolation, provider-session qualification/invalidation, and no implicit save/close.

The frozen 2026-09-04 P2 plan/spec is used only as requirements inventory.

## 2. Fresh reuse/provider matrix

At research start `main == origin/main == c4cfba1232c47325e52cd3f9852aa60c7db8ac43`. Canonical `main` had four known pre-existing untracked artifacts and was not modified. Research uses the isolated `research/fusion-cad-p2-reuse-design` worktree. Accepted Shimmer upstream/pin remains `97a06e76c289420a721590ddcab334f5f3dc3178`.

| Candidate | Current HEAD / version | Fresh evidence | License | Disposition |
| --- | --- | --- | --- | --- |
| `jhk-a1/cad-copilot` | `d18c69240fb27ccc6a9867a3c357fb37db954b85` | last commit 2026-06-27; current checkout `447/447` tests green with declared Anthropic extra | MIT | **design donor**, not runtime dependency: Command IR, allowlisting, expected-geometry/proof, DFM certificate, identity/rollback patterns |
| Trimesh | `fcf660feb0a14c68fd3945789e8ed77e260f9167`; 5.1.0 | representative throwaway accuracy/performance spikes completed | MIT | **mesh-evidence engine candidate** |
| OrcaSlicer | `c21e48450c44fbf9b08d4ed2647d7921899f47dd` | official CLI supports headless settings/filament loading, transform/arrange/orient, slice, project-3MF export, and effective-settings export | AGPL-3.0 | **separate-process optional provider only** for slicer evidence + Print Preparation; no copied/linked code without separate licensing decision |
| `faust-machines/fusion360-mcp-server` | `8bb5cb0400c551ac9fe74a02e6be09782064f5a8` | last commit 2026-09-10; current env `348 passed, 3 failed` from MCP SDK field-name compatibility | MIT | active Fusion operation donor/reference, not wholesale runtime replacement |
| `er-fo/CADAgent` | `42e5348eea5ea0d4c8383608bfa7974e6bff1abc` | last commit 2026-08-02; 30 test files; self-host backend is supported path | MIT | UI/whole-product reference; do not duplicate backend architecture |
| `Bhooorya/text-to-cad` | `e21bec0bebb89cf22120b84424581ca89154378e` | 2026-08-15 initial commit; current checkout `6/6` tests green | MIT | small JSON-plan donor only |
| CadQuery | `a6bedc0d7ceac1829290037259465e918fc00e80`; 2.8.0 | successfully used as deterministic ground-truth generator in spikes | Apache-2.0 | choose as the **single optional offline oracle / fixture generator**; never primary CAD runtime |
| build123d | `5b1b4b5da481a7b0140cb71d32b7fa93fe8032ce` | active | Apache-2.0 | **delete from runtime scope**; redundant once CadQuery is selected as test oracle |
| lib3mf | `bfb5df00057fae7e306c511fa7c6ff476dfaad28` | active Consortium implementation with read/write/validation | BSD-2-Clause | **defer** until external 3MF validation/manipulation is a proven need |

## 3. Autodesk/runtime truth that removes P2 code

- Autodesk Assistant became generally available in Fusion in the September 2026 update. This is evidence against building another generic in-product CAD copilot/UI.
- Stable native API capabilities and accepted Shimmer remain the first choice for CAD-native operations.
- `Features.arrangeFeatures` remains **Preview**; Autodesk explicitly warns against distributing programs that rely on Preview API. It is not a production packing foundation.
- Drawing `DXFExportOptions`, introduced September 2026, is also **Preview** with the same warning. Drawing DXF remains deferred/capability-gated.
- Fusion Automation is GA and exposes Autodesk's TrueShape packer. Serious packing/nesting should prefer this mature provider (or Orca arrangement for print workflows) before any custom solver.

Primary sources:

- <https://www.autodesk.com/products/fusion-360/blog/september-2026-major-product-update-whats-new/>
- <https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Features_arrangeFeatures.htm>
- <https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/drawing_DXFExportOptions.htm>
- <https://aps.autodesk.com/blog/design-automation-api-fusion-now-generally-available>
- <https://www.orcaslicer.com/wiki/cli/cli_mode>
- <https://github.com/OrcaSlicer/OrcaSlicer>
- <https://pypi.org/project/trimesh/5.1.0/>
- <https://github.com/3MFConsortium/lib3mf>

Fresh 2026-09-13 Orca CLI re-check confirms `--load-settings`, `--load-filaments`, `--export-3mf`, `--export-settings`, and normal setting overrides. Historical Orca issue #14718 (now closed upstream) showed that preset inheritance could silently fall back to hardcoded defaults in older releases; therefore Print Preparation must qualify the exact installed provider/profile bundle and verify exported effective settings rather than trusting a preset name or leaf JSON alone.

## 4. Throwaway Trimesh + CadQuery qualification

CadQuery 2.8.0 generated deterministic ground-truth parts; Trimesh 5.1.0 consumed exported meshes. No spike code is productionized.

Fixtures covered an enclosure, bracket, panel, bridge coupon, 0.2/0.5/1.0 mm clearance pairs, and a curved 1.5 mm shell.

On planar fixtures selected thickness and clearance checks matched parametric truth to floating-point precision. This **does not** prove global-minimum-wall correctness on arbitrary geometry; it proves controlled-fixture accuracy and provider mechanics.

### Curved-shell tessellation sensitivity

| Tessellation tolerance | Faces | Mean measured | p95 abs error | Time |
| ---: | ---: | ---: | ---: | ---: |
| 0.5 mm | 208 | 1.489063 mm | 0.010937 mm | 14.9 ms |
| 0.1 mm | 504 | 1.498135 mm | 0.001865 mm | 46.3 ms |
| 0.02 mm | 1264 | 1.499703 mm | 0.000297 mm | 102.6 ms |

Mesh-derived values therefore must carry tessellation provenance and an uncertainty/quality statement.

### Performance scaling

For 64 closest-point queries on subdivided panel meshes:

| Faces | Time |
| ---: | ---: |
| 10,784 | 229 ms |
| 43,136 | 741 ms |
| 172,544 | 2.85 s |
| 690,176 | 11.62 s |

Analysis budget, sampling budget, mesh quality, retained artifacts and async policy must be explicit.

### Proven semantic limit

Static mesh connectivity cannot establish slicer layer-order “unsupported islands”. A connected bridge coupon can contain an elevated bridge underside while still being one mesh component. Mesh-only P2 may report unsupported/overhang/bridge **risk candidates**; true layer/island conclusions belong to a slicer provider such as Orca and remain `provider_reported`.

## 5. Historical P2 requirement disposition

| Historical requirement | Disposition | New boundary |
| --- | --- | --- |
| Printer/process profile | **tiny glue** | normalized versioned profile + hash |
| Bed fit | **reuse + tiny glue** | authoritative Fusion bbox/frame for current orientation; mesh evidence for candidates |
| Minimum wall | **reuse Trimesh heuristic** | bounded sampling / mesh quality; never global guarantee without stronger proof |
| Minimum feature | **Trimesh heuristic / defer exact claim** | only explicitly defined measurable checks; otherwise `not_assessed` |
| Overhang | **reuse Trimesh heuristic** | face-normal/area geometry relative to explicit build direction |
| Bridge candidates | **Trimesh heuristic + optional Orca** | geometry candidate locally; slicer behavior externally |
| Unsupported islands | **optional Orca / delete mesh-only claim** | layer-order semantics are slicer territory |
| Print clearance | **reuse Fusion + Trimesh** | distinguish CAD geometric clearance from process-specific printable clearance |
| Orientation scoring | **tiny glue + Trimesh; optional Orca** | decomposed component scores, never opaque magic score |
| Joints / rigid groups / grounding | **reuse/wrap native Fusion/Shimmer if a real workflow gap exists** | **delete from P2 intelligence scope** |
| Named views / sections | **reuse native Fusion/Shimmer** | **delete from P2 intelligence scope** |
| Drawing DXF | **defer / capability-gated** | official drawing API remains Preview |
| Versioned recipes | **tiny declarative glue + JHK donor patterns** | no raw Python, no second executor; execution semantics must reflect actual P1 capability |
| Recipe provenance | **reuse P0/P1 provenance + tiny recipe metadata** | recipe id/version/plan hash are additional provenance |
| Recipe rollback | **reuse existing transactions only where genuinely supported** | never promise atomicity across Hands actions the transaction engine cannot stage |
| Packing / nesting | **optional mature provider** | Fusion Automation TrueShape or Orca; delete custom solver |
| STL/3MF/STEP export | **reuse P1/native** | not P2 |
| External 3MF validation | **defer lib3mf** | add only on proven external-validation gap |
| Offline geometry oracle | **optional CadQuery, test-only** | one oracle only; not runtime CAD |
| Old Schedule P2 golden | **delete/replace** | representative real-part corpus + fresh disposable unsaved live Fusion gate; protected Schedule designs remain untouched |
| Print-ready 3MF carrying printer/nozzle/filament/process configuration | **optional Orca provider + tiny glue** | preserve neutral Fusion `model.3mf`; produce separate Orca `print-project.3mf` plus effective-settings/provenance artifacts |
| Automatic “optimal” slicer settings | **bounded objective-driven selection** | choose best candidate among actually sliced/validated allowlisted candidates; never claim global optimum |

## 6. Resulting minimal P2 product scope

P2 reduces to four responsibilities:

1. **Revision-bound engineering evidence** over authoritative Fusion state, enriched by mesh/external-provider evidence where appropriate.
2. **Provider composition**: Fusion-native facts first; Trimesh for mesh evidence; Orca/Fusion Automation as optional external providers; every conclusion remains attributable.
3. **Versioned recipe intent**: small declarative recipe definitions and deterministic plan/proof metadata over existing semantic CAD operations. Execution is capability-gated by transaction semantics that genuinely exist; P2 does not build another Safe Executor.
4. **Print Preparation**: optional Orca-backed composition of a qualified machine/nozzle/filament/process profile with a revision-bound neutral 3MF, bounded candidate evaluation, and a reproducible `print-project.3mf` plus effective-settings/provider evidence.

## 7. Architecture decision

On 2026-09-13 the owner approved **Option A — Thin evidence facade + provider adapters + minimal recipe layer**, extended with optional Orca-backed Print Preparation. Options B and C remain rejected as the primary P2 substrate.

The canonical design is `docs/superpowers/specs/2026-09-13-fusion-cad-agent-api-v1-p2-reuse-design.md`. This research document remains the measured evidence basis, not implementation authorization.
