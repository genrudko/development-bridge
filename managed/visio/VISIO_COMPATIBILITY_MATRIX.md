# EnergoLogic Visio Editor — compatibility matrix

Baseline: **V364 / API 0.3.64**
Date: **2026-10-07**

## Qualification levels

- **LIVE PASS** — the exact environment was exercised with the running add-in.
- **ARCH/PACKAGE PASS** — architecture, compiler target, registration model and packaged
  dependency contract support the environment, but that exact Visio SKU was not installed
  on the current qualification workstation.
- **PENDING LIVE** — requires a machine/VM with the exact Visio SKU/bitness.

## Matrix

| Visio | 32-bit | 64-bit | Current status | Evidence / remaining gate |
|---|---:|---:|---|---|
| 2010 | target | target | ARCH/PACKAGE PASS; PENDING LIVE | AnyCPU binary, dual registry views, no runtime PIA dependency; run clean install + UI + geometry + cell topology + Undo/Redo on real Visio 2010 |
| 2013 | target | target | ARCH/PACKAGE PASS; PENDING LIVE | Same package contract; real SKU runtime acceptance pending |
| 2016 | target | target | ARCH/PACKAGE PASS; PENDING LIVE | Same package contract; real SKU runtime acceptance pending |
| 2019 | target | target | ARCH/PACKAGE PASS; PENDING LIVE | Same package contract; real SKU runtime acceptance pending |
| 2021 | target | target | ARCH/PACKAGE PASS; PENDING LIVE | Same package contract; real SKU runtime acceptance pending |
| Microsoft 365 / Visio 16.x | target | **LIVE PASS on current host** | LIVE PASS for installed host | V364 connected; Ribbon/context/panel visible; geometry regression PASS; real-cell helper transaction PASS |

## Compatibility mechanisms

### Binary architecture

- add-in DLL: `AnyCPU`;
- topology helper EXE: `AnyCPU`;
- no release dependency on a fixed `x64` CLR target.

### COM registration

On 64-bit Windows the installer manages both:

- `Registry64`;
- `Registry32`.

This is required because Visio bitness, not Windows bitness alone, determines which COM
registration view is observed by the Office host.

### Office interop

The release build embeds the Office COM type metadata used by the add-in. The shipped DLL
is validated so that `Assembly.GetReferencedAssemblies()` contains no runtime reference to:

- `Office`;
- `Extensibility`;
- `Microsoft.VisualStudio.Interop`.

`IDTExtensibility2`, `ext_ConnectMode` and `ext_DisconnectMode` are declared locally with
their COM GUIDs, DispIds and marshaling contract. This removes the Visual Studio Interop
runtime dependency.

### Target installation

The target PC receives prebuilt binaries. The installer does not invoke `csc.exe` and does
not search for Office PIA. Source files remain in the package only as audit material.

Required target prerequisites are therefore bounded to:

1. Windows 10/11;
2. Microsoft Visio desktop;
3. .NET Framework 4.x runtime (present/enable-able on the target OS);
4. permission for per-user COM add-in registration under HKCU.

## Live qualification procedure for each historical SKU

For every Visio version/bitness still marked `PENDING LIVE`:

1. start from a clean Windows user profile / clean EnergoLogic registration state;
2. unpack the canonical ZIP and run package validation;
3. install per-user without admin rights where policy permits;
4. launch Visio through the EnergoLogic launcher;
5. verify exactly one connected EnergoLogic ProgID and visible native UI;
6. execute Coordinates, Exact Offset, Align, Distribute, Base Copy/Move;
7. execute Select Cell + real-cell Move/Distribute with Glue verification;
8. verify one native Undo restores the complete geometry/topology state and one Redo
   restores the forward state;
9. close/reopen Visio and repeat a minimal smoke to detect load/registration regressions;
10. uninstall and verify both registry views and installed files are cleaned.

Only after these steps may that exact SKU/bitness be promoted from `PENDING LIVE` to
`LIVE PASS`.
