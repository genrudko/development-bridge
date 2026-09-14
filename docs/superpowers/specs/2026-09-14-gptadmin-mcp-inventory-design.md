# GPTAdmin MCP Inventory Design

**Date:** 2026-09-14
**Status:** Accepted for implementation

This document defines the local GPTAdmin target inventory for this VPS.
## Intent

GPTAdmin is the canonical local MCP hub. Today only `development-bridge` is present in its registry, while other MCP capability surfaces are still separate.

The desired state is one local inventory with stable names, clear preferred facades, persistent user services, and read-only acceptance checks.

## Target inventory

- `development-bridge`: Development Bridge, already connected through the OAuth-aware relay.
- `engineering`: Engineering Hub on `127.0.0.1:8797`; this is the preferred engineering facade.
- `drawio-app`: the dedicated Draw.io MCP App on `127.0.0.1:8791`.
- `audio`: Audio Analysis MCP on `127.0.0.1:8798`.
- `vps-shell`: the existing Local Shell MCP capability on `127.0.0.1:18765`.
- `browser-vps`: the existing Playwright MCP service on `127.0.0.1:8931` when enabled.
The five Engineering Hub backends (`drawio`, `iec`, `power`, `kicad`, `spice`) remain nested capability providers behind `engineering`. They are part of the inventory but are not duplicated as normal GPTAdmin targets because the existing hub already provides compact discovery and lazy lifecycle management for them.

Windows/Fusion providers remain represented through Development Bridge until a standalone Windows GPTAdmin relay is deployed. A later external-host target may expose diagnostics, but normal Fusion mutation must continue through Bridge guards.

## Runtime contract

Local HTTP MCPs use the same proven GPTAdmin `generic_stdio_mcp_relay.py` pattern with `mcp-remote` and `ndjson`. Each persistent relay is a user-systemd service that depends on `gptadmin-hub.service` and the relevant upstream service when that upstream is normally persistent.

The browser target is allowed to be on-demand; its relay must not force the ReviewGPT wake browser profile to become a general automation browser.

Target names are API contracts. Renaming a target requires a documentation and compatibility update rather than an ad-hoc service edit.

## Safety boundaries

GPTAdmin is a transport and federation layer. It does not replace Development Bridge policy. Git/GitHub guarded writes, durable jobs, coordinator semantics, and Fusion safety remain Bridge-owned.

The `engineering` target is preferred over direct backend access. `drawio-app` is separate because it provides the richer interactive MCP App surface.
## Acceptance

The inventory is accepted when:

1. GPTAdmin discovery shows every target above with the expected name and status.
2. `tools/list` succeeds for each online target.
3. One read-only tool call succeeds for each target that has a harmless probe.
4. Restarting the hub and persistent relay services restores the same target set without interactive OAuth for Development Bridge.
5. Closing SSH does not remove the persistent targets.
6. Existing Bridge and Engineering safety/facade rules remain unchanged.

## Source of truth

The operational target list and exact service mapping are documented in `docs/operations/gptadmin-mcp-inventory.md`. The runtime user-unit files are deployment state; they must agree with that document and with `/home/eodadmin/START_HERE.md`.
