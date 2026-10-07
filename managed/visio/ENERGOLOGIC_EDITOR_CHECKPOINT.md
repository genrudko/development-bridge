# EnergoLogic Visio Editor — canonical baseline 2026-10-07

Current branch: `feature/energologic-visio-qol-001`.

This file is the canonical checkpoint for the Visio-based EnergoLogic editor tranche.
It supersedes the historical V313 checkpoint and the intermediate Undo/interop probes.

## Accepted runtime baseline

- editor release: **V364**;
- ProgID: `EnergoLogic.VisioEditorAddinV364`;
- editor API: **0.3.64**;
- managed extension/package transport: **2026.10.06.213**;
- Windows target: **Windows 10/11**;
- Visio target: **Microsoft Visio 2010 and newer, 32/64-bit**;
- live workstation acceptance: installed Visio **16.x**;
- active acceptance document: `KRU-35_normal_scheme_v2_energologic_qol_host_v1.vsdm`;
- canonical reusable acceptance page: `UI-V318-Pitch-Acceptance`.

V364 is connected live and is the only connected EnergoLogic editor add-in in the current
Visio process. Historical V31…V363 registrations are treated as legacy and are removed
or disconnected by the installer/migration path.

## Production architecture

EnergoLogic uses Microsoft Visio as the drawing/interaction host. The editor add-in owns:

- native RibbonX commands;
- drawing context-menu commands;
- modeless WinForms parameter panel;
- cell/equipment operations;
- geometry helpers;
- topology/Glue repair and validation;
- diagnostics and validation surfaces.

Compound topology-sensitive operations use the external
`EnergoLogic.TopologyRestoreHelper.exe`. Geometry mutation, Glue restoration and
verification are executed by one external COM owner inside one native Visio UndoScope.
The add-in does not hold a Visio UndoScope across separate COM callback boundaries.

The rejected research paths are no longer part of production code:

- cross-callback/cross-process held UndoScope;
- `IVBUndoUnit` ShapeSheet mutation;
- acceptance-only bare Undo/Redo/keyboard/probe tools;
- helper-owned probe-only modes.

Read-only operational diagnostics remain where they are useful for support.

## Native Undo/Redo conclusion

Research established the following:

1. custom `IVBUndoUnit` can register and receive `Do()`, but Visio rejects the relevant
   ShapeSheet writes from that callback; it is not the production mechanism;
2. one helper process that owns both `BeginUndoScope/EndUndoScope` and all compound
   mutations produces a real native one-step Undo/Redo unit;
3. selection changes must not occur inside the compound native scope;
4. VTD-sensitive 1-D geometry must be verified/repaired before commit;
5. production Move/Distribute therefore use the helper-owned single-scope transaction.

The real-cell production path was live accepted during the V361 series with one native
Undo/Redo unit. V364 keeps the same accepted transaction logic and its final live smoke
reported the production transaction as one native Undo/Redo unit.

## Final V364 live acceptance

On a fresh disposable duplicate of `UI-V318-Pitch-Acceptance`, shape 155 was moved from
slot 3 to slot 4:

- horizontal shift: **+40.00 mm**;
- operation state: `success`;
- restored Glue edges: **3**;
- verified connections: **8**;
- shape count preserved: **44 → 44**;
- transaction result reports one native Undo/Redo unit.

Post-operation ShapeSheet inspection confirmed that the previously fragile 1-D objects
remained geometrically consistent:

- shape 155: `BeginX = 190 mm`, `EndX = 190 mm`, PinX derived correctly;
- shape 244: both endpoints remained glued and `BeginX = EndX = 190 mm`.

The disposable V364 smoke page and the temporary V362 geometry regression pages were
removed after acceptance. Historical acceptance/probe pages from earlier development
iterations were intentionally not mass-deleted.

## User-facing geometry regression

The final tranche also revalidated the normal geometry commands on disposable pages:

- Coordinates;
- Smart Nudge;
- Exact Offset;
- Snap to 5 mm grid;
- Align X / Align Y;
- Distribute selection X;
- Measure selection distance;
- Duplicate Selected;
- Base Move;
- Base Copy.

Representative exact checks included a snap to **60 × 40 mm** and reversible exact
offsets returning to the original coordinates.

## Standalone/offline package

Canonical package name:

`EnergoLogic-Visio-Editor-Kit-0.3.64.zip`

Final validated build on 2026-10-07:

- size: **689,913 bytes**;
- SHA-256: `3a584ee4bc1178809b1fe47bca42904446a2901d53c7eeb611bb2d4dcc820aff`;
- manifest entries: **23**;
- bundled personal ГОСТ stencils: **10**;
- third-party VTD files: **not included**.

The target machine does **not** compile the add-in. The ZIP contains prebuilt AnyCPU:

- `bin/EnergoLogic.VisioEditorAddinV364.dll`;
- `bin/EnergoLogic.TopologyRestoreHelper.exe`.

The source payload is kept in the package for audit/reproducibility, but installation only
validates and copies the prebuilt binaries.

Target-side installation therefore does not require:

- Internet;
- ChatGPT/MCP/Python;
- Visual Studio;
- C# compiler (`csc.exe`);
- Office/Visio PIA deployment;
- Visual Studio Interop assembly;
- Office `.NET Programmability Support` feature.

Office CommandBars/Ribbon COM types are embedded into the release DLL at build time.
`IDTExtensibility2` is declared locally using the official COM identity and marshaling
contract. Reflection validation of the shipped DLL rejects runtime references to
`Office`, `Extensibility` or `Microsoft.VisualStudio.Interop`.

`Install-EnergoLogic.ps1 -CompileOnly` is now a package/binary validation mode: it checks
`MANIFEST.json`, the prebuilt DLL/EXE and their dependency contract, and does not compile
or register COM.

## 32/64-bit compatibility design

The release binaries are `AnyCPU` and both the portable installer and the bridge installer
write/remove per-user COM/add-in registration in both 32-bit and 64-bit registry views on
64-bit Windows. This avoids binding the package to one Visio bitness.

## Compatibility status

See `VISIO_COMPATIBILITY_MATRIX.md` for the qualification matrix.

Important distinction:

- Visio 2010+ compatibility is an **architectural and compile/package-qualified target**;
- the current workstation provides direct live runtime evidence only for Visio 16.x;
- claiming physical live acceptance of Visio 2010/2013/2016/2019/2021 requires those
  actual SKUs/bitnesses to be installed and exercised on qualification machines.

No unsupported live-pass claim is made for an uninstalled historical Visio version.

## Regression gates at this checkpoint

Focused Visio suite after final standalone restructuring:

- `139 passed`;
- `python -W error -m py_compile managed/visio/visio_managed_extension.py` — PASS;
- `git diff --check` — PASS.

Full repository pre-commit gate:

- normal full run: **2507 passed, 1 failed**;
- the single failure is `tests/unit/test_coordinator_ui_static.py::test_coordinator_ui_uses_adaptive_leased_polling`;
- this failure is proven **pre-existing on HEAD `d1f1282d9451c4c6949cb770db502501f294a007`**: the untouched test expects `development-bridge/poll-leader-v1/${channelId}` while the untouched HEAD HTML already contains `development-bridge/poll-leader-v2/${channelId}`;
- no EnergoLogic/Visio file touches that Coordinator area;
- rerun with exactly that pre-existing test deselected: **2507 passed, 1 deselected in 110.30 s**.

The unrelated Coordinator mismatch is deliberately not modified in this Visio baseline commit.

## Frozen decisions

1. Visio is the graphics/UI host; do not restart a standalone diagram editor effort.
2. Russian UI / engineering terminology; English identifiers in code.
3. Production compound topology mutations use the helper-owned single native UndoScope.
4. Do not reintroduce `IVBUndoUnit` or cross-call held-scope research paths without new
   evidence that changes the underlying Visio constraints.
5. Release add-in binaries are AnyCPU and prebuilt; target installation must remain
   independent of a compiler/PIA toolchain.
6. Historical Visio support must be qualified honestly by real SKU/bitness when available.
7. Third-party VTD assets are never silently bundled into the portable package.
8. No Ready-for-Review or merge action without an explicit owner command.
