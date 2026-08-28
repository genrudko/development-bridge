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
`max_request_bytes` (262144), `max_arguments_bytes` (131072), and
`max_result_bytes` (1048576). Without the token, agent HTTP routes return 404
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
