# Unified Fusion Windows Launcher Design

## Goal

Replace the current split Windows runtime startup with one manually launched `Fusion Bridge` GUI that owns and supervises the three Development Bridge provider paths used by Fusion CAD Agent:

- reference: `fusion-workstation` via Autodesk Fusion MCP on `127.0.0.1:27182/mcp`;
- eyes: PERISCOPE proxy on `127.0.0.1:18769/mcp` plus relay node `fusion-eyes`;
- hands: pinned Shimmer sidecar on `127.0.0.1:18768/mcp` plus relay node `fusion-hands`.

Autodesk Fusion 360 itself remains a manual user launch. The GUI also remains a manual user launch; there is no Windows Startup entry.

## User Experience

Normal use after installation is exactly:

1. User launches Autodesk Fusion 360 manually.
2. User launches the existing `Fusion Bridge` GUI manually.
3. The GUI automatically waits for required Fusion-local services and starts/restarts the provider processes it owns. No separate PowerShell windows, Hands launcher, Eyes launcher, or additional Start button is required.

If the GUI is launched before Fusion is ready, it remains open, reports a waiting state, and converges automatically once Fusion becomes available.

Closing the GUI terminates only the child processes it owns. It never closes Fusion 360 or saves/closes Fusion documents.

## Architecture

Extend the existing `agents/fusion_relay_gui.pyw`; do not create a second GUI application. The existing workstation relay and Eyes process-group ownership remain intact. Add a focused Hands runtime helper, symmetric with `fusion_eyes_runtime.py`, to describe the pinned Shimmer paths, sidecar process, overlay qualification inputs, and `fusion-hands` relay process.

The GUI acts as a small local supervisor. Each provider group has independent desired state, observed state, owned process handles, status text, and restart/backoff behavior. Failure of Eyes or Hands must not stop `fusion-workstation`. Failure of the workstation relay must not kill a healthy Eyes/Hands local runtime unless that child directly depends on the failed process.

The GUI continues to reuse the DPAPI-protected desktop-node token. No plaintext token file, new credential store, or second token workflow is introduced.

## Provider Lifecycle

### Reference / `fusion-workstation`

The existing `windows_fusion_agent.py` path remains the reference relay. The GUI starts it automatically after a usable stored token is available. The current explicit `Start` button becomes unnecessary during normal operation; token first-run/repair controls remain available for recovery.

If local Autodesk MCP port `27182` is unavailable, the GUI keeps the workstation relay in a waiting/retrying state rather than exiting the application.

### Eyes / `fusion-eyes`

Reuse `fusion_eyes_runtime.py` and the existing PERISCOPE managed process group. The GUI owns:

- pinned PERISCOPE runtime already installed under `%LOCALAPPDATA%\DevelopmentBridgeFusion\periscope`;
- local `mcp-proxy` on port `18769`;
- relay node `fusion-eyes` with its existing distinct outbox/log.

Missing PERISCOPE runtime degrades only Eyes and is reported explicitly. Unknown occupancy of port `18769` remains fail-closed; the GUI must not attach to an unowned process.

### Hands / `fusion-hands`

Create `agents/fusion_hands_runtime.py` as the single source of local Hands runtime paths and process specifications. It owns the exact qualified Shimmer revision `97a06e76c289420a721590ddcab334f5f3dc3178`, the sidecar endpoint `127.0.0.1:18768/mcp`, add-in bridge expectation `127.0.0.1:9000`, the `fusion-hands` node id, and distinct Hands outbox/log paths.

The GUI starts the pinned Shimmer sidecar itself and then starts an unchanged relay targeting `http://127.0.0.1:18768/mcp` as node `fusion-hands`.

Unknown occupancy of `18768` is fail-closed: do not adopt or kill a process the GUI does not own. If a pre-existing process can be positively identified as the exact managed Shimmer runtime through the approved identity checks, the implementation may report it as external/healthy but must not claim ownership or terminate it.

## Guarded Shimmer Overlay

The current guarded overlay under `ops/fusion_shimmer_overlay/` remains the only Bridge-owned modification to pinned Shimmer.

The unified GUI is responsible for verifying the exact pinned Shimmer installation and overlay state before Hands is advertised as ready. Overlay application must remain deterministic and fail-closed:

- verify the pinned upstream revision/provenance and manifest preimage hashes;
- verify Bridge overlay source hashes;
- apply only the four qualified overlay changes defined by the existing installer/manifest contract;
- use atomic replacement and rollback on failure;
- verify postimage hashes before starting/qualifying Hands.

The GUI must not use Autodesk arbitrary-code execution to install the overlay. Installation is a normal local Windows filesystem operation performed by the user-launched GUI under the current user account.

A missing or mismatched Shimmer install leaves Hands degraded and produces an actionable status message; it does not break Reference or Eyes.

## Hands Qualification

Keep the Bridge-owned session-scoped qualification mechanism already implemented in `becee51`.

After both private guarded tools are visible from `fusion-hands` and the rich-node session generation is current, the runtime can be live-qualified through the existing hidden operator seam. Qualification remains bound to `(logical_node, rich_node, rich_session_generation)` and is invalidated automatically on reconnect/generation change.

The launcher must not persist a fake `supported` flag locally. Capability truth remains owned by Development Bridge. Before qualification, public `hands.sketch` and `hands.feature` are `degraded`; only Bridge may promote them to `supported` for the current qualified session.

## Supervision and Recovery

The GUI polls local prerequisites and child process state on a bounded cadence and uses bounded restart backoff instead of rapid restart loops.

Each owned child process has one of these user-visible states: waiting, starting, online, degraded, failed/retrying, stopped. The GUI records the latest reason for degradation.

Required recovery behavior:

- Fusion starts after GUI: provider groups converge automatically.
- Fusion closes while GUI remains open: relays stop claiming readiness and wait; the GUI stays open.
- Fusion restarts: provider groups reconnect without requiring GUI restart.
- Eyes child exits: restart only Eyes group after backoff.
- Shimmer sidecar or Hands relay exits: restart only Hands group after backoff; Bridge qualification naturally invalidates on generation change.
- Workstation relay exits: restart workstation relay after backoff.
- Windows reboot: after the user manually launches Fusion and then the GUI, the same convergence occurs with no additional launcher steps.

No provider restart is allowed to save, close, or mutate a Fusion document.

## GUI

Retain the current Tkinter application and its log pane. Replace the current coarse status presentation with three explicit provider rows:

- Reference — Autodesk MCP / `fusion-workstation`;
- Eyes — PERISCOPE / `fusion-eyes`;
- Hands — Shimmer / `fusion-hands`.

Each row shows local runtime state and Bridge registration state. Hands additionally shows overlay/qualification state when degraded.

Normal launch starts supervision automatically. Keep `Stop` as an explicit operator control to stop all GUI-owned child processes while leaving the GUI open. Keep token repair/forget and log access controls. A separate `Start` button is not part of the normal workflow; if retained for recovery, it must be visually secondary and idempotent.

## Process Ownership and Safety

The GUI stores every `Popen` handle it creates and terminates only those owned processes. Tree termination is allowed only for a process tree spawned by the GUI.

Ports `18768` and `18769` are protected by ownership checks. Occupancy without a positive managed-runtime identity is an error, not permission to kill or reuse the listener.

Protected Fusion documents, including `Schedule` and the historical golden document, are outside launcher responsibility. Startup, supervision, overlay verification, and shutdown must have no document save/close side effects.

## Packaging and Installation

Do not make `.exe` packaging a prerequisite. The first deliverable remains the existing Python/Tkinter GUI launched through `START_FUSION_GUI.cmd`, because that path already works and is testable.

Update the one-time Windows bootstrap/install flow so the unified GUI, Hands runtime helper, overlay manifest/files, and existing Eyes assets are installed together under the existing DevelopmentBridgeFusion layout. No separate permanent Hands launcher remains after migration.

A later `.exe` wrapper may be added as cosmetic packaging without changing runtime architecture.

## Testing

Use TDD for implementation.

Unit coverage must include pure process-spec/path helpers, provider state transitions, independent failure/restart behavior, bounded backoff, port ownership fail-closed behavior, overlay verification decisions, no false Hands readiness, and cleanup of only GUI-owned processes.

Existing workstation and Eyes launcher tests remain regression coverage. Add Hands tests without weakening those assertions.

Integration-level tests must simulate:

- GUI before Fusion, then Fusion becoming ready;
- each provider process dying independently;
- Shimmer overlay absent, valid, and hash-mismatched;
- Hands reconnect/session-generation invalidation;
- Stop/close terminating only owned processes;
- token reuse through the existing DPAPI abstraction.

Before live deployment, run the focused launcher/runtime tests, then the full repository suite and an independent read-only review.

Live acceptance is performed only on disposable Fusion documents. The final gate requires all three nodes online, Hands public capability truth consistent with qualification state, `pending_commands=0`, `uncertain_operations=[]`, and protected documents unchanged.

## Non-Goals

This change does not:

- auto-launch Fusion 360;
- auto-launch with Windows;
- replace Development Bridge provider routing;
- replace Autodesk MCP, PERISCOPE, or Shimmer;
- introduce a new public CAD API;
- persist Hands qualification on Windows;
- add a generic remote shell or arbitrary-code channel;
- require `.exe` packaging for acceptance.
