# Blender Bridge/Hub v1 Public Relay Design

**Status:** design for the next milestone after the accepted local provider runtime (`23b06d0`).

## 1. Goal

Expose one dedicated remote MCP surface, intended to be connected to ChatGPT as **Blender Bridge**, whose dynamic tools are executed by the Windows-local Blender Hub while preserving the existing outbound-only Development Bridge desktop transport.

The milestone must make the already-accepted local Hub provider runtime remotely usable. It does **not** add the Windows GUI, viewport streaming/picking, provider installers, Print Pipeline orchestration, or live Blender acceptance.

The public surface must preserve the upstream provider schemas and MCP results closely enough that a client sees direct namespaced tools such as `dcc.search`, `dcc.call`, `research.*`, `orca.*`, and 3MF tools rather than one generic `blender_call(name, args)` escape hatch.

## 2. Existing facts and constraints

The accepted local Hub already has:

- `NamespacedToolCatalog` with immutable schema/annotation/publication snapshots;
- one global mutation lock and conservative unknown-as-write classification;
- `ProviderSupervisor` with per-provider lifecycle locks, generation-closed handlers, stale-tool failure, provider isolation, explicit reconnect, and no call replay;
- `OperatorBroker` with same-turn async wait plus cross-thread answer/cancel delivery;
- local MCP provider connectors for loopback HTTP and bounded stdio.

Development Bridge already has:

- `DesktopNodeService` with authenticated outbound `register -> heartbeat -> claim -> result` flow;
- durable operation journal and mutation uncertainty semantics;
- expected desktop `session_generation` validation on synchronous calls;
- bounded result upload/externalization for images, PDFs, archives, 3MF/STEP/STL and other binary payloads;
- the proven Windows relay pattern in `agents/windows_fusion_agent.py`: independent persistent claim/heartbeat/control HTTPS channels, long-poll claims, local MCP execution, result-only retries, and durable local result outbox.

Protocol/runtime facts verified against MCP Python SDK 2.0.0 and the 2026-07-28 MCP specification:

- a low-level `Server` can implement dynamic `tools/list` and `tools/call` handlers;
- the advertised tool set may change over time, but unchanged lists must be deterministic;
- tool-list change notifications are supported, but clients can also relist after reconnect;
- OAuth resource indicators may identify a base resource/API containing multiple endpoints, but this Bridge already audience-binds tokens to an exact MCP resource. The new Blender connector therefore gets its own resource audience rather than silently sharing the primary Bridge token.

## 3. Approaches considered

### A. Add `blender_call(tool_name, arguments)` to the main Development Bridge connector

Smallest implementation, but rejected. It destroys direct tool schemas/annotations, pollutes the infrastructure connector with DCC application tools, makes tool discovery less useful to the model, and defeats the desired `@Blender Bridge` product boundary.

### B. Make the Windows Hub directly reachable from the internet

Rejected. It adds an inbound tunnel/listener and new credential/security surface, duplicates transport/retry/observability already solved by `DesktopNodeService`, and violates the outbound-only design chosen for the project.

### C. Dedicated dynamic MCP surface on VPS backed by the existing outbound desktop relay

**Chosen.** The VPS remains the public OAuth/MCP boundary. Windows initiates all connectivity. The dedicated MCP server publishes the exact registered Hub catalog and dispatches calls through the existing desktop command queue. The main Development Bridge MCP surface remains independent.

## 4. Component architecture

### 4.1 Windows `BlenderHubWorker`

A new Windows-side worker owns one `NamespacedToolCatalog`, one `ProviderSupervisor`, and one `OperatorBroker`.

Responsibilities:

1. connect configured DCC/3MF/Orca/Research providers locally;
2. build the accepted dynamic Hub catalog;
3. add Hub-owned synthetic tools (`operator.ask`, `operator.notify`, and a minimal read-only `hub.status`);
4. register the complete public tool descriptors to the VPS desktop relay;
5. heartbeat independently of provider calls;
6. long-poll claims, invoke **only through `NamespacedToolCatalog.invoke`**, and deliver the exact MCP-shaped result;
7. persist completed-but-undelivered results in the same outbox pattern as the Fusion relay;
8. never replay an upstream tool call after execution has begun.

The worker is a Hub runtime plus outbound relay client. It is not itself a public internet MCP server.

### 4.2 Generic Desktop Node relay contract

`DesktopNodeService` becomes workload-neutral without breaking the existing Fusion agent.

The internal liveness field becomes generic `ready`. The HTTP registration contract accepts:

- `ready: bool` for new agents;
- legacy `fusion_available: bool` as a backward-compatible alias when `ready` is absent.

For Fusion compatibility, `status()` continues to expose `fusion_available` for legacy nodes/callers while also exposing canonical `ready`. A Blender Hub node never sends or depends on `fusion_available=true`.

Registration also carries a bounded `protocol_profile`. Legacy registrations that omit it are treated as `fusion-v1`; the Blender Hub sends `mcp-v1`. `ready` means only that the desktop worker/claim loop can accept commands for its registered public surface; one degraded local provider does not make the whole node unready. Fusion-specific result interpretation (`extract_bridge_cad_result`) remains isolated to `fusion-v1`; `mcp-v1` uses generic MCP result classification and must never run Fusion payload decoding.

Generic command dispatch keeps the existing queue, journal, result uploads, result outbox compatibility, and `session_generation`. To minimize Fusion regression risk, legacy `DesktopNodeService` error text may remain backward-compatible internally; `BlenderRelayService` maps relay failures to bounded generic Blender/Desktop public errors and never exposes Fusion wording on `/blender/mcp`. Existing Fusion-domain service errors remain Fusion-specific above this layer.

The operation journal remains shared. New Blender calls pass an explicit `mutation` bit derived from the registered immutable ToolAnnotations snapshot, so the existing post-claim cancellation/timeout rule remains authoritative:

- claimed mutation -> `uncertain`, never auto-replay;
- unclaimed/non-mutating timeout -> retryable according to the existing relay policy.

### 4.3 VPS `BlenderRelayService`

A small Blender-specific service sits above `DesktopNodeService`. It does not know provider transport details.

It owns:

- configured Blender desktop `node_id`;
- last accepted Hub publication snapshot;
- exact desktop `session_generation` attached to that snapshot;
- a monotonic internal `publication_revision` for every accepted desktop registration;
- a monotonic `surface_revision` that advances only when public tool evidence changes and is used for client relist safety.

It converts the desktop node's registered tool JSON into immutable public MCP descriptors and validates the Hub contract before publication.

The desktop `register` route is the publication integration point for the configured Blender node: after `DesktopNodeService.register` commits a new desktop `session_generation`, the route synchronously asks `BlenderRelayService` to validate/accept that exact generation and tool snapshot before returning registration success to the worker. The old public snapshot may remain visible during validation, but its older expected desktop generation already fails closed at dispatch. A same-surface re-registration still commits the new expected desktop generation and advances internal `publication_revision`; tool evidence may remain byte-for-byte identical while dispatch binding changes, so `surface_revision` does not advance.

A publication is accepted atomically only if every descriptor is bounded and JSON-safe, names are unique, synthetic namespace collisions are impossible, and annotation/schema shapes are valid. Invalid refresh data leaves the previous accepted snapshot visible but **not callable** if its desktop session generation is no longer current.

No provider session/config/secrets cross to the VPS.

### 4.4 Dedicated public Blender MCP server

External endpoint: **`/blender/mcp`**.

The server uses low-level dynamic handlers rather than statically registering Python functions.

`tools/list`:

- reads one immutable `BlenderRelayService` snapshot;
- returns tools ordered lexicographically by qualified name;
- preserves `name`, `title`, `description`, `inputSchema`, `outputSchema`, exact supplied ToolAnnotations, and supported publication metadata (`execution`, `icons`, `_meta`);
- returns the same ordering/evidence for an unchanged revision.

The server tracks the `surface_revision` last observed by each live MCP session when that session executes `tools/list`. `tools/call` is accepted only when the session has listed the current `surface_revision`. If the public surface changed since that session's last list, the call fails pre-dispatch with a bounded `catalog_changed_relist_required` error; it never resolves the same tool name against silently changed schemas/semantics. A desktop re-registration that changes only dispatch generation, while tool evidence is identical, updates the internal dispatch binding but does not require a client relist.

`tools/call`:

1. resolves the qualified name in the currently accepted snapshot;
2. takes its snapshotted mutation classification and expected desktop `session_generation`;
3. calls `DesktopNodeService.call(..., expected_session_generation=...)` with explicit operation journal metadata;
4. returns the Hub's MCP result without semantic rewriting;
5. never automatically reconnects or replays on session change, timeout, disconnect, or uncertain mutation.

The main Development Bridge `tools/list` never includes Blender provider tools.

## 5. Tool descriptor and result wire contract

### 5.1 Registration descriptor

Each Hub-public tool registration contains only public JSON evidence:

- `name` (already qualified, e.g. `dcc.call`);
- `title` / `description`;
- `inputSchema`;
- optional `outputSchema`;
- exact `annotations` aliases supplied by upstream/Hub;
- supported publication metadata (`execution`, `icons`, `_meta`).

The VPS recomputes `mutating` from exact annotations with the same conservative rule as the Hub. A claimed `mutating` boolean sent by Windows is not trusted as authority.

Synthetic Hub tools use owned schemas/annotations and are included in the same immutable registration snapshot.

### 5.2 Result preservation

For inline results, the Windows worker sends the JSON-mode MCP `CallToolResult`/`InputRequiredResult` shape. `isError=true` is a normal MCP result and is not converted into transport failure.

For oversized or binary-bearing results, the existing desktop result-upload path externalizes the payload. The Blender public result adapter rehydrates MCP content where possible and adds `ResourceLink` blocks for Bridge-owned extracted resources/exports. It must preserve:

- text/image/audio/resource/resource-link content types supported by the installed SDK;
- `structuredContent`;
- `isError`;
- `resultType`;
- `_meta` after applying the existing public-safe/size rules.

The adapter must not apply Fusion-specific error decoding.

For `protocol_profile=mcp-v1`, `DesktopNodeService.submit_result` must classify/store the MCP envelope generically and bypass `extract_bridge_cad_result`. The legacy `fusion-v1` profile retains existing Fusion classification behavior so this milestone does not regress Fusion semantics.

## 6. Same-turn operator tools

### `operator.ask`

Input contains bounded:

- `operation_id`;
- `question`;
- optional `choices`;
- optional JSON-safe `context`;
- optional timeout capped by Hub policy (v1 target: 300 seconds).

The Windows worker calls `OperatorBroker.ask`. The local GUI/palette (implemented in a later GUI milestone) will read `pending_prompts()` and call `submit_answer`/`cancel` from its UI thread.

The remote MCP `tools/call` stays pending during the operator wait. The independent heartbeat/control channels remain alive, so waiting for the human does not make the desktop node appear offline.

Without a GUI consumer, the call may time out cleanly; the relay must not invent an answer.

Timeouts have an explicit margin: v1 keeps the operator wait cap at **300 seconds**, adds a Blender public desktop-call timeout of **360 seconds**, and expands only the allowed `DesktopNodeSettings.call_timeout_seconds` ceiling enough to permit that bounded override (target ceiling 600 seconds) while leaving the existing Fusion default unchanged. `DesktopNodeService.call` accepts a bounded per-call timeout override; the Blender relay uses 360 seconds and Fusion callers continue using the configured default. The worker heartbeat is a separate task/channel and is not inside the claimed-call await. Tests must prove a 300-second-equivalent blocked fake ask cannot hit the relay deadline first.

### `operator.notify`

Queues one bounded `OperatorNotification` locally and returns immediately. It never blocks a provider call.

This milestone implements the tool/runtime contracts and a fake UI test consumer; the polished Windows Palette is not included.

## 7. Generation and stale-publication safety

There are two independent generations and neither substitutes for the other:

1. **Hub provider/publication generation** closes over local provider handlers and is already enforced by `ProviderSupervisor`.
2. **Desktop node `session_generation`** identifies the currently registered Windows worker instance/catalog at the VPS relay.

Every accepted VPS catalog snapshot records the exact desktop session generation. Every remote call passes that value back into `DesktopNodeService.call(expected_session_generation=...)` before command enqueue.

Pre-enqueue validation is necessary but not sufficient. Every `PendingCommand` is stamped with the desktop `session_generation` that owned the publication at enqueue time, and `claim` refuses to execute a queued command whose stamped generation no longer equals the current node generation. Such an unclaimed stale command is completed as a retryable pre-dispatch `session_changed` result and is never handed to Windows. The claim payload also carries that generation; the worker compares it with the generation returned by its last successful registration before invoking the local catalog.

The worker serializes public-surface replacement/re-registration against command execution with one worker publication lock: provider refresh/reconnect may be staged, but a new public registration is committed only between claimed commands. A claimed command remains bound to the local catalog generation it started with; no mid-call re-registration redirects it to replacement handlers.

If Windows re-registers/restarts or its registered tool set changes first, an old remote tool descriptor cannot silently execute against the new runtime. The call fails pre-dispatch as session-changed; no command is claimed and no replay occurs.

The worker re-registers the whole catalog atomically whenever its accepted local public surface changes. Heartbeats may report unchanged tools without forcing generation churn.

## 8. Tool-list change notifications

V1 correctness does **not** depend on push notification delivery.

The dedicated server advertises tool-list changes only once an in-process notification broadcaster is proven to notify every live Blender MCP session after a new `surface_revision` is committed. Until then:

- `tools/list` is always dynamic and deterministic;
- reconnect/re-initialize sees the current list;
- no false `tools_changed` capability is advertised for the Blender server.

Because push notifications are not guaranteed in v1, the per-MCP-session `tools/list` revision check in §4.4 is the fail-closed stale-client mechanism. A stale client must relist before any changed surface can be called.

This avoids claiming a notification guarantee that the cross-process Windows registration path cannot yet prove. A small follow-up may add subscriptions/listen/list-changed once session fan-out semantics are tested.

## 9. OAuth and connector isolation

The primary Development Bridge protected resource and Blender Bridge are distinct audiences:

- primary: existing `https://<host>/mcp`, scope `bridge`;
- Blender: `https://<host>/blender/mcp`, scope `blender`.

There remains one embedded OAuth issuer and one durable OAuth store/owner approval flow. The authorization provider is generalized from one accepted resource to a bounded configured resource-policy mapping. Authorization codes, access tokens, and refresh-token families preserve the requested resource exactly.

A new `ResourceBoundTokenVerifier(expected_resource)` wraps the shared provider/store and rejects a valid token whose stored resource is not the endpoint's exact resource. Therefore:

- a `bridge` token cannot call Blender tools;
- a `blender` token cannot call Git/jobs/coordinator tools;
- refresh cannot switch resource families;
- token endpoint validates that requested scopes are allowed for the requested resource.

The root authorization-server routes are created only once. The Blender MCP child app uses the same issuer but only its resource-bound verifier; it does not create a second authorization server.

Authorization-server metadata/DCR advertise the bounded union of configured scopes (`bridge`, plus `blender` only when the Blender surface is enabled). Authorization validates that the requested resource exists and that every requested scope belongs to that resource; token and refresh exchange preserve the same resource family. `BridgeOAuthProvider.load_access_token` may validate tokens against the configured resource policy set, but each MCP resource is guarded by a verifier that additionally requires exact stored-resource equality and the endpoint's required scope.

RFC 9728 protected-resource metadata for `/blender/mcp` is exposed at the correct host-level well-known path for that resource. The child MCP app's mount must not create a misleading nested well-known URL.

With MCP SDK 2.0.0 this requires deliberate route composition: passing `resource_server_url` to a mounted child `streamable_http_app` would otherwise generate its protected-resource route relative to the mount. The implementation must either suppress/remove that generated child metadata route while keeping the correct `WWW-Authenticate` metadata URL, or build the authenticated child route explicitly from the SDK middleware. The externally reachable metadata route is exactly `/.well-known/oauth-protected-resource/blender/mcp`; tests assert there is no `/blender/.well-known/...` duplicate.

DCR compatibility remains for the current Bridge; no new dependency on DCR is introduced. Migration to CIMD is outside this milestone.

## 10. ASGI composition

`create_streamable_http_app` remains the single external Starlette application.

The dedicated Blender MCP server is created as a child Streamable HTTP app and mounted before the main-app fallback under `/blender`, producing the external MCP URL `/blender/mcp`. The parent main-auth middleware may see a Blender bearer token as anonymous, but must not reject it; the child resource-bound auth middleware performs the Blender audience/scope check.

The root app owns the correct protected-resource metadata route for the Blender resource before mounts are evaluated. Tests must prove routing/auth behavior rather than relying on middleware assumptions.

The main MCP server and Blender MCP server own separate MCP session managers and capability advertisements.

A Starlette `Mount` does **not** run the mounted child's lifespan. Therefore the top-level Bridge app explicitly composes the existing main MCP app lifespan and the Blender child app lifespan (including both Streamable HTTP session managers) with deterministic startup and reverse-order shutdown. Merely adding `Mount('/blender', child_app)` without entering the child lifespan is forbidden and has a regression test. Lifecycle composition must not duplicate the authorization-server routes or start either session manager twice.

## 11. Windows worker transport behavior

Reuse the proven Fusion relay lifecycle, but do not import Fusion domain code into Blender Hub.

The new agent module should factor/reuse only generic donor pieces where doing so does not destabilize Fusion:

- persistent HTTPS channel/client;
- result outbox;
- bounded result upload/delivery;
- heartbeat/re-register loop.

If extracting these donors would cause broad Fusion churn, v1 may add a small generic desktop-agent module and leave `windows_fusion_agent.py` as a compatibility wrapper in a later refactor. Duplicating unsafe retry/replay logic is not acceptable.

Worker execution sequence:

1. initialize local Hub/providers;
2. build synthetic tools and accepted catalog;
3. register `ready=true`, tool descriptors, and bounded Hub status telemetry;
4. flush result outbox before claiming new commands;
5. start independent heartbeat;
6. claim one command;
7. verify the claim's stamped desktop `session_generation` equals the worker's last accepted registration generation and that the registered local publication revision is still current; otherwise return a bounded pre-dispatch stale result without entering `catalog.invoke`;
8. validate the claimed tool still exists in the exact local public surface expected by the current registration;
9. invoke through `catalog.invoke`;
10. persist result locally before attempting delivery;
11. retry delivery only;
12. on local provider/session failure, refresh registration/status only after the claimed call reaches a terminal local outcome, and never replay the claimed call.

Only one claimed command executes at a time in v1. Provider-level read concurrency remains available *inside* future worker scheduling, but remote claim concurrency is intentionally one to keep mutation ordering and same-turn operator interaction deterministic.

## 12. Failure semantics

- **Windows node offline:** public call fails retryably before enqueue.
- **Desktop session changed:** fail pre-dispatch; caller may relist/retry explicitly.
- **Desktop session changes after enqueue but before claim:** the generation-stamped queued command is terminalized as pre-dispatch `session_changed`; Windows never receives it.
- **Client listed an older changed public surface:** fail pre-dispatch with `catalog_changed_relist_required`; no name-based fallback to the new descriptor.
- **Tool removed/stale:** fail pre-dispatch; no fallback by name/alias.
- **Call timed out before claim:** existing non-executed semantics apply.
- **Claimed read timed out/cancelled:** interrupted/timed-out; never automatically replayed by this layer.
- **Claimed mutation timed out/cancelled/disconnected:** `uncertain`; never replayed.
- **Hub returns `isError=true`:** return that MCP result normally.
- **Result delivery fails after execution:** retain local outbox and stop new claims until delivery is accepted or proven stale; retry result delivery only.
- **Provider degrades:** only that provider's local catalog status changes; subsequent Hub registration publishes the accepted surface/status according to existing supervisor rules.
- **Bad registration payload:** VPS rejects the new snapshot atomically and exposes no partially updated catalog.
- **OAuth resource/scope mismatch:** 401/invalid_target; never broaden audience.

## 13. Settings and public contracts

Add bounded `BlenderBridgeSettings` under `BridgeSettings`, disabled by default. Minimum fields:

- `enabled: bool = False`;
- `node_id: str = "blender-hub"`;
- `mount_path: str = "/blender"`;
- `mcp_path: str = "/mcp"`;
- derived/validated external resource URL when OAuth is enabled;
- operator ask timeout cap;
- Blender public desktop-call timeout (default 360s) with an invariant that it exceeds the operator ask cap by a bounded safety margin;
- bounded registration/tool/result limits should reuse DesktopNode settings unless a proven separate limit is needed.

Do not put provider commands, executable paths, or provider secrets in VPS Blender settings; provider configuration remains Windows-local.

Windows Hub provider configuration stays in the local Hub runtime config established by the provider-runtime milestone.

## 14. Testing strategy

All implementation follows strict RED -> GREEN -> adversarial review.

### Desktop relay compatibility

- current Fusion desktop-node tests remain green unchanged where possible;
- legacy `fusion_available` registration still works;
- new `ready` registration never needs the Fusion field;
- session generation changes on true registration/surface change and does not churn on identical heartbeat;
- mutation uncertainty and result outbox semantics remain unchanged.
- queued commands are generation-stamped and cannot cross a desktop re-registration boundary;
- `fusion-v1` retains existing Fusion result classification while `mcp-v1` bypasses Fusion decoding.

### Dynamic public server

- exact deterministic `tools/list` from fake Hub registration;
- exact schema/annotation/publication preservation;
- mutation classification recomputed on VPS;
- stale desktop generation fails before claim;
- removed tool does not alias/fallback;
- `isError`, structured content, result type, `_meta`, images and external resources survive round trip;
- no Blender tools appear on the main Development Bridge server.
- an MCP session that listed an older changed surface cannot call until it relists; unchanged tool evidence with only a new desktop dispatch generation remains callable without a schema relist;
- mounted Blender Streamable HTTP session-manager lifespan is explicitly entered and closed exactly once.

### OAuth isolation

- authorization accepts exactly configured main/Blender resources and their scopes;
- cross-resource or cross-scope requests fail;
- refresh keeps original resource;
- main token fails Blender endpoint and Blender token fails main endpoint;
- root protected-resource metadata path for `/blender/mcp` is correct;
- no nested `/blender/.well-known/oauth-protected-resource/...` metadata route is exposed;
- authorization routes exist once, not once per child server.

### Worker

Use fake local providers and fake Bridge HTTP channels only: no Blender, Orca, subprocess, DNS, or internet.

Prove:

- register/heartbeat/claim/result order;
- independent heartbeat continues during blocked `operator.ask`;
- exact one-at-a-time claim execution;
- every claimed tool invokes `NamespacedToolCatalog.invoke`;
- outbox blocks new claims until result delivery recovers;
- no command replay after any ambiguous failure;
- catalog refresh causes full atomic re-registration;
- explicit result-delivery retry does not re-enter provider handler.

### Final gate

Run focused Blender Hub + desktop-node + OAuth/transport tests, then full `tests/unit`, compileall, `git diff --check`, and an independent architecture/code review. No live provider/Windows action in this milestone.

## 15. Non-goals

Explicitly deferred:

- polished Windows Palette/GUI and startup installer;
- viewport screenshot/stream/pick UX;
- Print Pipeline orchestration and slicer profile selection;
- automatic provider installation/update;
- direct inbound Windows connectivity;
- arbitrary shell/file-system execution surface;
- automatic call retry/replay;
- MCP Tasks extension integration;
- guaranteed live tool-list push notifications;
- merging/pushing/deploying or live Blender acceptance.

## 16. Acceptance criteria

The milestone is accepted when, entirely in offline/fake tests:

1. a fake Windows Blender Hub can register a dynamic namespaced catalog through the existing outbound desktop route;
2. a dedicated authenticated `/blender/mcp` server lists that catalog with exact evidence and calls it through the desktop queue;
3. calls are pinned to the exact desktop session generation and stale publication cannot reach a replacement Hub;
4. mutating/unknown tools keep single-lane uncertainty/no-replay safety;
5. `operator.ask` can keep the same tool call pending while heartbeat remains healthy and a local fake UI answers it;
5a. the 300-second operator cap is strictly inside the Blender relay's 360-second desktop-call budget;
5b. a command queued under an old desktop generation can never be claimed by a replacement Hub;
5c. a live MCP session cannot silently call a changed tool surface without relisting;
6. MCP result structure/binary resources survive the relay without Fusion-specific rewriting;
7. OAuth audiences/scopes isolate Blender Bridge from the primary Development Bridge connector;
8. all existing Fusion and full-unit regressions remain green;
9. no new inbound Windows transport, public shell, provider secret leakage, auto replay, GUI, or Print Pipeline code is introduced.
