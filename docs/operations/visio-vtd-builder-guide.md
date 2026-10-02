# Visio VTD/GOST Builder Guide

## Purpose

This guide is mandatory for any Development Bridge work that controls Microsoft Visio live and builds or edits VTD/GOST electrical normal schemes. It records the qualified behavior discovered against the owner's real Visio stencils and KRU-35 reference drawings.

The goal is to prevent future chats or executors from rebuilding the same knowledge by trial and error.

## Non-negotiable visual QA

Never accept a Visio drawing from COM success, ShapeSheet telemetry, IDs, or coordinates alone.

For every substantial drawing stage, use this loop:

1. mutate the drawing;
2. call `visio_snapshot`;
3. call `visio_result_view`;
4. inspect the actual rendered image;
5. correct anything visually wrong before continuing.

Required visual gates:

- page/layout;
- first representative cell;
- complete equipment placement;
- labels/text orientation;
- final drawing.

Do not treat SaveAs or a green tool response as final acceptance without a final rendered visual inspection.

When the owner leaves a manual reference page in the document, preserve it and build on a separate page unless explicitly told otherwise.

## Native VTD/GOST masters only

Use the owner's actual opened VTD/GOST stencils and native masters. Do not replace available masters with ad-hoc rectangles, arbitrary lines, or external boxed labels.

A COM `Drop` is not always equivalent to a manual Visio drop. Some masters depend on post-drop state in:

- Shape Data (`Prop.*`);
- User cells (`User.*`);
- Actions (`Actions.*`);
- controls / text anchors (`Controls.*`, `Txt*`);
- child shapes inside a group;
- stencil/document macros.

When a COM-dropped master renders differently from the manual reference, compare both shapes structurally before guessing. Verify master identity, Shape Data, User cells, Actions, controls, child text, voltage class, text angle, and rendered output.

If a manual drop has a repeatable side effect that COM does not execute, reproduce that side effect in the native group/state and encode it as reusable builder behavior.

## Voltage class and native color

For these VTD masters, 35 kV is native index `10`:

```text
Prop.u = INDEX(10,Prop.u.Format)
User.i = 10
```

The native 35 kV color is brown. Do not force RGB when the master already contains voltage-class color logic.

The voltage class must also be set on outgoing continuation / object-link shapes. Verified KRU-35 reference behavior:

- input object link: 35 kV;
- outgoing feeder 1 object link: 35 kV;
- outgoing feeder 2 object link: 35 kV;
- reserve object link: 35 kV;
- TSN / `РУ СН` object link: below 3 kV, native index `16`.

A black outgoing line is a strong indicator that the object-link shape retained its default/undefined voltage class.

## Switching states and withdrawable positions

Withdrawable position is stored in `User.p`:

- `0` — working / рабочее;
- `1` — repair / ремонтное;
- `2` — control / контрольное.

ON/OFF is normally controlled by the master's native `Actions.Row_1`. Prefer `Trigger()` through the managed tools instead of arbitrary ShapeSheet writes.

Always read the state back after mutation.

For the current KRU-35 reference, the reserve is normally:

- OFF / ОТКЛ;
- withdrawn to repair position / ремонтное (`User.p = 1`).

Never assume the default Drop state is the required normal state.

## Busbar: `Шина10`

The verified bus master is `Шина10` from `Шины.vss`.

For the six-cell KRU-35 reference:

- `Prop.rt = INDEX(7,Prop.rt.Format)` -> 40 mm connection-point spacing;
- `Prop.tp = INDEX(5,Prop.tp.Format)` -> 6 points;
- native width is calculated automatically (`Prop.rt*(Prop.tp-1)+10 mm`, about 210 mm for this case);
- native line weight uses `ThePage!Prop.sh` (reference page approximately 2.5 mm).

Do not manually resize `Шина10` when its native properties define the point count and spacing.

`Actions.Row_1` controls visibility of the connection-point contours. In the verified manual reference:

```text
Actions.Row_1.Action = FALSE
```

Triggering it once hides the point contours and is incorrect for the target appearance.

The bus is a group. Its child shapes contain native point numbers. Manual Visio drop populated `1..6`; COM drop created the child shapes but left their `Text` blank. When the post-drop macro does not run, restore those texts inside the `Шина10` group rather than adding external number labels.

For the verified six-point group, the generated child slots carry `2,3,4,5,6,1` in their corresponding native subshapes.

Preserve both the native circles and native numbering.

## Cell construction and geometry

Build and visually accept one representative cell before replicating the pattern.

Prefer native 1-D shapes with exact endpoints over independent symbols plus arbitrary connector lines.

The manual KRU-35 reference uses approximately 40 mm horizontal spacing between cell axes.

Verified outgoing-feeder geometry:

- breaker/withdrawable device vertical span: 29.25 mm;
- CT immediately below: 15 mm;
- the CT bottom, OPN top, grounding-switch top, and TT-NP top share the same electrical node;
- OPN branch: about +7.5 mm from the main vertical axis;
- grounding-switch branch: about -7 mm from the main vertical axis;
- horizontal branch between them: about 14.5 mm;
- TT-NP in this reference is a regular `ТТ` master stretched vertically about 42.5 mm, not `ТТ для ЛЭП`;
- use native `Связь с объектом2` below the cell where appropriate and set its voltage class explicitly.

## Current KRU-35 cell semantics

Use the owner's manual page/video as the primary visual authority. The qualified topology is:

### Input

`ЛР-35` -> CT -> branch OPN + grounding switch -> stretched TT-NP -> cable/object link.

### Outgoing feeder 1

Withdrawable breaker cart -> CT -> branch OPN + grounding switch -> stretched TT-NP -> object link.

### Outgoing feeder 2

Same topology as outgoing feeder 1.

### TSN

Breaker -> CT -> grounding-switch branch -> TSN -> `РУ СН` object link.

### TN

Bus branch with OPN + grounding switch, then the native withdrawable connector / fuse path -> voltage transformer. Do not invent a breaker-cart topology here.

### Reserve

Cable-feeder style matching the reference, with the normal state OFF and in repair position.

## Native labels and text orientation

Prefer each master's own text. Avoid external boxed labels unless the reference explicitly uses them.

Text layout commonly depends on:

- `Controls.Row_2`;
- `TxtPinX` / `TxtPinY`;
- `TxtWidth` / `TxtHeight`;
- `TxtAngle`;
- `Actions.Row_2`.

Copy the state of a known-good manual reference shape rather than moving text by arbitrary coordinates.

For OPN and grounding-switch shapes in the verified reference:

```text
Actions.Row_2.Action = TRUE
TxtAngle = 180 deg
```

Fresh COM drops came in with a different text-orientation state (`FALSE` / 90 deg), which caused collisions.

Exact whitespace and line breaks can influence `TEXTWIDTH(TheText)` and therefore placement. Preserve verified native text formatting when cloning a reference shape.

## Managed tooling

The Windows Visio agent is bootstrapped for server-managed extension updates. Do not ask the owner to run another one-off PowerShell patch for routine new capabilities.

Use `visio_managed_update` to deliver server-pinned managed extension versions. A manual Windows bootstrap is only justified if the managed-update mechanism itself is broken.

The visual path is qualified end-to-end:

```text
Visio
  -> render_page_png
  -> Windows agent
  -> Development Bridge external image resource
  -> visio_snapshot
  -> visio_result_view
  -> actual ImageContent visible to the coordinator
```

Current managed capability family includes:

- visual page snapshots;
- managed extension updates;
- exact Shape Data read/write;
- VTD state read/write;
- User/Actions controls;
- 1-D endpoint control;
- connection-point inspection;
- native text-anchor control;
- batch endpoint/text/text-anchor updates;
- batch ShapeSheet cell reads.

When a generally reusable capability is missing, extend this managed API. Do not proliferate one-off `.ps1` patches.

## Working discipline

- Preserve reference pages unless explicitly authorized to modify them.
- Build automated variants on a separate page (for example `MCP-v2`).
- When rendering differs from the manual reference, compare the two native shapes before applying cosmetic fixes.
- Prefer native master state and stencil behavior over forced formatting.
- Treat the current KRU-35 `MCP-v2` result as a qualified working baseline, not proof that every unrelated VTD master has the same post-drop behavior.
