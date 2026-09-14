# Blender Bridge/Hub v1 Public Relay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the accepted Windows-local Blender Hub catalog as one dedicated authenticated `/blender/mcp` connector through the existing outbound Desktop Node relay, with exact dynamic tool evidence, generation-safe dispatch, same-turn operator prompts, and zero automatic call replay.

**Architecture:** Generalize the existing Desktop Node command transport just enough to support an `mcp-v1` node profile while preserving legacy Fusion behavior, then add a VPS `BlenderRelayService` and dynamic MCP server. The public Blender endpoint uses a distinct OAuth resource/scope but the same issuer/store, and the Windows worker reuses the proven outbound register/heartbeat/claim/result + result-outbox lifecycle. The main Development Bridge tool surface remains unchanged.

**Tech Stack:** Python 3.12, asyncio, dataclasses, MCP Python SDK 2.0.0, Starlette, Pydantic v2, http.client outbound Windows transport, pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-09-13-blender-bridge-public-relay-design.md`

## Global Constraints

- No inbound Windows listener/tunnel, public shell, arbitrary file-system execution surface, provider downloader/installer, GUI/Palette implementation, viewport UX, Print Pipeline, slicer orchestration, live Blender/Orca/provider action, push/merge/deploy, or automatic tool-call replay.
- Windows provider processes/endpoints/configuration remain local. No provider executable path, environment secret, session object, or raw exception crosses to VPS.
- Preserve current Fusion behavior. Legacy desktop registrations that omit `protocol_profile` remain `fusion-v1`; the Blender worker uses `mcp-v1` and never executes `extract_bridge_cad_result`.
- Every Blender upstream call still enters through `NamespacedToolCatalog.invoke`; the public relay must not bypass local provider generation locks or the catalog-wide mutation lock.
- Unknown/missing ToolAnnotations remain conservatively mutating. VPS recomputes mutation classification from exact registered annotation evidence and does not trust a Windows-supplied boolean.
- A command is bound to the exact desktop `session_generation` at enqueue and again at claim. Re-register/restart must never redirect an old queued command into a replacement Hub.
- A live MCP session that listed an older changed `surface_revision` must relist before `tools/call`. A same-surface desktop re-registration updates dispatch generation without forcing a schema relist.
- `operator.ask` may wait up to 300 seconds; Blender desktop calls use 360 seconds, with the existing Fusion default unchanged and a bounded Desktop Node ceiling of 600 seconds.
- `tools_changed` is not advertised for the Blender server in this milestone.
- Root OAuth authorization routes are created once. Main Bridge resource is exact `/mcp` + `bridge`; Blender resource is exact `/blender/mcp` + `blender`.
- Mounted Blender MCP session-manager lifespan must be entered explicitly; Starlette `Mount` alone is not sufficient.
- Result-delivery retries are allowed; upstream/provider tool execution retries are not.
- Use the shared environment explicitly:

```bash
PYTHON=/home/eodadmin/codex-workspace/development-bridge/.venv/bin/python
PYTEST=/home/eodadmin/codex-workspace/development-bridge/.venv/bin/pytest
WORKTREE=/home/eodadmin/.local/state/development-bridge/worktrees/blender-bridge-hub-v1
```

---

### Task 1: Generalize Desktop Node protocol without regressing Fusion

**Files:**
- Modify: `app/desktop_nodes/service.py`
- Modify: `app/transport.py`
- Modify: `app/settings.py`
- Modify: `tests/unit/test_desktop_nodes.py`
- Modify: `tests/unit/test_desktop_node_journal.py`
- Modify: `tests/integration/test_desktop_node_routes.py`
- Modify only as required by compatibility: `tests/unit/test_windows_fusion_agent.py`

**Interfaces:**
- Produce `DesktopProtocolProfile(str, Enum)` with `FUSION_V1 = "fusion-v1"` and `MCP_V1 = "mcp-v1"`.
- `NodeState` stores canonical `ready: bool`, `protocol_profile: DesktopProtocolProfile`, and existing `session_generation`.
- `PendingCommand` gains immutable-at-enqueue `session_generation: int`.
- Preserve legacy calls while extending `DesktopNodeService.register(..., fusion_available: bool | None = None, telemetry=None, *, ready: bool | None = None, protocol_profile: str | DesktopProtocolProfile | None = None)` and the matching `heartbeat` semantics.
- Extend `DesktopNodeService.call(..., expected_session_generation: int | None = None, timeout_seconds: float | None = None)`; default uses existing `settings.call_timeout_seconds`, Blender later passes 360.
- `claim()` includes `session_generation` in every claimed command.
- `status()` includes `ready` and `protocol_profile`; legacy `fusion_available` remains compatible for `fusion-v1`.

- [ ] **Step 1: Write RED tests for registration/profile compatibility.** Add exact tests for legacy `fusion_available=True`, new `ready=True, protocol_profile="mcp-v1"`, invalid/mismatched dual flags, unknown profiles, strict booleans, unchanged heartbeat not bumping generation, and changed readiness/tools bumping it. Example:

```python
@pytest.mark.asyncio
async def test_mcp_profile_registers_ready_without_fusion_alias(desktop):
    status = await desktop.register(
        "blender-hub", [{"name": "dcc.search"}], None,
        ready=True, protocol_profile="mcp-v1",
    )
    assert status["ready"] is True
    assert status["protocol_profile"] == "mcp-v1"
    assert status["fusion_available"] is False
```

- [ ] **Step 2: Run the registration RED slice.**

```bash
$PYTEST -q tests/unit/test_desktop_nodes.py -k 'ready or profile or fusion_available'
```

Expected: failures for missing generic fields/signatures, with existing legacy tests still collected.

- [ ] **Step 3: Implement the minimal profile/readiness model.** Keep `_MUTATING_TOOLS` only as the legacy Fusion default. Resolve registration input with a pure helper: legacy field only -> `fusion-v1`; `mcp-v1` requires explicit `ready`; conflicting readiness inputs fail before state mutation. Do not broaden accepted profile strings.

```python
class DesktopProtocolProfile(str, Enum):
    FUSION_V1 = "fusion-v1"
    MCP_V1 = "mcp-v1"
```

- [ ] **Step 4: Write RED tests for generation-stamped queue safety.** Enqueue at generation G, re-register to G+1 before claim, then assert the command never reaches a claimant, its waiting synchronous call receives retryable `DESKTOP_NODE_OFFLINE` details with `status="session_changed"`, and mutation handler/upstream counters remain zero. Repeat for heartbeat-driven generation change. Assert a command enqueued and claimed at the same generation includes G in its claim payload.

```python
assert claimed["session_generation"] == service.get_session_generation("blender-hub")
```

- [ ] **Step 5: Implement generation ownership.** Stamp `PendingCommand` at enqueue. On generation advance, fail/cancel only unclaimed commands from older generations under `_condition`; leave already claimed commands owned by their original execution and preserve current timeout/uncertainty handling. Add a defensive stale-generation check inside `claim` so no stale queued item is ever returned even if future mutation code misses proactive invalidation.

- [ ] **Step 6: Write RED tests for bounded per-call timeout.** Prove the default still uses existing settings; an explicit 360-second override is accepted when the configured ceiling permits it; nonpositive/nonfinite/over-ceiling overrides fail pre-enqueue; cancellation and claimed mutation uncertainty remain unchanged.

- [ ] **Step 7: Raise only the allowed settings ceiling and implement timeout override.** Change the `DesktopNodeSettings.call_timeout_seconds` field maximum from 300 to 600 while keeping its default at 300. `call(timeout_seconds=...)` uses the explicit bounded value without mutating global settings.

- [ ] **Step 8: Write RED tests for protocol-specific result classification.** Feed a valid ordinary MCP `CallToolResult` envelope containing text that resembles a Fusion failure and prove `mcp-v1` uses only generic top-level MCP/error classification. Feed the existing strict `BRIDGE_CAD_RESULT_V1` fixture through `fusion-v1` and prove current uncertain/failure behavior is unchanged.

- [ ] **Step 9: Implement profile-specific result classification.** `fusion-v1` retains `extract_bridge_cad_result`; `mcp-v1` bypasses it and treats `isError=true` as a failed journal outcome while retaining the exact result payload. Keep late-result/result-outbox logic unchanged.

- [ ] **Step 10: Extend the desktop HTTP route RED/GREEN.** `register` and `heartbeat` accept strict `ready`/`protocol_profile` fields while preserving old Fusion bodies. No Blender-specific service is wired in this task. Test 400 on malformed combinations and unchanged Fusion route behavior.

- [ ] **Step 11: Focused regression gate and commit.**

```bash
$PYTEST -q tests/unit/test_desktop_nodes.py tests/unit/test_desktop_node_journal.py tests/integration/test_desktop_node_routes.py tests/unit/test_windows_fusion_agent.py
$PYTHON -m compileall -q app/desktop_nodes app/transport.py app/settings.py tests/unit/test_desktop_nodes.py tests/unit/test_desktop_node_journal.py tests/integration/test_desktop_node_routes.py
git -C "$WORKTREE" diff --check
git -C "$WORKTREE" status --short
```

Commit:

```bash
git add app/desktop_nodes/service.py app/transport.py app/settings.py tests/unit/test_desktop_nodes.py tests/unit/test_desktop_node_journal.py tests/integration/test_desktop_node_routes.py tests/unit/test_windows_fusion_agent.py
git commit -m "feat(desktop-nodes): add generic MCP relay protocol"
```

---

### Task 2: Add immutable Blender relay publication and dynamic MCP handlers

**Files:**
- Create: `app/blender_relay/__init__.py`
- Create: `app/blender_relay/models.py`
- Create: `app/blender_relay/service.py`
- Create: `app/blender_relay/server.py`
- Modify: `app/settings.py`
- Modify: `app/container.py`
- Modify: `app/transport.py`
- Create: `tests/unit/test_blender_relay.py`
- Create: `tests/unit/test_blender_relay_server.py`
- Modify: `tests/integration/test_desktop_node_routes.py`

**Interfaces:**
- Produce frozen `BlenderToolDescriptor(name, title, description, input_schema, output_schema, annotations, publication_metadata, mutating)` with defensive JSON snapshots.
- Produce frozen `BlenderPublication(publication_revision: int, surface_revision: int, session_generation: int, tools: tuple[BlenderToolDescriptor, ...])`.
- Produce `BlenderRelayService(settings, desktop_nodes)` with synchronous `accept_registration(node_id, session_generation, protocol_profile, tools) -> BlenderPublication`, `snapshot() -> BlenderPublication`, and async `invoke(name, arguments) -> dict[str, object]`.
- Produce `BlenderBridgeSettings(enabled=False, node_id="blender-hub", mount_path="/blender", mcp_path="/mcp", operator_ask_timeout_seconds=300, call_timeout_seconds=360)` with path/timeout invariants from the spec.
- Produce `create_blender_server(relay: BlenderRelayService) -> Server` with plain MCP `Server` capability defaults: no `tools_changed` advertisement.

- [ ] **Step 1: Write descriptor/publication RED tests.** Register exact nested schemas, ToolAnnotations, execution/icons/`_meta`; mutate caller-owned inputs; prove snapshot evidence is immutable, sorted by qualified name, and mutation is recomputed with `app.blender_hub.catalog.is_mutating`. Reject duplicate/unnamespaced/overlong names, non-object schemas/annotations, unsupported profile, wrong node id, synthetic `operator`/`hub` namespace collision, non-JSON values, and oversized total registration evidence.

- [ ] **Step 2: Implement immutable descriptors and atomic acceptance.** Validate the complete candidate before assigning any relay field. Every accepted desktop registration advances `publication_revision`; compare canonical public tool evidence to decide whether `surface_revision` advances. Same evidence + new desktop generation keeps the same `surface_revision` but updates `session_generation` atomically.

- [ ] **Step 3: Wire Blender registration into the HTTP route with RED first.** For the configured Blender node only, `desktop.register` commits its generation, then `BlenderRelayService.accept_registration(...)` validates that exact generation before HTTP success. On relay validation failure return bounded 400/409, keep no partial new Blender publication, and prove the previous snapshot's old generation cannot dispatch.

```python
status = await desktop.register(...)
publication = blender.accept_registration(
    node_id, status["session_generation"], status["protocol_profile"], body["tools"]
)
```

- [ ] **Step 4: Write dynamic `tools/list` RED tests.** Instantiate the low-level Blender server with a fake relay publication and assert exact MCP `Tool` JSON aliases: `inputSchema`, optional `outputSchema`, only supplied annotation hints, `execution`, `icons`, `_meta`, deterministic lexical ordering, and no static Development Bridge tools.

- [ ] **Step 5: Implement `create_blender_server`.** Use plain `mcp.server.Server`, dynamic `tools/list` and `tools/call` handlers, and no `DevelopmentBridgeServer` subclass. Do not advertise tool-list change support.

- [ ] **Step 6: Add per-session stale-surface RED tests.** On `tools/list`, record the publication `surface_revision` against the concrete server session using weak ownership so closed sessions do not leak. Change public tool evidence, then call from the old session and require a bounded `catalog_changed_relist_required` result with zero Desktop Node calls. Relist and prove the call may proceed. Change only desktop dispatch generation with identical evidence and prove no relist is required.

- [ ] **Step 7: Implement fail-closed session revision tracking.** Prefer `weakref.WeakKeyDictionary` keyed by the SDK server-session object; the integration test must prove the installed MCP 2.0.0 session type is weak-referenceable. If it is not, use a bounded session-id map with explicit lifecycle cleanup in the server lifespan; do not use an unbounded `id(session)` dictionary.

- [ ] **Step 8: Write result-adapter RED tests with real MCP models.** Round-trip real `CallToolResult` and `InputRequiredResult`: content blocks, `structuredContent`, `isError`, `resultType`, and `_meta`. For an external desktop result, use real `DesktopNodeService.external_result` metadata and assert Bridge-owned `ResourceLink` blocks are added without Fusion decoding. `isError=true` remains a normal MCP return.

- [ ] **Step 9: Implement generic result parsing.** Validate JSON with a Pydantic `TypeAdapter` over the installed MCP result types outside transport-failure catches. Inline payloads reconstruct the matching MCP result; external payloads load the retained raw result then attach bounded Bridge-owned links. Any malformed Windows MCP envelope becomes a sanitized public relay error, not a raw traceback.

- [ ] **Step 10: Container/settings integration and gate.** Build `BlenderRelayService` only when enabled, otherwise preserve current container behavior. Run:

```bash
$PYTEST -q tests/unit/test_blender_relay.py tests/unit/test_blender_relay_server.py tests/integration/test_desktop_node_routes.py tests/unit/test_settings.py
$PYTHON -m compileall -q app/blender_relay app/container.py app/settings.py app/transport.py tests/unit/test_blender_relay.py tests/unit/test_blender_relay_server.py
git -C "$WORKTREE" diff --check
```

Commit:

```bash
git add app/blender_relay app/settings.py app/container.py app/transport.py tests/unit/test_blender_relay.py tests/unit/test_blender_relay_server.py tests/integration/test_desktop_node_routes.py tests/unit/test_settings.py
git commit -m "feat(blender-relay): publish dynamic Blender tools"
```

---

### Task 3: Isolate Blender OAuth resource and mount the second MCP session manager

**Files:**
- Modify: `app/auth/provider.py`
- Modify: `app/auth/routes.py`
- Modify: `app/settings.py`
- Modify: `app/container.py`
- Modify: `app/transport.py`
- Modify: `app/blender_relay/server.py`
- Modify: `tests/unit/test_settings.py`
- Modify: existing OAuth provider/route unit tests located under `tests/unit/`
- Modify: `tests/integration/test_mcp_oauth.py`
- Create: `tests/integration/test_mcp_blender_relay.py`

**Interfaces:**
- Produce immutable `OAuthResourcePolicy(resource: str, scopes: frozenset[str])` or an equivalent bounded mapping owned by `BridgeOAuthProvider`.
- Generalize `BridgeOAuthProvider` from one `resource_url` to exact configured resource policies while preserving current main-resource behavior.
- Produce `ResourceBoundTokenVerifier(provider, expected_resource)` whose `verify_token` returns a token only when its stored resource exactly equals the endpoint resource.
- Root issuer supports `{main_resource: {"bridge"}, blender_resource: {"blender"}}` when Blender is enabled.
- Blender external protected resource is exactly `<public_base>/blender/mcp`; metadata URL is exactly `/.well-known/oauth-protected-resource/blender/mcp`.

- [ ] **Step 1: Write multi-resource provider RED tests.** Authorization accepts exact known resource + allowed scopes, rejects unknown resource/cross-scope requests, authorization codes preserve resource, token exchange cannot switch it, refresh stays in the same family, and access-token lookup never accepts a token for a resource absent from policy.

- [ ] **Step 2: Implement bounded resource policies.** Replace direct single-resource comparisons with one pure policy lookup. Keep current main-only configuration behavior byte-for-byte compatible when Blender is disabled. Authorization-server metadata/DCR advertise the union of enabled scopes; endpoint `required_scopes` remain separate.

- [ ] **Step 3: Write exact-resource verifier RED tests.** A valid `bridge` token is rejected by a Blender verifier and vice versa; expiry and current provider revocation semantics remain unchanged. Implement `ResourceBoundTokenVerifier` without copying token objects or weakening scope checks.

- [ ] **Step 4: Write protected-resource metadata RED tests.** With Blender enabled, assert:

```text
/.well-known/oauth-protected-resource/mcp
/.well-known/oauth-protected-resource/blender/mcp
```

exist at the root and advertise the correct resource/issuer/scope. Assert `/blender/.well-known/oauth-protected-resource/...` is 404. Assert authorization-server/DCR/token/revoke routes exist exactly once.

- [ ] **Step 5: Implement authenticated child app composition.** Create the child Streamable HTTP app with the Blender resource-bound verifier and `required_scopes=["blender"]`. Prevent the SDK-generated child protected-resource metadata route from becoming externally visible under the mount; provide the correct root route explicitly using SDK helpers. Do not create a second authorization server provider/routes.

- [ ] **Step 6: Write lifespan RED tests before mounting.** Instrument main and Blender child Starlette lifespan contexts. A top-level TestClient startup must enter each exactly once and shutdown in reverse order; a plain `Mount('/blender', child)` fixture must demonstrate why explicit composition is required.

- [ ] **Step 7: Implement explicit lifespan composition.** Preserve the existing main app lifecycle while entering the mounted Blender child's MCP session-manager lifespan. Do not call private MCP subprocess/session APIs; composing Starlette lifespan contexts is allowed. Ensure exception/cancellation during child startup unwinds the already-entered main lifecycle exactly once.

- [ ] **Step 8: Full endpoint auth E2E with in-process MCP clients.** Using ASGI/httpx clients only, prove main token -> `/mcp` works and `/blender/mcp` fails; Blender token -> `/blender/mcp` works and `/mcp` fails; no-token/cross-scope fails with the correct protected-resource metadata pointer. Then list fake Blender tools and execute one fake read tool end-to-end through the desktop queue.

- [ ] **Step 9: Gate and commit.**

```bash
$PYTEST -q tests/unit/test_settings.py tests/integration/test_mcp_oauth.py tests/integration/test_mcp_blender_relay.py
$PYTHON -m compileall -q app/auth app/blender_relay app/transport.py app/container.py app/settings.py tests/integration/test_mcp_blender_relay.py
git -C "$WORKTREE" diff --check
```

Commit:

```bash
git add app/auth app/blender_relay/server.py app/settings.py app/container.py app/transport.py tests/unit/test_settings.py tests/integration/test_mcp_oauth.py tests/integration/test_mcp_blender_relay.py
git commit -m "feat(blender-relay): isolate public MCP OAuth surface"
```

---

### Task 4: Add the outbound Windows Blender Hub worker and same-turn operator tools

**Files:**
- Create: `agents/desktop_node_agent.py`
- Modify: `agents/windows_fusion_agent.py`
- Create: `agents/windows_blender_agent.py`
- Modify: `app/blender_hub/operator.py` only for bounded notification retention if required by RED
- Create: `tests/unit/test_desktop_node_agent.py`
- Modify: `tests/unit/test_windows_fusion_agent.py`
- Create: `tests/unit/test_windows_blender_agent.py`
- Modify: `tests/unit/test_blender_hub_operator.py` only for bounded-retention regression

**Interfaces:**
- `agents.desktop_node_agent` owns generic `_PersistentHTTPSChannel`, `BridgeClient`, `ResultOutbox`, bounded upload/result delivery, and generic heartbeat helpers extracted from the proven Fusion agent without changing wire behavior.
- `windows_fusion_agent.py` imports those generic primitives and keeps Fusion-specific local MCP connection/execution/watchdog logic.
- Produce `BlenderHubWorker(supervisor, catalog, broker, bridge, *, node_id, heartbeat_seconds, claim_wait_seconds, operator_ask_timeout_seconds)` with async `connect_initial()`, `register_publication()`, `run()`, and bounded helper methods.
- Produce `install_hub_tools(catalog, broker, status_provider, ask_timeout_seconds)` that reserves `operator.*` and `hub.*` and registers `operator.ask`, `operator.notify`, `hub.status` through the same catalog invocation surface.

- [ ] **Step 1: Extract generic transport with characterization RED/GREEN.** Move only transport/outbox/result-delivery behavior from `windows_fusion_agent.py` into `desktop_node_agent.py`. Existing Fusion tests must pass unchanged before adding Blender behavior. No change to Fusion MCP URL/watchdog/tool execution semantics.

- [ ] **Step 2: Write synthetic-tool RED tests.** Assert reserved namespace collision fails before provider connect. `operator.ask` sends exact bounded prompt to `OperatorBroker.ask`; `operator.notify` records one bounded notification and returns immediately; `hub.status` returns only provider IDs/namespaces/states/errors already sanitized by the supervisor. Every synthetic tool is present in the same serialized public registration snapshot.

- [ ] **Step 3: Implement synthetic tools through `NamespacedToolCatalog`.** Register owned providers/namespaces through `register_provider`; do not add an alternate dispatch map. Keep conservative annotations unless a literal read-only claim is semantically true.

- [ ] **Step 4: Write initial-connect/isolation RED tests.** With fake connectors, one provider may fail while siblings connect. Worker becomes `ready=true` once its command loop/public catalog is coherent, not only when every provider is online. Serialize the exact current catalog excluding handlers/internal status/config.

- [ ] **Step 5: Implement worker initialization and registration.** Connect configured providers independently, install Hub tools, build public descriptors, POST `ready=true, protocol_profile="mcp-v1"`, capture returned desktop `session_generation`, and keep the exact local surface fingerprint/revision associated with it.

- [ ] **Step 6: Write same-turn operator heartbeat RED test.** Run worker with fake Bridge channels and a fake `operator.ask` command. Block the broker answer; advance fake time across multiple heartbeat intervals; assert heartbeat continues and no second claim executes. Submit the fake UI answer and assert the same claimed call returns that answer without re-entering `catalog.invoke`.

- [ ] **Step 7: Implement one-lane claim loop with independent heartbeat.** Heartbeat is a separate task/channel. The publication lock prevents re-registration while a claimed call is executing but does not stop heartbeat posts. A heartbeat 404 records that re-registration is required; recovery registration waits until the claimed call reaches a terminal local result.

- [ ] **Step 8: Write generation/publication race RED tests.** Claim carries generation G. Change local public surface or simulate Bridge re-register to G+1 before invocation; require zero catalog calls and a bounded stale result. During a blocked provider call, stage a refresh and prove new registration waits until the call finishes, then occurs before the next claim.

- [ ] **Step 9: Implement publication reconciliation between claims.** After each terminal local call, recompute public evidence. If evidence changed, register before next claim. If only provider status changed but retained public evidence is identical, update bounded status telemetry without needlessly changing the public tool surface; explicit Bridge re-registration still captures the new desktop generation.

- [ ] **Step 10: Write no-replay/outbox RED tests.** Make provider execution return, then fail result POST repeatedly. Assert provider handler call count remains one, outbox persists, no new claim occurs, and only result delivery retries. Make a claimed provider call raise typed session failure and assert no automatic reconnect/replay; later explicit worker/provider action may re-register for future commands only.

- [ ] **Step 11: Implement outbox-first recovery using the generic transport.** Save result before first delivery attempt; flush all retained results before claiming again; stale 400/409 removes only the retained result and never repeats the upstream call.

- [ ] **Step 12: Bound operator notification history if RED proves growth.** Convert `_notifications` to a bounded deque (target max 256) without changing tuple-return API; add overflow test retaining the newest entries. Do not change prompt arbitration semantics.

- [ ] **Step 13: Worker/Fusion gate and commit.**

```bash
$PYTEST -q tests/unit/test_desktop_node_agent.py tests/unit/test_windows_fusion_agent.py tests/unit/test_windows_blender_agent.py tests/unit/test_blender_hub_operator.py tests/unit/test_blender_hub_catalog.py tests/unit/test_blender_hub_providers.py tests/unit/test_blender_hub_supervisor.py
$PYTHON -m compileall -q agents/desktop_node_agent.py agents/windows_fusion_agent.py agents/windows_blender_agent.py app/blender_hub tests/unit/test_windows_blender_agent.py
git -C "$WORKTREE" diff --check
```

Commit:

```bash
git add agents/desktop_node_agent.py agents/windows_fusion_agent.py agents/windows_blender_agent.py app/blender_hub/operator.py tests/unit/test_desktop_node_agent.py tests/unit/test_windows_fusion_agent.py tests/unit/test_windows_blender_agent.py tests/unit/test_blender_hub_operator.py
git commit -m "feat(blender-hub): add outbound Windows relay worker"
```

---

### Task 5: Whole public-relay adversarial gate

**Files:**
- Verify all files changed in Tasks 1-4 plus the public-relay spec/plan.
- Corrective code is allowed only behind a new failing regression.

- [ ] **Step 1: Run the focused Blender/desktop/OAuth suite.**

```bash
$PYTEST -q \
  tests/unit/test_blender_hub_catalog.py \
  tests/unit/test_blender_hub_operator.py \
  tests/unit/test_blender_hub_transport.py \
  tests/unit/test_blender_hub_providers.py \
  tests/unit/test_blender_hub_supervisor.py \
  tests/unit/test_blender_relay.py \
  tests/unit/test_blender_relay_server.py \
  tests/unit/test_desktop_nodes.py \
  tests/unit/test_desktop_node_journal.py \
  tests/unit/test_desktop_node_agent.py \
  tests/unit/test_windows_fusion_agent.py \
  tests/unit/test_windows_blender_agent.py \
  tests/integration/test_desktop_node_routes.py \
  tests/integration/test_mcp_oauth.py \
  tests/integration/test_mcp_blender_relay.py
```

- [ ] **Step 2: Re-falsify the critical races.** Run named tests proving: stale queued command after desktop generation bump never claims; stale MCP-session surface never dispatches; identical surface + new desktop generation does not force relist; claimed mutation timeout is uncertain/no replay; result delivery retry never invokes provider twice; provider refresh registration cannot overtake a claimed call; blocked `operator.ask` keeps heartbeat alive and finishes inside the 360-second relay budget.

- [ ] **Step 3: Re-falsify OAuth/ASGI boundaries.** Verify exactly two protected resources when enabled, exact cross-audience denial, one authorization server, no nested Blender well-known route, child MCP session manager started/stopped exactly once, and Blender tool names never appear in main `/mcp` `tools/list`.

- [ ] **Step 4: Run the full unit suite.** Baseline before this milestone is 1840 passing tests.

```bash
$PYTEST -q tests/unit
```

No new unexpected skips. Existing Starlette deprecation warning may remain but no new warning class is accepted without explanation.

- [ ] **Step 5: Compile and inspect repository state.**

```bash
$PYTHON -m compileall -q app agents tests/unit/test_blender_relay.py tests/unit/test_blender_relay_server.py tests/unit/test_windows_blender_agent.py
git -C "$WORKTREE" diff --check
git -C "$WORKTREE" status --short
git -C "$WORKTREE" log --oneline -12
```

Search milestone-added code/docs for unfinished-marker patterns (T + ODO, T + BD, FIX + ME, Not + Implemented) and accidental public secrets/config paths.

- [ ] **Step 6: Independent review gate.** Prefer Codex or Antigravity when quota is available; OpenRouter is acceptable only if its configured API probe is healthy. Reviewer must be read-only and compare the complete milestone against `docs/superpowers/specs/2026-09-13-blender-bridge-public-relay-design.md`. Required focus: OAuth audiences, mounted lifespan, stale generations/revisions, result preservation, no replay, Fusion compatibility, and outbound-only Windows transport. Repair only proven findings with RED tests and re-run affected/full gates.

- [ ] **Step 7: Final bounded milestone commit if corrective code exists.** If Tasks 1-4 already end clean after review, do not create an empty commit. If Task 5 adds reviewed corrective code, commit:

```bash
git add <only-corrective-files>
git commit -m "fix(blender-relay): harden public relay boundaries"
```

Do not push, merge, deploy, install providers, or run live Blender/Orca actions in this milestone.
