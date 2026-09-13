# Blender Bridge/Hub v1 Design

## Purpose and boundaries

Blender Hub is a thin provider multiplexer, supervisor, and glue layer. It does not port `fusion.cad/v1`, invent a unified Blender API, or move Blender domain knowledge out of upstream providers. One external surface may expose provider tools under namespaces such as `dcc.*`, `research.*`, and `orca.*`.

Task 1 is core-only: durable contracts and testable service primitives. It does not wire public MCP tools, implement a network transport, touch Windows or Blender, add remote shell access, or implement the Print Pipeline.

## Eventual architecture

1. **Provider supervisor.** Tracks independently configured upstream providers and their `online`, `degraded`, or `offline` state, including a provider-local error. A failed provider never makes the catalog or healthy providers unavailable.
2. **MCP multiplexer.** Publishes upstream tools under their configured namespace and rejects duplicate tool names within that namespace. It preserves upstream schemas and metadata instead of synthesizing a Blender-wide semantic API.
3. **Global mutation lock.** Allows reads to overlap while every mutating or conservatively classified call shares one process-wide asynchronous write lock across all providers. Classification is fail-closed: only explicit `readOnly: true` is read-only; missing, false, or malformed hints mean mutation; any `destructive: true` wins a conflict.
4. **Windows↔VPS transport reuse.** Reuses the established authenticated relay pattern in a later task. A dispatched mutating call whose transport is lost returns `UNCERTAIN` and is never replayed. An explicitly idempotent read may reconnect and retry once; a non-idempotent read is not replayed.
5. **Same-turn Operator Chat.** `operator.ask` registers structured prompt data and keeps the same coroutine pending until a thread-safe answer, timeout, or cancellation. Terminal paths remove the pending prompt so late answers are rejected. `operator.notify` records/emits a notification without waiting.
6. **Windows/Blender UI.** A later Windows-side UI will render provider health, pending prompts, notifications, and Blender-facing controls. Task 1 defines only the core data contracts it will consume.
7. **Print Pipeline.** A later block will coordinate provider-native print preparation and verification. It will use namespaced provider tools and the shared mutation/transport/operator contracts; no print behavior is implemented in Task 1.

## Task 1 service boundaries

- `app.blender_hub.catalog`: immutable tool descriptors, fail-closed mutation classification, namespaced registration, per-provider health, and invocation guarded by one catalog-wide write lock.
- `app.blender_hub.operator`: typed prompt/notification models and an in-memory thread-safe same-turn broker. Operation IDs are unique while pending; timeout/cancellation always clean up; stale or duplicate answers return `False`.
- `app.blender_hub.transport`: a generic async dispatch helper whose caller supplies dispatch and reconnect callbacks. The result makes success, ordinary failure, and uncertain mutation outcomes explicit.

Provider adapters remain responsible for executing upstream tools. The catalog accepts async callables and does not know Blender semantics or network details.

## Error and concurrency semantics

Catalog registration is atomic per provider: duplicates in the proposed namespace are rejected before any of that provider's tools are added. Re-registering a provider replaces its prior catalog entries only after validation. Offline/degraded state affects only that provider. Invocation of an unavailable provider fails locally.

Read-only invocations bypass the mutation lock and may overlap each other and an in-flight write. All calls not proven read-only acquire the single global write lock, so writes across namespaces/providers cannot overlap.

Transport retry decisions are made before any replay: mutation never replays and transport loss after dispatch becomes `UNCERTAIN`; an idempotent read gets at most two total dispatch attempts with at most one reconnect; all other calls get one attempt.

## Verification

Focused tests cover catalog duplicates and provider isolation, classification conflicts and unknown metadata, read overlap and global write exclusion, prompt answer/timeout/cancellation/stale-answer behavior, nonblocking notifications, and all replay branches. Task 1 completion additionally requires the closest relevant tests, Python compilation, `git diff --check`, and final Git review.
