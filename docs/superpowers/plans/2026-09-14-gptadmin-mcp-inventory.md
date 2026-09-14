# GPTAdmin MCP Inventory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put every existing VPS MCP capability surface behind stable GPTAdmin target names.

**Architecture:** Keep GPTAdmin Hub on `127.0.0.1:9001`. Reuse the proven generic stdio relay plus `mcp-remote` for existing HTTP MCP servers. Development Bridge remains the guarded orchestration facade; Engineering Hub remains the compact facade for its five internal backends.

**Tech Stack:** GPTAdmin Go Hub, generic stdio relay, `mcp-remote` 0.14.2, Node 22, user systemd, MCP Streamable HTTP.

**Spec:** `docs/superpowers/specs/2026-09-14-gptadmin-mcp-inventory-design.md`

## Global Constraints

- Do not modify upstream MCP business logic merely to register it in GPTAdmin.
- Use `ndjson` for the generic relay to `mcp-remote`.
- Keep all new listeners loopback-only.
- Do not expose secrets in unit files, logs, Git, or model-visible output.
- Engineering raw backends remain behind target `engineering`.
- Normal Fusion mutation remains behind `development-bridge`.

---
### Task 1: Runtime inventory

Document the current GPTAdmin target mapping and its owning MCP services before changing runtime state.
**Files:** `docs/operations/gptadmin-mcp-inventory.md`, `/home/eodadmin/START_HERE.md`

**Produces:** one canonical mapping for `development-bridge`, `engineering`, `drawio-app`, `audio`, `vps-shell`, and `browser-vps`.

- [ ] Read the current user-service state and listener map.
- [ ] Record upstream URL, owner service, auth mode, and target role.
- [ ] Confirm Engineering backends stay nested under `engineering`.
- [ ] Run `git diff --check` and commit the documentation change.
### Task 2: Local relay targets

Add persistent GPTAdmin relays for the existing local HTTP MCPs.

**Deployment files:** `gptadmin-engineering.service`, `gptadmin-drawio-app.service`, `gptadmin-audio.service` under the user systemd directory.

**Command shape:**
```text
python3 generic_stdio_mcp_relay.py --hub http://127.0.0.1:9001 --agent-id <target> --name <name> --stdio-format ndjson mcp-remote http://127.0.0.1:<port>/mcp
```

- [ ] Verify the upstream endpoint responds to MCP initialize before installing its relay.
- [ ] Validate each unit with `systemd-analyze --user verify`.
- [ ] Start the three relays and confirm GPTAdmin discovery shows `engineering`, `drawio-app`, and `audio` online.
- [ ] Call `tools/list` and one harmless read-only tool per target.
- [ ] Restart the three relays and repeat discovery once.
### Task 3: VPS shell target

Connect the existing Local Shell MCP as target `vps-shell` through its OAuth-aware MCP endpoint.

**Deployment file:** `gptadmin-vps-shell.service`.

**Interface:** the relay uses a dedicated `mcp-remote` callback port and its own persisted OAuth state; it must not reuse Development Bridge client registration.

- [ ] Start the relay once and complete the one-time OAuth authorization without exposing credentials in chat or logs.
- [ ] Confirm automatic token reuse on relay restart.
- [ ] Confirm GPTAdmin `tools/list` for `vps-shell` and execute one read-only system inspection.
- [ ] Close the interactive SSH session and verify the target remains online.

### Task 4: Browser target

Connect `eod-playwright-mcp.service` as `browser-vps` without sharing the ReviewGPT browser profile.

- [ ] Verify Playwright uses its dedicated profile and output directories.
- [ ] Add the GPTAdmin relay with an explicit dependency on `eod-playwright-mcp.service`.
- [ ] Confirm `browser-vps` discovery and `tools/list`.
- [ ] Run one read-only page/navigation smoke against a disposable page, then confirm the ReviewGPT browser units/profile were untouched.
### Task 5: Inventory acceptance

- [ ] Restart the GPTAdmin hub and its persistent relay services once.
- [ ] Confirm the canonical target set returns online.
- [ ] Verify `tools/list` across every online target.
- [ ] Record intentionally on-demand targets as such.
- [ ] Run final `git diff --check`, inspect status, and commit only intended documentation.
