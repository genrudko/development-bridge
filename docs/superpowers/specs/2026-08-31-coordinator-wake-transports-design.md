# Coordinator Wake Transports Design

## Context

Development Bridge already has the durable continuation machinery we need: `CoordinatorService` persists `PendingWake` records, continuation IDs, batching, leases, retries, transport ACK state, model ACK state, cooldowns, and escalation. The current delivery path is tightly coupled to Coordinator X / Browser Host. We have now proven a second browser transport (`review-gpt`) that can create a new user turn in the exact current ChatGPT Project conversation from the VPS while the owner PC is off.

The goal is therefore **not** to build a second outbox. The goal is to make delivery pluggable while keeping `CoordinatorService` as the single durable continuation state machine.

## Goals

1. Preserve the current coordinator/job APIs and durable continuation semantics.
2. Add a transport-neutral server-side delivery layer.
3. Make `review-gpt` the first direct transport backend.
4. Keep Coordinator X available as legacy/fallback during migration.
5. Make a future Work / Cloud Browser backend additive rather than architectural rework.
6. Prevent automatic duplicate sends after ambiguous browser failures.
7. Target the exact route conversation UUID and authoritative Project URL.
8. Require an idle/native-not-generating ChatGPT target before direct send.
9. Keep live ChatGPT payloads tiny; durable job/result state remains in Development Bridge.

## Non-goals

- Do not use OpenAI private ChatGPT APIs, `/backend-api`, auth-token replay, or Cloudflare bypass.
- Do not replace `CoordinatorService` persistence with a new database/outbox.
- Do not remove X / Browser Host in this change.
- Do not integrate Work / Cloud Browser before its E2E is proven.
- Do not run repeated live ChatGPT acceptance tests while implementing.

## Architecture

### Existing durable core

`CoordinatorService` remains authoritative for:

- pending continuation creation;
- `continuation_id` identity;
- debounce/batching/deduplication;
- delivery leases and attempt counts;
- transport-delivered state;
- model ACK / observed-turn resolution;
- web cooldown/backoff;
- escalation.

No second continuation queue is introduced.

### New transport boundary

Add a focused coordinator transport module with:

```python
class WakeTransport(Protocol):
    name: str
    async def probe(self, target: WakeTarget) -> WakeProbeResult: ...
    async def deliver(self, request: WakeDeliveryRequest) -> WakeDeliveryResult: ...
```

`WakeTarget` carries route identity only: route ID, channel ID, conversation ID, and authoritative route URL.

`WakeDeliveryRequest` additionally carries the continuation ID, tiny prompt, and deterministic delivery key.

`WakeDeliveryResult.disposition` is one of:

- `delivered`: exact user turn is proven committed;
- `not_submitted`: failure is proven before submission; retry policy may decide later;
- `uncertain`: submission may have happened; **automatic resend is forbidden**;
- `owner_input_required`: browser/login/Cloudflare state requires operator action.

### Delivery service

Add `CoordinatorWakeDeliveryService`, started/stopped from the MCP server lifespan beside `JobService` and `TelegramSupervisorService`.

The service:

1. does nothing when direct delivery is disabled;
2. iterates active routes at a bounded interval;
3. asks `CoordinatorService` for a transport-eligible continuation without requiring Browser Host preflight;
4. resolves the exact route URL/conversation ID;
5. runs the configured primary direct transport;
6. finalizes the existing coordinator claim based on the transport disposition;
7. never auto-resends an `uncertain` delivery;
8. leaves X routes/tools intact.

The dispatcher is deliberately single-process/single-lane in v1. ChatGPT Web is not a high-frequency bus.

## Coordinator state changes

The existing `status()` and `claim()` Browser Host preflight behavior stays the default for X callers.

Add an explicit direct-transport mode used only by `CoordinatorWakeDeliveryService` so a direct transport can claim without the X-specific Browser Host preflight gate while still respecting:

- web backoff;
- global/channel cooldown;
- claim lease;
- attempt limits;
- batching;
- continuation identity.

Add durable failure metadata to `PendingWake` sufficient to fail closed:

- last transport name;
- last transport disposition;
- bounded last transport error/detail;
- owner-input-required flag.

An `uncertain` or `owner_input_required` result blocks further automatic delivery and becomes escalation/diagnostic state instead of silently expiring into another send attempt.

## ReviewGPT transport

### Configuration

The adapter is disabled by default. Enabling it requires explicit configuration for:

- Node executable;
- `review-gpt` CLI path;
- review-gpt config file;
- browser endpoint (expected local CDP endpoint);
- state/receipt directory;
- process timeout.

No spike path is hard-coded as a production default.

Environment overrides are supported through the normal settings loader.

### Probe

Before claiming a send, `ReviewGptWakeTransport.probe()` checks the configured browser endpoint and verifies an exact matching ChatGPT target for the target conversation. It must reject:

- unreachable CDP;
- no exact conversation target;
- Cloudflare / `Just a moment` target;
- logged-out/non-ChatGPT target;
- active native generation / visible Stop control.

A failed probe cannot create a ChatGPT user turn.

### Send

The adapter invokes the public `review-gpt` CLI with argv, never shell interpolation:

- configured `--config`;
- `--chat-url <authoritative route URL>`;
- `--prompt <tiny continuation prompt>`;
- `--no-artifacts` / `--no-zip`;
- `--send`;
- a deterministic `--response-file` path whose `.capture.json` sidecar is retained as the durable committed-turn receipt;
- structured output where available.

The tiny prompt is of the form:

```text
DBRIDGE_CONTINUE <continuation_id>. Call coordinator_ack for this continuation_id, process any batched messages it returns, inspect the durable Bridge job/result state, and continue the current bounded task. <bounded reason>
```

The full job output is never pasted into the wake prompt.

### Idempotency / crash recovery

The continuation ID is the delivery key. Before any send, the adapter checks the deterministic capture sidecar for the same exact conversation and a committed user-turn identity. If such a receipt already proves submission, the adapter returns `delivered` without sending again.

If the CLI exits successfully only after proving the committed user turn, the adapter returns `delivered`.

If the CLI exits non-zero after `--send` and no durable proof establishes a clean pre-submit failure, return `uncertain`; never retry automatically.

Browser endpoint failure or explicit Cloudflare/login evidence detected before the CLI send path returns `owner_input_required`.

## Future Work transport

A future `WorkCloudBrowserWakeTransport` must implement the same `WakeTransport` contract. If Work proves better, configuration changes transport priority only:

```text
primary = work_cloud_browser
fallback = review_gpt
```

Coordinator/job code does not change.

No automatic cross-transport fallback is allowed after an `uncertain` result from the primary transport, because that can duplicate a user turn.

## Error handling

- `delivered` -> mark existing coordinator transport ACK/delivered state and wait for model ACK/observed turn.
- `not_submitted` -> release safely according to bounded retry policy.
- `uncertain` -> persist failure state, block automatic resend, surface escalation.
- `owner_input_required` -> persist failure state, block automatic resend, surface explicit browser/login intervention requirement.

Errors and receipt paths are bounded and sanitized; no prompt text, cookies, tokens, or signed URLs are logged as secrets.

## Testing

All implementation is TDD.

Required offline coverage:

1. existing X behavior remains unchanged by default;
2. direct claim bypasses only Browser Host preflight, not cooldown/backoff/lease rules;
3. uncertain/owner-input states are durable and prevent resend;
4. exact-route target construction uses the registered conversation UUID/Project URL;
5. ReviewGPT probe rejects unreachable/wrong/Cloudflare/generating targets;
6. ReviewGPT adapter uses argv, deterministic receipt path, no artifacts, and exact route URL;
7. an existing valid receipt prevents a second process invocation;
8. dispatcher maps transport results to coordinator state correctly;
9. disabled configuration starts no delivery loop and preserves current behavior;
10. existing coordinator contract/integration tests remain green.

No live ChatGPT send is part of the normal test suite.

## Rollout

1. Land code with direct delivery disabled by default.
2. Configure the already-proven VPS `review-gpt` runtime explicitly.
3. Restart only after offline tests/review are green.
4. Run one deliberate exact-current-chat acceptance E2E.
5. Keep X as fallback during soak.
6. Test Work when healthy; change priority only if it proves better.
