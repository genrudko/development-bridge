# Fusion CAD Hands P1 Slice Design

**Status:** APPROVED by owner on 2026-09-11.

## Goal

Add the first practical rich-modeling slice behind the existing `fusion.cad/v1` facade without replacing the accepted P0 Autodesk provider, without exposing Shimmer's raw index/name contract, and without weakening revision/transaction safety.

## Provider topology

A logical workstation resolves to explicit provider roles:

- `reference`: accepted Autodesk/P0 provider;
- `rich`: pinned Shimmer provider;
- `eyes`: read-only eyes provider when configured.

The model-facing request continues to name the logical workstation. Provider routing is configuration, not a hard-coded `fusion-workstation -> fusion-shimmer` string substitution.

## Public first slice

Add `fusion_sketch` and `fusion_feature` only.

`fusion_sketch` supports:

- `create` on `xy`, `xz`, `yz`, or a planar face ref;
- `batch` against one sketch with line, rectangle, circle, geometric constraint, and driving dimension actions;
- symbolic intra-batch action references so constraints/dimensions do not depend on caller-visible Shimmer curve indices;
- `expected_revision` for committed mutations;
- `dry_run=true` for preview/abort.

`fusion_feature` supports `create` with kinds:

- `extrude`;
- `hole`;
- `fillet`;
- `chamfer`.

All committed mutations require `expected_revision`. All requests are strict (`extra=forbid`) and finite-valued. The known Shimmer schema defect is normalized: distance/horizontal/vertical/angular dimensions require `entity_two`; radial/diameter dimensions reject it when inappropriate.

## Shimmer reuse envelope

Do not copy Shimmer CAD algorithms into Development Bridge. Keep the upstream Shimmer operations as the modeling implementation.

Development Bridge owns a small source-controlled overlay under `ops/fusion_shimmer_overlay/` containing:

- an add-in operation module with `bridge.cad_guard` and `bridge.cad_apply`;
- a sidecar tool module exposing only `_bridge_cad_guard` and `_bridge_cad_apply` to Development Bridge;
- an installer/manifest that targets the exact pinned Shimmer commit and fails closed on mismatch.

`bridge.cad_apply` executes on Shimmer's existing Fusion main-thread dispatcher and may delegate only an explicit allow-list of operations used by this slice. Arbitrary registry dispatch is forbidden.

For a committed call:

`guard -> PTransaction.Start -> delegated Shimmer operation(s) -> private token/effect evidence -> PTransaction.Commit`.

For `dry_run=true`:

`guard -> PTransaction.Start -> delegated Shimmer operation(s) -> private effect evidence -> PTransaction.Abort -> verify baseline guard restored`.

Failures after transaction start abort when the outcome is proven local and abortable. Lost/uncertain commit outcomes are never replayed automatically.

## Provider guard and coherence

Public model revision remains the existing `rev_N` derived from the authoritative P0 fingerprint. The Shimmer provider guard is private supplementary evidence bound to a P0 revision; it does not become a second public revision dialect.

An edit-ready binding uses a coherence handshake:

`Shimmer guard A -> authoritative P0 observation -> Shimmer guard B -> require A == B -> bind B to rev_N`.

The provider guard is canonical and deterministic over the active document identity plus mutation-sensitive Shimmer-readable state used by this slice, including component revision ids, occurrence transform/grounding/visibility, design parameters, and reserved Bridge attributes that the overlay can read reliably. The live gate must falsify it with manual sketch/feature, other-component, occurrence-transform, and parameter changes before Hands is reported supported.

Immediately before mutation, `bridge.cad_apply` recomputes the guard on Fusion's main thread and rejects mismatch before `PTransaction.Start`. There is no IPC/UI return between guard verification and transaction start/apply.

## Opaque refs

Shimmer indices/names are adapter-private. Public results use only existing `ent_*` refs.

Inputs carrying `ent_*` are resolved through the existing `EntityRefRegistry`; only the private native token is forwarded to the Shimmer envelope. The overlay resolves tokens through Fusion's native entity-token lookup and validates expected entity kind/context before delegation.

The envelope snapshots entity-token sets before/after delegated operations and returns private created/changed entity evidence. Bridge registers public refs only after proven commit. Preview-created refs are never registered.

## Transactions

Do not build a second transaction state engine. The first slice proves standalone commit and `dry_run` through the guarded Shimmer envelope. Only after live proof should the same declarative sketch/feature actions be added to the existing `fusion_transaction` plan/replay machinery.

## Safety and scope

- No document save/close side effects.
- Never mutate the protected `Schedule` original during development or acceptance.
- No raw agent-authored Python path.
- Shimmer arbitrary-code tools remain disabled.
- Official Autodesk/P0 read/view/reference behavior remains intact.
- No push/merge/deploy in this implementation task unless separately authorized.
- Live Fusion acceptance is a later gate; this plan performs offline implementation and review only.
