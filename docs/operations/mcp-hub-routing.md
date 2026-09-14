# MCP Hub Routing Contract

GPTAdmin is the canonical local MCP hub for Development Bridge and future VPS-side MCP providers. Executors must treat the hub topology as part of the runtime contract, not as an optional convenience layer.

## Canonical topology

```text
ChatGPT -> Remote Desktop Commander -> VPS -> GPTAdmin -> development-bridge -> Development Bridge

VPS executor -> GPTAdmin -> development-bridge -> Development Bridge
```

GPTAdmin listens locally on `127.0.0.1:9001`. The canonical GPTAdmin target for Development Bridge is `development-bridge`.

After reaching that target, `bridge_guide` is the first Bridge tool to call in a new coordinator context. Hidden Bridge capabilities remain discoverable through `bridge_search -> bridge_schema -> bridge_call`.

## Naming boundary

Do not conflate these identifiers:

- GPTAdmin `agent_id=development-bridge` selects the Development Bridge MCP server behind the hub.
- Development Bridge logical `route_id=bridge` selects the coordinator route inside Development Bridge.

The first is MCP transport routing. The second is coordinator conversation routing.

## What is not canonical

Do not treat the ChatGPT custom `Dev_Bridge` namespace as the authoritative ingress. It may be used when present, but its disappearance proves only that the current ChatGPT turn lost that binding; it does not prove that Development Bridge or its OAuth endpoint is down.

Normal executors must not create their own `mcp-remote` process, connect directly to `https://mcp.vigilante.website/mcp`, re-register OAuth clients, or repair Bridge OAuth state. Those paths bypass the hub routing contract and create duplicate transport state.

GPTAdmin is only the transport/federation layer. It does not weaken or replace Development Bridge policy. Guarded Git/GitHub writes, durable jobs, coordinator wake/ACK, Fusion revision/capability/transaction safety, and other Bridge-owned invariants must still execute through Development Bridge.

## Failure and fallback order

When Bridge access appears missing, diagnose in this order:

1. Verify GPTAdmin Hub is reachable and the `development-bridge` target is online.
2. Verify the target exposes Bridge tools and call `bridge_guide` once.
3. If GPTAdmin is unhealthy, inspect the GPTAdmin/relay user services and bounded logs before changing transport state.
4. Use the direct `RDC -> bridge-rescue -> Development Bridge` path only as an operator/coordinator emergency fallback or a bounded diagnostic. Do not promote that fallback into a second normal executor ingress.

The persistent user services are `gptadmin-hub.service` and `gptadmin-development-bridge.service`. Their runtime is independent of an interactive SSH session when the user systemd manager is running with linger enabled.

## Executor rule

Executors working on the VPS should perform ordinary repository work locally. When a Bridge-native capability is required, route that capability through GPTAdmin target `development-bridge`. Do not ask the owner to repair a missing ChatGPT MCP namespace, copy OAuth material, or start an ad-hoc transport merely because the direct namespace is absent.
