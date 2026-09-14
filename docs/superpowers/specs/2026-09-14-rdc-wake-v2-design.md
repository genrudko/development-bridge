# RDC / GPTAdmin Wake v2 Design

**Date:** 2026-09-14
**Status:** Accepted for implementation

This design updates current-chat binding and continuation re-entry for the new canonical GPTAdmin ingress.
## Problem

ReviewGPT already delivers durable continuations into a bound ChatGPT conversation. Initial binding still depends on the direct Development Bridge MCP App.

The canonical ingress is now `ChatGPT -> RDC -> GPTAdmin -> development-bridge`. RDC does not supply the return target used by the existing bind flow.
Wake v2 keeps ReviewGPT as the delivery transport and uses a small browser helper for the one-time binding step.

The model handles logical route IDs and continuation IDs only.

## Reused infrastructure

The existing RouteRegistry prepare, candidate, and commit flow remains authoritative. Its existing TTL and generation checks are reused.
The direct `coordinator_route_bind_current` App flow remains available for compatibility. The canonical GPTAdmin path uses a new safe prepare tool that returns only `route_id`, `state`, and `generation`.

## Components

### Safe prepare tool

Add `coordinator_route_bind_prepare`. It accepts `route_id`, `allow_project_change=false`, and `bootstrap_if_missing=false`, calls the same route-control prepare logic, and returns no MCP UI metadata or operation credential.

This makes it safe to invoke through GPTAdmin, whose generic relay forwards the complete upstream MCP result.
### Browser binder API

Add a small authenticated HTTP surface under the existing route-control prefix:

- `GET /binder/pending` returns pending bind requests for the browser helper.
- `POST /binder/complete` accepts one pending operation plus the active ChatGPT tab URL and executes the existing candidate + commit flow.

The API uses a dedicated binder bearer secret configured separately from Bridge OAuth and route-control tokens. If the binder secret is absent, the binder endpoints are disabled.

The response contains only safe route state. The active tab URL is never returned by these endpoints.
### Browser helper

Add a Firefox/Chromium WebExtension in `browser-extension/bridge-binder/`. Its popup reads pending route requests and lets the owner bind the active ChatGPT tab to one selected logical route.

The helper stores its Bridge endpoint configuration in extension-local storage. Binding requires an explicit user click.

If exactly one route is pending it may be preselected. Multiple pending routes require explicit selection.
### Wake prompt

ReviewGPT remains the primary direct wake transport. The continuation prompt identifies the canonical re-entry path `RDC -> GPTAdmin -> development-bridge` and then instructs the next turn to call `coordinator_ack` once before continuing from durable state.

No second wake queue or transport state machine is introduced.

## Failure semantics

- Prepare failure changes no binding.
- Binder authentication failure changes no binding.
- An invalid active tab target changes no binding.
- Generation or project-policy races fail closed through the existing RouteRegistry checks.
- Repeating a completed operation does not create a second generation.
- ReviewGPT `uncertain` delivery semantics remain unchanged; no cross-transport resend is added.
## Security invariants

The model-visible MCP result from the safe prepare tool must not contain the pending operation token, operation URL, binder bearer, active-tab address, or control-token metadata.

The browser binder bearer is dedicated to binder endpoints and cannot authorize ordinary Bridge MCP, Git/GitHub operations, route unbind, or wake cancellation.

The existing direct App binding path continues to use its own existing operation and control metadata.

## Acceptance

1. A bind can be prepared through `RDC -> GPTAdmin -> development-bridge` with only safe fields returned to the model.
2. The browser helper can complete that pending bind from a ChatGPT tab with one explicit owner action.
3. Wrong bearer, wrong site, expired operation, project mismatch, and generation race all fail without changing the active binding.
4. After binding, a synthetic durable continuation is delivered by ReviewGPT into the bound chat.
5. The new turn can re-enter exclusively through RDC/GPTAdmin and ACK the continuation without requiring the direct `Dev_Bridge` namespace.
6. Existing direct-App binding tests and ReviewGPT delivery semantics remain green.
