# EnergoLogic Editor — live checkpoint 2026-10-04

Current branch: `feature/energologic-visio-qol-001`.

## Runtime

- bridge implementation before this checkpoint: `05a877e`;
- managed Visio extension: `2026.10.03.111`;
- live add-in: `EnergoLogic.VisioEditorAddinV313`;
- editor API: `0.3.13`;
- `visio-workstation`: online;
- source page `MCP-v2`: keep immutable.

Editor v3.13 uses explicit two-phase Cell Pitch distribution:

1. geometry move + pending topology plan;
2. `ApiCompletePendingTopology` restores and verifies Glue.

The UI invokes phase 2 after the original button handler returns.

## Latest live acceptance

Disposable page: `UI-V313-Pitch-Delay-Probe`.

- slot 3 was removed completely; 44 shapes remained;
- `SelectCell(155)` returned 11 members:
  `[155,158,160,162,166,182,240,242,244,249,250]`;
- `MeasurePitch([66,155])` returned `80 mm`;
- `DistributePitch(40)` phase 1 succeeded.

A deliberate **10 second** delay before phase 2 did **not** help.

Phase 2 still failed on:

`244.End -> 166 / Connections.1`.

Compensation also failed on the same edge after moving geometry back.

Therefore the remaining problem is **not** simply VTD settle time and should not be attacked with larger blind delays.

## Discriminating evidence

Immediately after failure, `244.End` was half-glued:

- `EndX FormulaU = 190 mm`;
- `EndY FormulaU = PAR(PNT(ТСН2!Connections.1.X,ТСН2!Connections.1.Y))`;
- no real EndX `Connects` entry existed.

On the same page, immediately afterward, the managed-extension low-level tool:

`batch_glue_endpoints([{shape_id:244, endpoint:"end", target_shape_id:166, target_connection_row:1}])`

succeeded without extra waiting.

Post-check `get_connections` then confirmed:

`244.EndX -> 166 / Connections.1.X`.

So:

- native Visio `GlueTo` is valid;
- target `166/Connections.1` is valid;
- the remaining defect is localized to the C# add-in detach/restoration path.

## Next exact investigation

Do not resume Undo research.

On a fresh disposable copy of `MCP-v2`:

1. instrument `244.EndX/EndY` formulas before detach, after detach and after every GlueTo attempt;
2. compare C# `DetachEndpoint / GlueEndpointWithRetry` with the proven Python `batch_glue_endpoints` semantics;
3. focus on X/Y endpoint normalization — current `DetachEndpoint` writes both coordinates, while `GlueEndpoint` glues only X;
4. accept Cell Pitch distribute only after authoritative `get_connections` confirms the complete TSN topology.

Undo remains deferred technical debt and must not block completion/polish of the user-facing Editor.
