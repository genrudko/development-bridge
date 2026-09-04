# ChatGPT Out-of-Band Route Control v1 — Design

**Date:** 2026-09-04  
**Status:** Accepted design, implementation not started  
**Scope:** Development Bridge coordinator route binding and wake lifecycle

## 1. Problem

Development Bridge can maintain durable coordinator routes and wake a ChatGPT conversation, but its current `current chat` discovery path depends on model-visible marker turns plus browser/search discovery. That approach is unreliable and creates a second, more serious operational risk: conversation addresses, conversation identifiers, route-discovery markers, and other chat-identifying protocol data may enter the model-visible conversation path. During live operation, chats that encountered such identity-bearing traffic were observed to lose Bridge tool availability at the conversation level.

The coordinator also lacks a complete route-control lifecycle. It can bind and wake, but operators do not have one coherent control plane for safe status, unbind, pending-wake cancellation, and diagnosis. A stale or wrong binding can therefore remain operationally sticky.

The goal of v1 is to make physical ChatGPT conversation identity an **out-of-band control-plane concern**. Physical chat identity must never be required in LLM context, user/assistant protocol turns, ordinary MCP tool prose, or model-visible diagnostics.

## 2. Feasibility evidence

A live spike on 2026-09-04 established the critical host behavior.

1. Standard MCP `openLink` opened the Bridge diagnostic page but did **not** provide any return metadata. The server observed no return-target query parameter.
2. ChatGPT-specific `window.openai.openExternal(...)`, with the Bridge domain present in `openai/widgetCSP.redirect_domains`, opened the same Bridge endpoint and ChatGPT appended a `redirectUrl` query parameter.
3. The Bridge server parsed that return value as an unambiguous conversation-specific ChatGPT target.
4. The spike passed without sending a user message and without calling `updateModelContext`.

The live server recorded only a sanitized classification:

- return target present: yes;
- conversation-specific target: yes;
- parameter key: `redirectUrl`;
- tested target: ordinary non-Project conversation.

This proves the core mechanism for ordinary Web chat. Project-chat and mobile behavior remain mandatory live acceptance gates before legacy discovery is retired.

## 3. Goals

1. Bind an existing logical Bridge route to the exact ChatGPT conversation from which the user initiates the action, without model-visible physical identity.
2. Provide a complete operator lifecycle: **bind/rebind, status, unbind, cancel wakes, unbind+cancel**.
3. Keep physical URL, conversation ID, project/GPT identity, redirect values, and one-time bind credentials outside model-visible context.
4. Preserve existing route generation, project-policy, and atomic route-update protections.
5. Make every route-control operation understandable to the owner and diagnosable by ChatGPT/Bridge without exposing physical identity.
6. Fail closed on stale tokens, generation races, project-policy mismatch, malformed return targets, ambiguous cancellation, or persistence failure.
7. Keep ChatGPT browser catalog discovery optional and separate from the correctness of bind/wake routing.

## 4. Non-goals

- Building a general ChatGPT conversation catalog in this phase.
- Keeping Chromium resident to poll ChatGPT.
- Inferring the current conversation from titles, Global Search, marker text, model output, or heuristics.
- Automatically moving a route between Projects without explicit policy authorization.
- Cancelling underlying executor/repository jobs when the user asks only to cancel wake delivery.
- Reworking the ReviewGPT transport beyond the minimum needed to consume the newly bound target.
- Solving the separate Jobs API defect where repository `busy` does not identify the blocking durable job. That becomes an independent bounded change (`job_list(active)` plus blocker metadata on busy responses).

## 5. Core invariants

### 5.1 Physical identity never crosses the LLM boundary

The following values are control-plane secrets/metadata and MUST NOT appear in model-visible tool output, model context, `sendMessage`, `updateModelContext`, continuation prose, or sanitized diagnostics:

- ChatGPT conversation URL;
- conversation ID;
- Project/GPT physical identifier;
- `redirectUrl` or equivalent raw return target;
- one-time bind token or candidate token;
- raw browser target data.

They may exist only in the ChatGPT host, Bridge HTTP control endpoint, strict target parser, RouteRegistry persistence, ReviewGPT transport internals, and short-lived local raw diagnostic storage.

### 5.2 No model-mediated discovery

The production bind path MUST NOT call `sendMessage` or `updateModelContext` to identify a chat. It MUST NOT search for synthetic markers. The LLM may request that a bind UI be shown, but the identity acquisition and commit occur entirely out of band.

### 5.3 Fail closed

A failed operation leaves the previous active route binding unchanged. A bind is committed only after all required checks succeed. An unbind is committed only when its wake-cancellation policy is satisfied.

### 5.4 Route generations remain authoritative

A rebind to a different physical conversation increments route generation and allocates the next generation channel exactly once. Same-target rebind is idempotent and does not create a new generation.

## 6. Architecture

### 6.1 Components

#### Coordinator MCP App

The existing coordinator widget becomes the operator control surface. It renders safe route state and actions, but never receives or displays physical chat identity.

Primary actions:

- `Bind this chat` / `Rebind this chat`;
- `Unbind`;
- `Cancel wake`;
- `Unbind + cancel wakes` for the explicit emergency path.

The widget receives an opaque, short-lived control operation URL from Bridge. On bind, it calls ChatGPT-specific `openExternal` for that URL. It does not use model-visible messages or context updates for route identity.

#### Route-control landing endpoint

The external endpoint accepts the ChatGPT-added `redirectUrl`. The initial GET MUST NOT directly mutate the route. It:

1. validates the opaque operation token and TTL;
2. validates and strictly parses the return target with `parse_chatgpt_target()`;
3. applies expected-route/project/generation preconditions;
4. stores a short-lived server-side candidate keyed by an opaque operation/candidate ID;
5. returns a human-readable status page.

The page performs a same-origin POST to finalize the candidate. This avoids a state-changing GET and reduces exposure to link prefetch/replay. The POST consumes the candidate exactly once and calls the atomic RouteRegistry commit path.

No raw return target is embedded back into page HTML, JavaScript, model-visible state, or diagnostics.

#### RouteRegistry

The existing `prepare_current_bind()` / `complete_current_bind()` semantics are retained and adapted from marker discovery to out-of-band candidate completion.

The registry owns:

- route existence and route ID validation;
- bind operation token lifecycle;
- source-generation guard;
- project identity policy;
- idempotent same-target bind;
- generation increment for changed target;
- atomic persistence;
- bound/unbound state.

An unbound logical route remains registered but is not an eligible wake target. Its active physical target fields are removed from the active binding record. Historical physical targets, if retained for local audit/recovery, are stored outside model-visible route status and are never used as an implicit active target.

#### CoordinatorService / durable wake layer

The coordinator exposes route-scoped cancellation primitives. `cancel wakes` means:

- cancel queued/pending coordinator deliveries for the selected route generation;
- cancel durable job-wake waiters that would later create coordinator wakes for that same route generation;
- do **not** cancel the underlying executor/repository jobs.

Cancellation is idempotent. It returns only sanitized counts and state.

`unbind` fails closed when pending or future-producing wake state still exists. The operator must first cancel wakes or explicitly invoke `unbind + cancel wakes`, which performs both under one guarded control operation.

#### ReviewGPT transport

ReviewGPT continues to receive a strict physical target from the route registry. It does not participate in bind discovery. After a successful new binding, an optional non-sending target probe may verify that the stored target can be located before the UI reports `ready for wake`.

## 7. Bind flow

1. The owner invokes route control for a known logical route.
2. Bridge prepares an opaque bind operation with TTL, expected source generation, route ID, current project policy, and operation ID.
3. The widget displays `Bind this chat` and invokes `openExternal` only after the owner's click.
4. ChatGPT opens the Bridge landing endpoint and appends `redirectUrl` for the exact source conversation.
5. The landing endpoint validates the operation and parses the target strictly.
6. The server records a short-lived candidate; the GET does not mutate route state.
7. The result page automatically submits a same-origin POST to finalize the candidate. If automatic POST is blocked, the page presents an explicit `Complete binding` button.
8. RouteRegistry atomically commits the candidate if token, project policy, and generation still match.
9. Same-target bind returns `already bound`; different target increments generation once.
10. The result page shows a clear success/failure state and an opaque diagnostic operation code.
11. A `Return to ChatGPT` button calls a Bridge redirect endpoint that uses the server-held target; the raw target is not embedded in rendered HTML.

## 8. Status, unbind, and cancellation

### 8.1 Safe status

Model-visible and widget-visible status may include:

- logical route ID/title;
- `bound | unbound | bind_pending | error`;
- generation;
- pending coordinator wake count;
- pending durable wake-waiter count;
- last route-control operation status and safe diagnostic code;
- whether target probe is `ready | degraded | not_checked`.

It MUST NOT include physical chat metadata.

### 8.2 Unbind

`Unbind` disables the physical target for future wake delivery while preserving the logical route and route history. If wake state exists, ordinary unbind returns a guarded `pending_wakes` result and changes nothing.

### 8.3 Cancel wakes

`Cancel wake` cancels current pending coordinator delivery state and future-producing durable wake waiters for the selected route generation. It does not cancel jobs themselves. Completed jobs remain queryable through normal durable job APIs.

### 8.4 Unbind + cancel wakes

This is the explicit recovery action for a stale/wrong binding. The service cancels wake-producing state first, verifies cancellation, then unbinds. Failure at any stage returns a failed operation trace and leaves the binding active unless cancellation was already safely committed; the final status page states the exact resulting safe state.

## 9. Human-readable result page

The external route-control page is an operator UI, not a developer dump.

Success example:

> ✅ **Chat linked**  
> ChatGPT securely identified this conversation and Bridge accepted it for route `bridge`.  
> Generation: 7  
> Pending wake: 0  
> Diagnostic code: `bind-7F3K`  
> `[Return to ChatGPT]`

Failure example:

> ❌ **Chat could not be linked**  
> Failed at: Conversation identification  
> Existing binding was not changed.  
> Diagnostic code: `bind-7F3K`  
> `[Return to ChatGPT]`

The page uses large `✅ / ⚠️ / ❌` status treatment, plain-language stage names, and responsive mobile layout. It never displays raw physical identifiers or tokens.

## 10. Diagnostic trace contract

Every route-control operation receives a random opaque diagnostic ID that is not derived from any chat or route physical identifier.

Sanitized stage names:

1. `widget_external_open`
2. `return_received`
3. `target_parse`
4. `token_check`
5. `project_policy`
6. `generation_guard`
7. `candidate_store`
8. `registry_commit`
9. `wake_cancel`
10. `target_probe`

Each stage records:

- `ok | failed | skipped`;
- timestamp;
- bounded duration;
- stable error code when failed.

Representative safe error codes:

- `RETURN_TARGET_MISSING`
- `TARGET_PARSE_FAILED`
- `TOKEN_INVALID`
- `TOKEN_EXPIRED`
- `TOKEN_REPLAYED`
- `PROJECT_MISMATCH`
- `GENERATION_CHANGED`
- `CANDIDATE_EXPIRED`
- `REGISTRY_WRITE_FAILED`
- `PENDING_WAKES`
- `WAKE_CANCEL_FAILED`
- `TARGET_PROBE_FAILED`

A model-visible diagnostic tool accepts only the opaque diagnostic ID and returns the sanitized trace. It never returns raw physical identity.

A separate raw local trace may contain enough control-plane detail for deep VPS debugging. It has a short TTL (default 24 hours), restricted local access, and is never returned through ordinary MCP/model output. The raw trace is for root-cause investigation only, not routine operation.

## 11. Legacy discovery retirement

The marker/Global-Search current-chat discovery path is not retained as a production fallback.

Retirement is staged:

1. implement out-of-band route control alongside legacy code;
2. pass all live acceptance gates;
3. switch `coordinator_route_bind_current` to the out-of-band path;
4. disable marker emission/search discovery;
5. remove marker-specific UI, transport discovery hooks, tests, and documentation after one bounded stabilization cycle.

If out-of-band acceptance fails on a required platform, the legacy path remains disabled for that platform rather than silently falling back to model-mediated identity discovery.

## 12. Chat catalog relationship

A future ChatGPT catalog may improve recovery, diagnostics, and operator browsing, but it is not part of bind correctness and is not a prerequisite for wake.

If implemented later, catalog refresh follows a cold/on-demand hierarchy:

1. use fresh local cache;
2. perform direct authenticated read when possible;
3. start ephemeral Chromium only when required;
4. refresh, persist cache, terminate Chromium.

No hourly resident-browser polling is permitted merely to maintain chat discovery.

## 13. Acceptance gates

The route-control implementation is not production-complete until all applicable gates pass.

### Offline/contract gates

- strict `parse_chatgpt_target()` tests for ordinary, Project, GPT, malformed, cross-origin, query/fragment, and ambiguous paths;
- RED/GREEN tests for one-time token, TTL, replay, generation race, and project mismatch;
- state-changing GET is prohibited by test; only finalizing POST mutates binding;
- same-target bind idempotency;
- changed-target generation increment exactly once;
- ordinary unbind refuses when wake-producing state exists;
- cancel wakes cancels pending coordinator state and durable job-wake waiters but not underlying jobs;
- unbound routes cannot be selected as wake targets;
- sanitized status/diagnostics contain no physical identity;
- model-visible widget path contains no marker emission or identity-bearing `sendMessage` / `updateModelContext` behavior.

### Live ChatGPT gates

1. ordinary Web conversation bind;
2. Project Web conversation bind;
3. one mobile-client bind;
4. same-conversation repeated bind is idempotent;
5. cross-Project bind without explicit authorization fails closed;
6. expired/replayed bind candidate fails closed;
7. successful bind followed by non-sending ReviewGPT target probe;
8. `unbind + cancel wakes` prevents any later delivery from previously registered durable waiters;
9. result page clearly reports success/failure without requiring developer interpretation.

Only after gates 1-9 pass may legacy marker discovery be disabled and scheduled for removal.

## 14. Migration and compatibility

Existing logical route IDs and route contexts remain authoritative. Existing bound routes are migrated to the new binding-state representation without changing generation or channel. Existing physical targets remain active until explicitly rebound/unbound.

Tool compatibility:

- `coordinator_x_mount` remains for mounting an already bound logical route;
- `coordinator_route_bind_current` retains its public intent but renders the new out-of-band control flow instead of marker discovery;
- manual exceptional takeover may remain as an operator-only recovery mechanism but must not become an ordinary worker path;
- route status and route list return sanitized logical metadata only.

## 15. Implementation boundaries

Implementation must occur in an isolated worktree and must not modify the dirty runtime checkout or the active Fusion CAD Agent worktree.

The temporary 2026-09-04 return-probe code is feasibility evidence, not production code. Production implementation must replace the `/return-probe` debug endpoint, `/tmp` state file, and probe-only button with the guarded route-control flow defined above.

No push, merge, deploy, or live restart is implied by implementation work. Live deployment/restart requires an explicit acceptance step after offline review and verification.

## 16. Separate follow-up: Jobs API observability

During the spike, a second Bridge control-plane defect was reproduced: `run_command` can reject work because a repository is busy, but the normal MCP surface cannot list the active durable job that owns the repository lock.

This must be handled as a separate bounded change, not bundled into route control:

- add `job_list(active)` or equivalent filtered active-job listing;
- include safe blocking job metadata in repository-busy responses;
- never require direct SQLite/state-file inspection merely to identify the blocker.
