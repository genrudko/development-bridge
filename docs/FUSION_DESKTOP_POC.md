# Autodesk Fusion desktop relay (Milestone 1)

This proof of concept keeps Autodesk Fusion's MCP endpoint local to Windows.
The Windows agent initiates outbound HTTPS requests to Development Bridge; do
not publish or tunnel `127.0.0.1:27182` to the internet.

## Bridge

Set one long random shared token in the server's secret environment:

```text
DEVELOPMENT_BRIDGE_DESKTOP_NODE_TOKEN=<random-token>
```

Optional YAML keys under `desktop_nodes` are
`offline_after_seconds` (45), `claim_timeout_seconds` (25),
`call_timeout_seconds` (300), `max_pending_commands` (32),
`max_request_bytes` (262144), `max_arguments_bytes` (131072),
`max_result_bytes` (1048576), optional `journal_path`, `journal_history_limit`
(200), and `journal_max_bytes` (5242880). Without the token, agent HTTP routes return 404
and the Fusion MCP tools fail closed as not configured.

## Windows 10/11 with Python 3.12

1. In Fusion, open **Preferences > General > API**, enable the local MCP/API,
   and leave Fusion running. Its normal endpoint is
   `http://127.0.0.1:27182/mcp`; a Fusion setting or `FUSION_MCP_URL` can
   override it.
2. Copy this repository (or at minimum the agent module plus matching
   dependencies) to Windows, create a Python 3.12 virtual environment, and run
   `py -3.12 -m pip install "mcp==2.0.0"`.
3. In PowerShell, configure and start the outbound agent:

```powershell
$env:DEVELOPMENT_BRIDGE_URL = "https://bridge.example"
$env:DEVELOPMENT_BRIDGE_NODE_ID = "fusion-workstation"
$env:DEVELOPMENT_BRIDGE_DESKTOP_NODE_TOKEN = "<same-random-token>"
# Optional: $env:FUSION_MCP_URL = "http://127.0.0.1:27182/mcp"
py -3.12 agents\windows_fusion_agent.py
```

4. From the Development Bridge MCP client, call
   `fusion_node_status`, then `fusion_tools`, then `fusion_call` using exactly
   one discovered tool name and JSON object arguments.

If Fusion is closed or its MCP endpoint is disabled, the agent reports the node
unavailable when it can reach Bridge and retries both connections. While a Fusion
tool call is running, a separate 10-second keepalive prevents the node from being
marked offline. Fusion MCP reads are bounded to 285 seconds by default and the
Bridge call waits up to 300 seconds. A stale late result is discarded without
tearing down an otherwise healthy Fusion session. Calls still only invoke
dynamically discovered Fusion tools; there is no arbitrary command or target-URL
facility. Do not blindly retry a mutating CAD command after an uncertain timeout:
inspect the model first because Fusion may have completed the operation locally.
## Reliability rules for CAD mutations

Treat CAD writes as non-idempotent unless the script explicitly proves otherwise.
A timeout or lost response is an uncertain outcome: Fusion may already have applied
the feature locally, so inspect the timeline/BRep (and preferably a screenshot)
before deciding what to do next. Never transparently replay a mutating command.

Prefer small deterministic mutations that normally finish well below the transport
timeout. Split repeated geometry into bounded batches (roughly 5-10 complex
profiles/features per call is a practical starting point), give generated sketches
and features stable names, and verify the model after each batch. Reads and
screenshots can remain direct. Saving the Fusion document remains an explicit
user action; relay recovery must not silently save or overwrite a design.

## Durable CAD operation journal and checkpoints

Configure `desktop_nodes.journal_path` outside every registered repository, for
example `/home/eodadmin/.local/state/development-bridge/fusion-operations.jsonl`.
Each `fusion_call` then records a bounded durable operation snapshot with the
command/tool identity, SHA-256 of arguments/result, mutation flag, timestamps, and
state (`queued`, `claimed`, `succeeded`, `failed`, `timed_out`, `cancelled`,
`orphaned`, `interrupted`, `uncertain`, `late_succeeded`, or `late_failed`). `fusion_node_status` exposes the
last/recent operations and unresolved `uncertain_operations`.

For important CAD work, supply `journal` metadata on `fusion_call`:

```json
{
  "operation_id": "op-ajour-long-01",
  "summary": "Cut long-wall ajour batch 1",
  "mutation": true,
  "parent_operation_id": "op-ajour-precheck-01",
  "checkpoint": {
    "expected_features": ["Ajour_Reference_Full_Long_Walls"],
    "verification": "BRep loops + screenshot after mutation"
  }
}
```

The `checkpoint` object is deliberately generic and bounded: the coordinator can
record stable feature names, before/after state summaries, expected BRep facts, and
screenshot verification intent without persisting large image/base64 payloads. Use
linked read/screenshot calls with `parent_operation_id` for actual verification.

A claimed mutating command whose caller times out becomes `uncertain`, and the
timeout is non-retryable. If its result arrives later, even after a Bridge restart,
the durable command/operation mapping reconciles it to `late_succeeded` or
`late_failed`. On Bridge startup, a persisted `claimed` mutation is proactively
recovered as `uncertain`; an unclaimed queued command becomes `orphaned`. This
resolves ambiguous restarts without replaying the CAD mutation.

After Fusion has produced a result, the Windows agent retries delivery across
transient network/Bridge outages with capped exponential backoff. It blocks new
claims while preserving that completed result in memory; only delivery is retried,
never the CAD command itself. If the agent/process is lost entirely, the durable
server journal intentionally remains `uncertain` and requires model inspection.
