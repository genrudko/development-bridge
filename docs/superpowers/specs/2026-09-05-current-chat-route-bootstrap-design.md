# Current-chat route bootstrap design

## Problem

`coordinator_route_bind_current` can only bind an already registered logical route. A chat that needs a new logical identity therefore has no safe URL-free bootstrap path and is pushed toward reusing another route or legacy `takeover(url=...)`.

## Goal

Allow a current ChatGPT conversation to create and bind a missing logical route through the existing out-of-band bind-card flow, without exposing or requesting physical ChatGPT URLs, conversation IDs, project IDs, session IDs, redirect targets, tokens, or markers in model-visible context.

## API

Extend `coordinator_route_bind_current` with optional `bootstrap_if_missing: bool = false`.

- Existing route: preserve current bind semantics exactly.
- Missing route + `bootstrap_if_missing=false`: keep current `INVALID_ARGUMENT unknown route` behavior.
- Missing route + `bootstrap_if_missing=true`: create a pending bootstrap bind operation only; do not create a route yet.

## State machine

`missing -> bootstrap_pending -> candidate_validated -> commit -> bound route generation 0`

Before commit, no route entry, channel, generation, default-route change, requested-route change, session binding, or delivery lease is created.

On commit, atomically create exactly one route with:

- requested `route_id`;
- `generation=0`;
- channel derived by the existing route-channel naming policy;
- `binding_state=bound`;
- validated current physical ChatGPT target and project identity from the OOB return flow.

Replay is idempotent only for the already committed same operation. Concurrent creators for the same missing route fail closed or converge to exactly one committed route; they must never create two generations or overwrite a different physical target.

## Safety

- No marker/search fallback.
- No model-visible physical target material.
- Failed, expired, replayed, malformed, cross-project, or uncommitted bootstrap leaves no logical route behind.
- Existing-route bind behavior and exclusive X endpoint ownership remain unchanged.
- `takeover(url=...)` remains legacy/manual migration only and is not used by ordinary bootstrap.

## Integration

Reuse `RouteControlService` and the current bind-card/openExternal/return/commit flow. The route registry gains only the minimum pending-bootstrap representation and atomic create-on-commit operation needed to support a missing source route.

## Acceptance

1. Missing route without the flag still fails.
2. Missing route with the flag returns bind-pending while registry remains route-free.
3. Commit creates generation 0 exactly once using OOB-validated target.
4. Failed/expired/replayed/cross-project operations leave no route.
5. Existing-route bind regression suite remains green.
6. Tool schema exposes `bootstrap_if_missing` and compact/direct surface remains unchanged otherwise.
7. Full test suite passes and independent review reports no load-bearing findings.
