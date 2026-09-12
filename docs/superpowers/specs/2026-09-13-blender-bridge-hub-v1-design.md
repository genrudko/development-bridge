# Blender Bridge / Hub v1 Design

**Status:** approved for implementation

**Baseline:** `development-bridge` main at `c4cfba1232c47325e52cd3f9852aa60c7db8ac43`

## Purpose

Build a Windows-first Blender Bridge/Hub that aggregates multiple existing Blender/printing MCP providers behind one logical workstation, without reimplementing Blender domain functionality in Development Bridge.

The Hub is infrastructure glue, not a new Blender CAD API. Upstream providers remain responsible for Blender semantics. Development Bridge supplies provider supervision, remote connectivity, tool discovery/routing, mutation serialization, operator interaction, and durable operational evidence.

## Non-goals

- Do not port the Fusion `fusion.cad/v1` semantic facade to Blender.
- Do not create a new object/entity reference model unless real provider conflicts prove it necessary.
- Do not vendor or copy code from upstream projects whose license does not permit it.
- Do not make arbitrary Windows shell execution a public Hub capability.
- Do not let two providers mutate one Blender scene concurrently.
- Do not claim generated print settings are intrinsically optimal without real printer/filament calibration context and slicer evidence.

## Runtime topology

```text
ChatGPT
   |
   v
Development Bridge / VPS
   |
   | one Blender workstation route / connector
   v
Windows Blender Hub
   |-- dcc provider        (broad Blender tools)
   |-- research provider   (revision/transaction/inspection when available)
   |-- 3mf provider        (3MF validation/review)
   |-- orca provider       (OrcaSlicer control/profile/slicing)
   `-- future providers
          |
          +--> Blender
          `--> OrcaSlicer
```

The Windows Hub is the provider multiplexer/supervisor. The VPS is the remotely reachable Development Bridge endpoint and operational control plane.

## Provider model

Each configured provider gets a stable namespace such as `dcc`, `research`, `threemf`, or `orca`.

The Hub discovers each provider's tool catalog and exposes namespaced public names:

```text
dcc.create_cube
research.mesh_inspect
threemf.validate
orca.slice
```

The Hub does not normalize Blender semantics across providers in v1. Provider overlap is intentional and can be used for cross-checks.

Provider source/version must be pinned. Updating a provider is an explicit operation, not an implicit `git pull latest` during startup.

Where upstream license status is unresolved, the provider may run as an external unchanged process but its code must not be copied into this repository.

## Global mutation rule

All provider tools are classified as read-only or mutating.

Read-only calls may execute concurrently. Mutating calls across all Blender-facing providers share one global write lock:

```text
read A -----+
read B -----+---- may overlap

write A ----[ lock ]----+
write B ----------------+---- waits for same lock
```

This is deliberately smaller than Fusion transaction orchestration. Upstream revision/transaction checks remain active when the provider supplies them.

If mutation classification is unknown, configuration must default conservatively to mutating rather than silently permit concurrent writes.

## Same-turn Operator Channel

Same-turn human interaction is a hard v1 requirement.

`operator.ask` is a blocking MCP operation. The MCP request stays open while the Windows Hub presents the question. When the user answers in Hub/Blender UI, the result completes that same tool call so the model continues the same ChatGPT turn.

```text
current ChatGPT turn
   -> operator.ask(...)
   -> VPS relay
   -> Windows Hub UI
   -> user answer
   -> same pending MCP call returns
   -> model continues same turn
```

This is distinct from durable between-turn continuity. A queued notification that returns `sent` is not an acceptable implementation of `operator.ask`.

Supported interaction types in v1:

- text answer
- confirm/reject
- finite choice
- notification (non-blocking)

Viewport/object/face picking is a later v1 slice built on the same request/reply correlation protocol.

Every operator request carries a unique prompt id and may carry an operation id, provider name, object/context summary, and evidence attachment reference.

## Transport

Windows initiates/maintains the outbound connection to the VPS. The design must not require inbound arbitrary remote access to the Windows host.

The transport must support:

- provider status/capability updates
- proxied tool calls/results
- long-lived blocking operator requests
- heartbeats while a same-turn request is waiting
- reconnect without replaying an already ambiguous/non-idempotent provider mutation
- bounded attachments/results, including image evidence

The transport implementation may use a persistent WebSocket/stream or an equivalent long-lived channel. The API boundary, not the specific socket library, is normative.

## Windows Hub UI

The Hub GUI is an operational supervisor, not a modeling application. Minimum state:

- Blender detected/connected
- OrcaSlicer detected/connected when enabled
- each provider online/degraded/offline
- provider version/pin
- global mutation lock state
- active calls
- operator inbox/chat
- logs/restart-provider actions

A Blender add-on/N-panel may present the same operator inbox and viewport-pick workflow, backed by the same Hub service.

## Print Pipeline

3D-print preparation is part of v1 scope.

The intended pipeline is:

```text
Blender model
  -> mesh/printability preflight
  -> repair only when explicitly allowed
  -> geometry 3MF export
  -> 3MF validation/review
  -> OrcaSlicer import
  -> real printer/nozzle/filament context
  -> profile physics validation
  -> slice
  -> warnings + time/material/toolpath evidence
  -> optional variant comparison
  -> final Orca project / 3MF / G-code artifact
```

### Geometry 3MF vs print project

The Hub treats these as separate artifacts:

- **Geometry 3MF:** model exported from Blender/print-prep provider.
- **Print project:** slicer-owned artifact including orientation, supports, printer, filament, and process settings.

The slicer-owned project is the preferred final editable artifact when the provider supports it.

### Print context

The Hub must carry real context instead of inventing a profile:

- printer model and preset id/name
- nozzle diameter and material/type
- filament preset/material
- calibrated values when known: flow ratio, pressure advance, max volumetric speed, temperatures
- optimization goal: balanced, dimensional accuracy, strength, surface quality, or fastest safe

Missing calibration is represented as unknown, not guessed.

### Settings optimization

The model may propose process variants, but the slicer provider is responsible for applying profiles, checking physical/profile constraints, slicing, and returning evidence. When trade-offs exist, the Hub should expose measurements/warnings rather than claim a universal optimum.

Typical compare loop:

```text
candidate process settings
  -> physics/profile gate
  -> slice each candidate
  -> compare print time / material / warnings / geometry evidence
  -> model or operator chooses
```

## Initial upstream strategy

Preferred provider roles from current research:

- broad Blender Hands: `dcc-mcp-blender`
- safety/research: `blender-research-mcp` as an external unchanged provider while licensing remains unresolved
- print-prep/session UX donor/provider as useful: `blender-mcp-bridge`
- 3MF validation: official/consortium 3MF MCP provider when compatible
- slicer control: OrcaSlicer MCP provider(s), preferring one that can read/apply presets, validate profile physics, slice, compare variants, capture toolpath evidence, and save a project artifact

Provider choice is configuration. The Hub must not hard-code one upstream project's internal tool names into its core routing layer.

## Failure semantics

- Provider offline: fail that provider call clearly; do not silently reroute a mutation to another provider.
- Duplicate public tool name inside one namespace: configuration/catalog error.
- Unknown mutation classification: conservative write lock.
- Operator prompt timeout/cancel: return explicit timeout/cancel result; never fabricate an answer.
- Transport disconnect during mutating call: result is uncertain unless the provider can authoritatively prove terminal outcome. Do not automatically replay.
- Print-profile validation blocked: do not slice/export as though validation passed.

## Testing

Offline tests must cover at least:

- namespace catalog discovery and conflicts
- concurrent read behavior
- cross-provider mutation serialization
- blocking same-turn operator request/answer correlation
- timeout/cancel behavior
- provider reconnect without mutation replay
- print-context validation and preservation of real calibration values
- adapter contract for Blender, 3MF, and Orca provider classes

Live acceptance, after offline green:

1. one Blender session with two providers
2. mutation via provider A
3. independent read/inspection via provider B
4. same-turn operator question answered from Windows Hub
5. same ChatGPT turn continues and performs a follow-up call
6. model exported to geometry 3MF
7. 3MF validated
8. opened in OrcaSlicer with actual printer/nozzle/filament preset context
9. at least two process variants sliced/compared
10. final project artifact saved explicitly

## Implementation boundary

The first implementation milestone is intentionally small:

1. provider catalog + namespacing
2. global mutation gate
3. same-turn operator broker
4. print-context model
5. provider adapter/transport contract

GUI, Blender N-panel selection, provider installation, and live Orca/Blender acceptance build on that core.