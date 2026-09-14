# Wake v3 VPS-Only Nonce Rendezvous Design

**Date:** 2026-09-14
**Status:** Accepted for implementation
**Supersedes:** Browser Binder as the canonical bind path in `2026-09-14-rdc-wake-v2-design.md`

## Goal

Bind a logical Development Bridge route to the exact current ChatGPT conversation without depending on the owner's desktop, browser extension, copied URL, or direct `Dev_Bridge` namespace. After binding, wake delivery remains fully VPS-resident.

Canonical flow:

```text
ChatGPT turn emits one-time DBRIDGE_BIND marker
  -> ReviewGPT authenticated browser on VPS
  -> ChatGPT Global Search exact marker rendezvous
  -> exact candidate verification
  -> existing RouteControl candidate + commit guards
  -> durable route binding

job -> ReviewGPT wake -> exact bound chat
    -> RDC -> GPTAdmin -> development-bridge -> coordinator_ack
```

Browser Binder remains an emergency/manual fallback only.
## Proven feasibility and constraint

The authenticated ReviewGPT Chromium profile exposes ChatGPT Global Search on the VPS. A native-CDP probe found an older exact phrase from this conversation with exactly one result, proving account-history content search works without the owner's computer.

A freshly emitted random probe marker initially returned zero results. Therefore ChatGPT search indexing is eventual-consistent. Rendezvous is a durable retrying workflow, not a single synchronous lookup.

The resolver must drive the Search UI with native browser input and verify the input value before trusting results. Direct assignment to the React-controlled input is not valid evidence because it can leave stale results visible.

## Rendezvous identity

Bridge generates a cryptographically random, URL-safe nonce with at least 128 bits of entropy and formats the visible marker as:

```text
DBRIDGE_BIND bnd_<nonce>
```

The nonce is a rendezvous locator, not an authorization credential. It is intentionally model-visible. The hidden current-bind token, physical ChatGPT URL, conversation ID, project ID, and binder bearer remain non-model-visible.

One active rendezvous per logical `route_id` is allowed. Preparing another rendezvous for the same route replaces only a stale/terminal rendezvous; it must not silently supersede a live one.
## Durable state and retry policy

Rendezvous state is stored separately from physical route bindings. It contains only logical/safe data: `route_id`, `expected_generation`, nonce, creation/expiry time, retry counters, next-attempt time, and terminal error code if any. It never persists a candidate ChatGPT URL or conversation identifier.

The default TTL is 30 minutes. Retry delays are `5s, 15s, 30s, 60s`, then 120 seconds capped until expiry. Bridge restart restores pending rendezvous and continues from the durable `next_attempt_at` value.

Search result semantics operate on **deduplicated canonical conversation identities**, not raw result rows:

- zero unique exact candidates -> keep pending and retry;
- exactly one -> verify the candidate conversation contains the exact marker in exactly one message turn, then attempt guarded bind;
- more than one -> terminal `RENDEZVOUS_AMBIGUOUS`, binding unchanged;
- TTL expiry -> terminal `RENDEZVOUS_EXPIRED`, binding unchanged.

Transient browser/search failures retry while TTL remains. Login/Cloudflare intervention becomes `owner_input_required` and does not guess or bind.

## Candidate verification and commit

The search resolver may hold the candidate URL only in process memory. It must never print it to normal logs, tool results, diagnostics, or durable rendezvous state.

Before binding, the service acquires the existing route lock and verifies the route still exists at `expected_generation`. It then creates a normal hidden current-bind operation internally and immediately reuses existing `accept_bind_return(..., retain_return_target=False)` plus `commit_bind(...)`.

Existing project-policy, generation, token replay, and canonical ChatGPT target validation remain authoritative. The rendezvous layer does not implement parallel binding rules.
## ReviewGPT integration

Do not introduce a second ChatGPT browser profile. Rendezvous search reuses the same authenticated ReviewGPT Chromium lifecycle, configured Node executable, CDP endpoint, and operation lock as wake delivery so search and wake cannot manipulate the profile concurrently.

Add a small repository-owned Node helper for ChatGPT Global Search. It uses CDP native input, waits for the search input to exist, verifies the exact query value, waits for loading to settle, canonicalizes and deduplicates conversation result URLs, and opens a sole candidate to verify the marker against message-turn DOM.

The helper emits structured JSON to its parent process. A physical candidate URL is emitted only for a verified single candidate and is consumed in memory by Bridge; it is never copied into user/model output or durable files.

## Model-visible MCP surface

Add compact-visible `coordinator_route_bind_rendezvous_prepare(route_id, allow_project_change=false)`.

Success data is exactly safe rendezvous state: `route_id`, `state`, `generation`, `marker`, and `expires_at`. The tool description requires the calling assistant to emit the returned marker exactly once in visible chat text in the same turn. No bind token, operation URL, physical target, or Browser Binder credential is returned.

Extend existing widgetless `coordinator_route_control_status(route_id)` with safe rendezvous diagnostics: state, attempt count, expiry, and terminal error code. Do not expose nonce through status after preparation.

## Browser Binder compatibility

The existing Browser Binder extension/API remains installed and tested as a manual recovery mechanism. Documentation and guide text must stop calling it canonical or required. No Browser Binder behavior is removed in Wake v3.
## Security and failure invariants

- The nonce authorizes nothing by itself; only the guarded server-side current-bind operation can mutate a route.
- Search is exact-marker only. No title heuristics, fuzzy fallback, recent-chat guessing, or user-supplied physical URL is allowed.
- Candidate rows are deduplicated by canonical ChatGPT conversation identity before ambiguity evaluation.
- A sole search result is still not trusted until the opened conversation contains the exact marker in exactly one message turn.
- Generation/project-policy mismatch, route deletion, stale rendezvous, or commit failure leaves the previous active binding unchanged.
- No candidate physical identity may appear in normal logs, model-visible tool payloads, durable rendezvous state, or review packages.
- `uncertain` wake semantics remain unchanged and never trigger a second transport resend.

## Acceptance

1. Prepare through `RDC -> GPTAdmin -> development-bridge` returns only the safe marker envelope.
2. With the owner's desktop/browser absent, ReviewGPT on the VPS observes `0` while indexing is pending and retries durably across Bridge restart.
3. A unique indexed marker resolves to one verified conversation and commits through existing route guards exactly once.
4. Zero results do not mutate binding; multiple unique results fail closed; generation/project races fail closed; expiry fails closed.
5. Browser/login intervention is reported without guessing and can resume without recreating the route.
6. Browser Binder remains green as fallback but is absent from the canonical operator path.
7. After VPS-only binding, a synthetic durable job produces one ReviewGPT wake in that exact chat.
8. The resulting turn re-enters only through `RDC -> GPTAdmin -> development-bridge`, calls `coordinator_ack` once, and leaves no duplicate pending wake.
9. Existing direct-App bind, Browser Binder, route-control, and ReviewGPT wake test suites remain green.
