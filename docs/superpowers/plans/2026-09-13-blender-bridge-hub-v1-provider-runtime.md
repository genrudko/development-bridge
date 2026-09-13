# Blender Bridge/Hub v1 Provider Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the local, independently supervised HTTP/stdio MCP provider runtime and populate/invoke the accepted Task 1 catalog without adding an external Hub surface.

**Architecture:** `providers.py` contains bounded configuration, transport-neutral session contracts, MCP conversion, and small SDK connectors. `supervisor.py` owns independent provider sessions and lifecycle policy. The existing catalog is extended only to retain immutable upstream schemas/display metadata; all calls still enter through `NamespacedToolCatalog.invoke`, preserving its single global mutation lock.

**Tech Stack:** Python 3.12, asyncio, dataclasses/protocols, MCP Python SDK 2.0.0 (`ClientSession`, Streamable HTTP, stdio), pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-09-13-blender-bridge-hub-v1-provider-runtime-design.md`

## Global constraints

- No public/local Hub MCP server, VPS relay, `DesktopNodeService` integration, Windows GUI, provider installer/downloader, Print Pipeline, arbitrary shell, or live Blender/Orca/provider action. The local Hub MCP server is explicitly deferred.
- Do not modify or generalize `agents/windows_fusion_agent.py`; it is a read-only lifecycle donor.
- Provider endpoints and stdio launch specs come only from operator configuration. HTTP is loopback-only with redirects and environment/proxy routing disabled; stdio uses exact argv and never a shell. Transport config is independent of provider kind.
- Preserve upstream JSON schemas, ToolAnnotations, MCP results, and remaining SDK tool publication metadata. Never synthesize annotation hints.
- Every upstream invocation enters through `NamespacedToolCatalog.invoke`; no adapter or supervisor bypass is allowed.
- No automatic reconnect or call replay. Only a typed adapter SDK/session failure detaches the failed session and degrades only its provider, plus the explicit surface-quarantine decisions below; mutations are never retried.
- Sanitized adapter and supervisor exceptions are created and raised after leaving the raw exception handler, have no cause/context chain, and expose only stable identifiers, phase/tool, exception type, and bounded codes/text.
- Unit tests use fakes/monkeypatched SDK context managers only: no subprocess, network, DNS, package installation, or live providers.
- Each implementation task follows RED -> GREEN -> adversarial debug sweep -> `git diff --check` -> bounded diff/status review -> local commit. Do not push, merge, deploy, or perform external actions.
- Use the shared environment explicitly:

```bash
PYTHON=/home/eodadmin/codex-workspace/development-bridge/.venv/bin/python
PYTEST=/home/eodadmin/codex-workspace/development-bridge/.venv/bin/pytest
```

---

### Task 1: Provider configuration and catalog descriptor contracts

**Files:**
- Create: `app/blender_hub/providers.py`
- Modify: `app/blender_hub/catalog.py`
- Modify: `app/blender_hub/__init__.py` only for intentional public exports
- Create: `tests/unit/test_blender_hub_providers.py`
- Modify: `tests/unit/test_blender_hub_catalog.py`

**Interfaces:**
- Produce `ProviderKind(str, Enum)`: `DCC_GATEWAY`, `THREE_MF`, `ORCA`, `RESEARCH`.
- Produce frozen `HttpProviderConfig(provider_id: str, namespace: str, kind: ProviderKind, url: str, read_timeout_seconds: float | None = None)`.
- Produce frozen `StdioProviderConfig(provider_id: str, namespace: str, kind: ProviderKind, argv: tuple[str, ...], cwd: Path | None = None, env: Mapping[str, str] = field(default_factory=dict), read_timeout_seconds: float | None = None)`.
- Produce `ProviderConfig = HttpProviderConfig | StdioProviderConfig`, `validate_provider_configs(configs: Iterable[ProviderConfig]) -> tuple[ProviderConfig, ...]`, and `build_stdio_environment(config: StdioProviderConfig, environ: Mapping[str, str]) -> dict[str, str]`.
- Produce frozen `UpstreamTool(name: str, title: str | None, description: str | None, input_schema: Mapping[str, object], output_schema: Mapping[str, object] | None, annotations: Mapping[str, object], publication_metadata: Mapping[str, object])` using immutable/deep-copied JSON-safe snapshots.
- Extend `ProviderTool` and `CatalogTool` with matching schema/display/publication fields while retaining `metadata` as the exact canonical annotation mapping consumed by Task 1 `is_mutating`. Preserve existing constructor call sites with safe defaults.

- [ ] **Step 1: Write configuration RED tests.** Cover valid HTTP IPv4/`localhost`/bracketed IPv6 URLs; reject non-loopback hosts, deceptive suffixes, missing/invalid ports, user-info, query/fragment, bad schemes, duplicate IDs/namespaces, invalid/boundary IDs and namespaces, nonpositive/nonfinite timeouts, oversized argv/env, invalid env keys, non-string values, and empty command. Assert validation makes no network or subprocess call.
- [ ] **Step 2: Run RED.**

```bash
$PYTEST -q tests/unit/test_blender_hub_providers.py tests/unit/test_blender_hub_catalog.py
```

- [ ] **Step 3: Implement minimal frozen config/value contracts and validators.** Parse URLs with `urllib.parse.urlsplit`; compare the normalized parsed hostname to the three allowlisted loopback names; require an explicit valid port. Build stdio env from only `PATH`, `PATHEXT`, `SYSTEMROOT`, `WINDIR`, `COMSPEC`, `TEMP`, `TMP`, `TMPDIR`, `LANG`, `LC_ALL`, followed by validated overrides. Enforce 64 argv entries, 4096 characters per entry/value, 128 overrides, and 16 KiB merged UTF-8 environment data. Do not classify keys as secret or emit config in errors/status.
- [ ] **Step 4: Write catalog preservation RED tests.** Register tools with nested `inputSchema`, `outputSchema`, title/description/publication metadata, and canonical annotations; mutate every caller-owned nested object and objects returned from `list_tools`; prove catalog evidence and snapshotted mutation classification do not change. Keep all existing Task 1 catalog tests green.
- [ ] **Step 5: Extend catalog descriptors minimally and GREEN.** Deep-copy JSON-safe fields on registration and return defensive immutable/copy snapshots from listing. Do not infer annotations or change namespace qualification, collision rules, provider-state behavior, or the global lock.
- [ ] **Step 6: Debug sweep and commit.** Exercise Unicode/encoded URL edge cases, `localhost.evil`, IPv4 integer spellings, duplicate configuration atomicity, Windows environment keys, NaN timeout, JSON-invalid schema values, and legacy `ProviderTool(name, handler, metadata)` callers. Run focused tests, `$PYTHON -m compileall -q app/blender_hub tests/unit/test_blender_hub_providers.py tests/unit/test_blender_hub_catalog.py`, `git diff --check`, and review `git status --short` plus the complete task diff. Commit `feat(blender-hub): add provider configuration contracts`.

---

### Task 2: Transport-neutral sessions and MCP SDK connectors

**Files:**
- Modify: `app/blender_hub/providers.py`
- Modify: `tests/unit/test_blender_hub_providers.py`

**Interfaces:**
- Produce runtime-check-free `ProviderSession(Protocol)` with async `initialize()`, `list_tools() -> tuple[UpstreamTool, ...]`, `call_tool(name, arguments) -> object`, and `close()`.
- Produce `ProviderConnector(Protocol)` with async `connect(config: ProviderConfig) -> ProviderSession`.
- Produce `StreamableHttpProvider.connect(config: HttpProviderConfig) -> ProviderSession` and `StdioProvider.connect(config: StdioProviderConfig) -> ProviderSession`.
- Produce internal `_McpProviderSession` owning one `AsyncExitStack` and SDK `ClientSession`; `initialize`, `list_tools`, and `call_tool` are thin SDK adapters, and `close` is idempotent.
- Produce typed adapter base `ProviderSessionFailure(provider_id, phase, exception_type)` and `ProviderConnectionError(provider_id, phase="connect", exception_type=...)` for connector/context-entry failure. Supervisor `ProviderCallFailure(provider_id, tool_name, phase="call", exception_type=...)` is a separate sanitized public error.
- Produce private immutable `CleanupIssue(exception_type, phase)` and a one-attempt cleanup helper that converts ordinary cleanup exceptions/`ExceptionGroup` immediately to sanitized values without retaining raw objects, never raises an ordinary cleanup error, and leaves `asyncio.CancelledError` untouched.

- [ ] **Step 1: Write HTTP connector and partial-entry RED tests with monkeypatched async context managers/client transport.** Prove the connector constructs and enters a dedicated `httpx2.AsyncClient(follow_redirects=False, trust_env=False, timeout=...)` with connect/write/pool set to 30 seconds and read set to 300 seconds. Prove that exact client is passed as `http_client=` to `streamable_http_client(config.url, ...)`, so the SDK default-client path is never used and a 3xx cannot be followed. Then prove `ClientSession(read, write)` is entered, `initialize()` precedes list/call, separately configured MCP `read_timeout_seconds` reaches `call_tool`, and partial client/transport/session/initialize failures close the manually owned stack exactly once. Make context entry fail with one sentinel while cleanup fails with a different sentinel and both an ordinary exception and `ExceptionGroup`; require primary exception-type precedence, absence of both sentinels from text/status/formatted traceback and recursively traversed cause/context/groups, and `None` public cause/context. Add cleanup-only close failure and cleanup-cancellation cases. Invalid URL construction must fail before HTTP or SDK mocks are touched. Tests open no network connection.
- [ ] **Step 2: Write stdio connector RED tests.** Prove `StdioServerParameters` receives `command=argv[0]`, exact `args`, validated `cwd`, and only the minimal merged env; `stdio_client` and `ClientSession` are entered without a shell or platform-specific process options. Put sentinel secrets in ambient and override environments, then prove unrelated ambient secrets and all configuration values are absent from exceptions and public session/status representations.
- [ ] **Step 3: Write MCP conversion and typed-boundary RED tests.** Use real SDK `Tool`, `ToolAnnotations`, and `CallToolResult` models. Assert exact JSON-mode preservation of nested input/output schemas, title/description, execution/icons/`_meta`, and only supplied annotation aliases. Assert omitted hints stay omitted. Assert call results preserve content, structured content, `isError`, `resultType`, and `_meta` without semantic rewriting. For initialize/list/call separately, make the exact SDK await raise and assert typed `ProviderSessionFailure` metadata. Make conversion/`model_dump`/snapshot code raise and assert the original error propagates, is not typed as a session failure, and the adapter remains usable. Assert `CancelledError` is untouched.
- [ ] **Step 4: Implement small connectors/session adapter and GREEN.** Manually own `AsyncExitStack`; use the private one-attempt cleanup helper for partial entry and `_McpProviderSession.close`. Ordinary cleanup exceptions, including groups, become type/phase-only `CleanupIssue`; cancellation is never converted. For primary context-entry failure, record only type/phase in a narrow handler, leave it, clean up, then raise unchained sanitized `ProviderConnectionError` from a no-active-exception point; primary wins over ordinary cleanup. On setup cancellation, attempt cleanup once and propagate cancellation, including cancellation raised by cleanup. Cleanup-only close failure becomes unchained `ProviderSessionFailure(phase="close")` after the helper returns. Use the dedicated entered `httpx2.AsyncClient`, MCP contexts, and exact security/timeouts above. Wrap only each concrete SDK await/context-entry operation; keep conversion/snapshots outside. Convert with `model_dump(mode="json", by_alias=True, exclude_none=True)`. Do not catch an SDK-returned `isError`.
- [ ] **Step 5: Debug sweep and commit.** Falsify close-before-initialize, double-close, every partial-entry point, primary-plus-cleanup failure, cleanup `ExceptionGroup`, cleanup-only close failure, cleanup cancellation, initialize/list/call failure, conversion/programming exception, empty arguments, and annotation alias/default leakage. Put distinct sentinel secrets in primary and cleanup failures and assert absence from `str`/`repr`, formatted traceback, recursively inspected cause/context/groups, and status; require public wrapper cause/context `None`. Run `$PYTEST -q tests/unit/test_blender_hub_providers.py`, compile the module/test, run `git diff --check`, and review the bounded diff/status. Commit `feat(blender-hub): add local MCP provider connectors`.

---

### Task 3: Supervisor, catalog integration, and bounded DCC gateway

**Files:**
- Create: `app/blender_hub/supervisor.py`
- Modify: `app/blender_hub/__init__.py` only for intentional public exports
- Create: `tests/unit/test_blender_hub_supervisor.py`
- Modify: `tests/unit/test_blender_hub_catalog.py` only for catalog integration regressions

**Interfaces:**
- Produce `ProviderSupervisor(configs: Iterable[ProviderConfig], catalog: NamespacedToolCatalog, connector_for: Callable[[ProviderConfig], ProviderConnector])`.
- Produce async `connect(provider_id) -> ProviderStatus`, `refresh(provider_id) -> ProviderStatus`, `reconnect(provider_id) -> ProviderStatus`, `close(provider_id) -> ProviderStatus`, `close_all() -> tuple[ProviderStatus, ...]`, and `invoke(qualified_name, arguments) -> object`.
- Produce typed `ProviderSessionUnavailable(provider_id, tool_name)` for handler-level fail-fast invocation when last-known tools remain published but no usable session exists.
- Produce typed `ProviderToolStale(provider_id, tool_name)` for generation mismatch, sanitized and unchained, with no degradation, retry, or upstream access.
- `connect` and `reconnect` share destructive one-attempt replacement semantics: invalidate publication and close the old session before staging one candidate; there is no rollback to the old session and no call retry.
- Use private per-provider runtime records containing config, `ProviderSession | None`, usability state, monotonic `publication_generation`, selected published-name snapshot, and one `asyncio.Lock`; expose only catalog `ProviderStatus`, never config/session details. The lock serializes all lifecycle operations and all upstream calls for that provider. Different providers remain independent.
- Define `DCC_CANONICAL_TOOLS = frozenset({"search", "describe", "load_skill", "call"})` and a pure surface-selection helper used before catalog registration.
- Define a small pure publication-failure decision helper that permits retaining a usable session only when all previously published upstream names remain in the newly selected, validated surface; it quarantines otherwise.

- [ ] **Step 1: Write destructive replacement lifecycle/isolation RED tests with fake sessions/connectors.** At construction all providers have empty catalog registrations and `OFFLINE/not_connected`. For connect and reconnect while usable, prove generation increments and publication clears before old-session detach/close; sanitized old-close failure stops before candidate creation and remains empty `OFFLINE`. Fail candidate context/connection, initialize, SDK list, conversion, surface selection/policy, handler/snapshot construction, and catalog registration separately. Assert the single local candidate owner transfers it through exactly one close attempt on every pre-commit exit, runtime session none/unusable, empty publication, sanitized `OFFLINE` phase/type without config, original non-SDK exception propagated unchanged, and no old-session resurrection. Catalog failure leaves the atomic empty registration. Prove a later explicit reconnect can recover. Explicit close clears/increments despite sanitized close failure; `close_all` continues every sibling. A failing provider does not block a healthy one.
- [ ] **Step 2: Write generation/registration/refresh RED tests.** Prove successful refresh chooses a next generation, constructs handlers with it, atomically replaces only that provider, then commits runtime generation/name snapshot only after registration succeeds; registration return plus runtime commit is one synchronous await-free critical section under the provider lock. SDK list failure with unchanged surface may retain the old snapshot and generation while becoming unusable, so fresh invoke yields `ProviderSessionUnavailable`. For both incomplete-DCC and missing-prior-name publication quarantine, capture old read and mutating handlers, choose the next generation, rebuild the retained snapshot from the exact accepted immutable names/schema/display/publication metadata/`ToolAnnotations` with only new-generation handlers, atomically register it, and only then commit generation and quarantine. Assert old handlers raise unchained `ProviderToolStale` and fresh retained handlers raise unchained `ProviderSessionUnavailable`, all with zero upstream access and unchanged retained evidence. Extra DCC aliases remain ignored and no partial canonical surface is published. Force retained-snapshot registration to fail: require atomic empty registration, generation advance, `DEGRADED` unusable/session none, unchanged propagation of the original non-SDK error, stable type/phase-only publication-abort status with no raw leak, stale old handlers, and absent fresh lookup. Every other clear path increments generation with atomic empty registration. Other provider entries/status remain unchanged; duplicate config is rejected before mutation. All lifecycle/calls for one provider serialize, while different providers progress independently.
- [ ] **Step 3: Write DCC policy RED tests.** A gateway listing the four canonical tools plus aliases publishes exactly four; aliases are ignored without failure. Missing any canonical tool on initial connect closes the session, publishes none, and yields `OFFLINE/canonical_surface_incomplete`. An incomplete refresh republishes the exact previous complete four at the next generation only for inspection, detaches/best-effort closes the session, yields unusable `DEGRADED`, makes a captured old handler stale, and makes fresh retained invokes fail fast with `ProviderSessionUnavailable` until explicit connect/reconnect. Verify retained schemas/annotations/publication evidence are unchanged and 3MF/Orca/research providers publish every listed tool and defer collisions to the catalog.
- [ ] **Step 4: Write invocation, stale-handler, and lock-order RED tests.** Assert `supervisor.invoke` calls `catalog.invoke`. Each handler acquires its provider lock, checks captured versus current generation before session/upstream, and uses that exact session only on a match. Deterministically capture/queue an old read handler and an old mutating handler, successfully refresh to remove/replace the tool, resume each, and require unchained `ProviderToolStale`, zero old upstream calls, no degradation/retry, plus successful fresh lookup through the new handler. Repeat after close/clear. Retain same-provider serialization, different-provider overlap, and catalog-wide mutation serialization. Test typed call failure detach/close and unchained `ProviderCallFailure`; matched-generation unusability gives unchained `ProviderSessionUnavailable`; `isError=True` is unchanged. Instrument global-mutation-lock -> provider-lock order, synchronous registration/status, lifecycle never invoking catalog, and no reverse acquisition/deadlock.
- [ ] **Step 5: Write race/cancellation RED tests.** Block a call and race both reconnect and close against it; prove the lifecycle operation waits for the provider lock, the in-flight call stays on its exact old session, and no call is redirected to a stale or replacement session. Cancel a normal call and prove `asyncio.CancelledError` propagates without degrading or detaching the healthy session, then prove that session remains callable. For both destructive connect and reconnect, deterministically cancel at candidate initialize, SDK list, conversion/snapshot, policy/selection, handler construction, and a synchronous catalog-registration fake raising `CancelledError`. In every candidate-stage case assert empty publication, runtime session none/unusable and `OFFLINE`, exactly one candidate-close attempt, no old resurrection, propagated cancellation, and no secret leakage. Add primary cancellation plus ordinary sanitized candidate-close failure (primary cancellation remains), candidate close raising `CancelledError` (cancellation wins), and old-session close cancellation (no candidate created). Cancellation is never converted to a provider failure.
- [ ] **Step 6: Implement supervisor and GREEN.** Implement the destructive transaction and staged candidate exactly as specified: pre-invalidate generation/publication, detach, stable `OFFLINE`, close old, then run the entire candidate pipeline locally; install session/name snapshot and set `ONLINE` only after atomic registration. Stop on sanitized old-close failure; propagate old-close cancellation without creating a candidate. From candidate creation to commit maintain one local owner and route every pre-commit exit, including cancellation, through exactly one cleanup attempt. Preserve primary cancellation over ordinary sanitized cleanup failure, let cleanup cancellation win immediately, retain only bounded `replacement_cancelled`/phase status, and never retain raw exception text/config. Make synchronous registration plus runtime session/name/status/generation commit one await-free critical section under the provider lock; registration cancellation before return is pre-commit. Typed SDK/connection failures use sanitized outcomes; incomplete DCC uses canonical status; non-SDK failures set sanitized local-abort phase/type then propagate the original unchanged. Implement generation-closed handlers and commit-after-registration refresh. On surface-change quarantine, republish exact retained evidence with next-generation handlers before committing generation and detaching; if retained republish fails, atomically clear, advance generation, quarantine/degrade, close best-effort, and propagate the original non-SDK error unchanged. Pure unchanged-surface SDK refresh failure may retain generation as-is. Best-effort close consumes only sanitized `ProviderSessionFailure`, with `close_all` sibling continuation. Never broadly catch normal adapter/conversion/policy/catalog work merely to reclassify it. Raise public wrappers from no-active-exception points with no chain. Preserve cancellation and catalog-global -> provider lock order; lifecycle never calls `catalog.invoke`.
- [ ] **Step 7: Debug sweep and commit.** Exercise every candidate stage failure and cancellation point, old-close stop/cancellation, later recovery, unknown IDs, call/close/reconnect races, repeated connect/close, exact retained-snapshot republish for DCC and dropped-name quarantine, retained-republish abort-to-empty, SDK-retained-publication unusability, successful registration commit boundary, old read/mutation handler staleness versus fresh unavailable lookup, and cancellation/cleanup precedence. Use primary/cleanup sentinel secrets and recursive group traversal; require sanitized wrappers/status and no chains. Confirm non-SDK connect/reconnect failures leave no candidate or old session, while non-SDK ordinary call/refresh failures retain a healthy session; lock ordering cannot deadlock and no call is replayed. Run:

```bash
$PYTEST -q tests/unit/test_blender_hub_catalog.py tests/unit/test_blender_hub_providers.py tests/unit/test_blender_hub_supervisor.py
$PYTHON -m compileall -q app/blender_hub tests/unit/test_blender_hub_catalog.py tests/unit/test_blender_hub_providers.py tests/unit/test_blender_hub_supervisor.py
git diff --check
git status --short
```

Review the complete task diff and commit `feat(blender-hub): supervise local MCP providers`.

---

### Task 4: Whole-milestone adversarial gate

**Files:**
- Verify only: `app/blender_hub/*.py`, `tests/unit/test_blender_hub_*.py`, and the two provider-runtime documents.
- Do not add server, relay, GUI, installer, provider package, or live-test files.

- [ ] **Step 1: Run the focused milestone suite.**

```bash
$PYTEST -q tests/unit/test_blender_hub_catalog.py tests/unit/test_blender_hub_operator.py tests/unit/test_blender_hub_transport.py tests/unit/test_blender_hub_providers.py tests/unit/test_blender_hub_supervisor.py
```

- [ ] **Step 2: Run the closest affected regressions.** The catalog changes are internal to `app.blender_hub`; run the full unit suite to detect constructor/type leakage without invoking integration transports.

```bash
$PYTEST -q tests/unit
```

- [ ] **Step 3: Falsify the acceptance conditions.** Re-run targeted tests proving loopback URL rejection; explicit non-redirecting/non-environment HTTP client injection with 30/30/30/300 connect/write/pool/read seconds and a distinct MCP `read_timeout_seconds`; exact no-shell argv/env; partial-entry/cleanup precedence, sanitization, groups, and cancellation; typed SDK boundaries; ordinary call/refresh non-SDK errors remain non-poisoning while destructive connect/reconnect non-SDK aborts leave empty `OFFLINE`; exactly-once candidate ownership/cleanup on every failure and cancellation stage; independent provider failure; generation-stale read and mutation handlers with zero upstream access and successful replacement lookup; old-stale versus fresh-unavailable retained handlers; same-provider serialization and catalog-global -> provider lock order with no reverse deadlock; unusable-session fail-fast and explicit recovery; exact-evidence DCC/surface-change retained republish and republish-failure clearing; successful registration commit-after-return; exactly four DCC tools with aliases ignored; exact immutable schemas/annotations/results; one catalog-wide mutation lock; and zero call replay. Inspect bounded pytest output for warnings and unexpected skipped tests.
- [ ] **Step 4: Compile and perform final repository review.** Run `$PYTHON -m compileall -q app/blender_hub tests/unit/test_blender_hub_*.py`, `git diff --check`, `git status --short`, `git diff --stat`, and the complete `git diff -- app/blender_hub tests/unit docs/superpowers/specs/2026-09-13-blender-bridge-hub-v1-provider-runtime-design.md docs/superpowers/plans/2026-09-13-blender-bridge-hub-v1-provider-runtime.md`. Confirm no placeholder markers (`TODO`, `TBD`, `FIXME`, `pass`, `NotImplemented`) in milestone-added code/docs and no changes outside scope.
- [ ] **Step 5: Review spec-to-test coverage and signatures.** Check every numbered architectural requirement in the spec against at least one named test; confirm config/session/supervisor signatures agree across code, tests, spec, and plan; confirm `metadata` still means exact ToolAnnotations for Task 1 classification; confirm no direct session-call entry point bypasses `NamespacedToolCatalog.invoke`.
- [ ] **Step 6: Commit only after the gate is green.** If Task 4 requires corrective code, add a failing regression first, make the smallest repair, and rerun affected checks plus Steps 1–5. Commit the final bounded milestone state as `feat(blender-hub): complete provider runtime milestone`. Do not push, merge, deploy, install providers, start a Hub server, or run a live acceptance.
