# ChatGPT Browser Host

This directory turns the proven Xvfb + ordinary Chrome cold-wake PoC into a managed browser host for Development Bridge.

## Milestone 1: durable browser host

Implemented here:

- ordinary headful Chrome on a local Xvfb display; no `--headless` mode;
- one persistent authenticated Chrome profile;
- one current physical ChatGPT conversation URL for the logical route;
- CDP health checks bound to `127.0.0.1` only;
- automatic correction if Chrome drifts to another ChatGPT page;
- recovery of the coordinator MCP App from ChatGPT virtualized history after browser reload/restart;
- closure of extra ChatGPT page targets to avoid X claim races;
- X polling health verification from the VPS address through the Bridge journal;
- state snapshot in `~/.local/state/development-bridge/browser-host/state.json`;
- `healthcheck` command with non-zero exit when state is stale/unhealthy;
- user-systemd unit with restart-on-failure;
- fail-closed behavior on login/security challenges. The host never bypasses Cloudflare, Turnstile, CAPTCHA, Sentinel, or other protections.

The current `BROWSER_HOST_TARGET_URL` is intentionally only a **bootstrap physical binding**. It proves and stabilizes transport. It must not become the public address of the Telegram integration.

## Runtime layout

```text
~/.local/lib/development-bridge/browser-host/browser_host.py
~/.config/development-bridge/browser-host.env
~/.config/systemd/user/chatgpt-browser-host.service
~/.local/state/development-bridge/browser-host/state.json
```

One-time boot prerequisite for a per-user service on a VPS with no permanent login session:

```bash
sudo loginctl enable-linger "$USER"
```

Then:

```bash
systemctl --user daemon-reload
systemctl --user enable --now chatgpt-browser-host.service
```

Health check:

```bash
set -a
. ~/.config/development-bridge/browser-host.env
set +a
~/.local/chrome-cft/venv/bin/python \
  ~/.local/lib/development-bridge/browser-host/browser_host.py healthcheck
```

## Milestone 2: chat discovery and logical routing

Implemented baseline:

- persistent logical route registry shared by Bridge and Browser Host;
- generation-specific X channels on route takeover, so stale conversations cannot claim new-route events;
- Telegram `/chats`, `/to <route>`, and one-shot `@<route> message`;
- coordinator `coordinator_route_takeover` tool for moving a logical route to a replacement ChatGPT conversation;
- Browser Host dynamically follows the route registry instead of requiring a service/env rewrite;
- authenticated DOM discovery continuously records visible ChatGPT conversation links in `chat-registry.json`; `/chats` exposes a bounded recent view.

Remaining discovery expansion is incremental: project-title enrichment plus deliberate `Show more`/project-expansion passes for chats that are not currently rendered.

### ChatGPT Web request governor

ChatGPT Web is treated as a low-frequency reasoning surface, not an event bus. Durable job completions are debounce-batched before X delivery, and a successful `ui/message` transport ACK starts a persisted global cooldown across logical routes before another wake may be claimed. Browser Host also detects visible ChatGPT rate-limit dialogs (`Too many requests` / localized equivalents), writes shared `web-backoff.json`, and Coordinator suppresses new X claims until that backoff expires. Repeated detected limits use bounded 120s -> 240s -> 300s backoff.

Transport failures may still retry the same X delivery, but an already accepted `ui/message` is never deliberately redelivered just because model ACK is delayed.

### Browser chat discovery

Use the already authenticated ordinary ChatGPT page as the discovery source. Read sidebar/project DOM and build a bounded registry with at least:

```text
title
project_title
project_id
conversation_id
url
last_seen
```

Discovery must handle project expansion, `Show more`, and lazy/virtualized sidebar content instead of assuming all chats are present in the initial DOM.

### Logical routes

Telegram and other external sources address a stable logical route such as `ad5x`, `bridge-dev`, or `eod`, never a permanent `conversation_id`.

```text
Telegram -> route_id -> route registry -> active conversation -> Browser Host
```

A route record should carry an active generation/lease so an old open conversation cannot steal a new event after takeover.

### Chat rollover / takeover

Automatic physical-chat rollover is fail-safe and generation-scoped. `coordinator_route_rollover_prepare` reserves the next generation without modifying the active route. Browser Host then uses ChatGPT's supported **Branch in new chat** turn action, verifies that the candidate remains in the same project, binds the candidate's coordinator MCP App to the reserved generation channel, and requires real X polling before any route mutation.

Before commit, the successor also performs a native-listener preflight: the successor model must call `coordinator_x_mount` for the reserved channel and Browser Host must observe a new coordinator iframe in that preflight turn. This avoids making the new route depend only on MCP App cards copied from the source branch, which ChatGPT may fail to rehydrate.

Only after candidate URL/ID, control binding, native mount, and X polling all pass does Bridge atomically commit the new route generation. A durable post-commit bootstrap is operation-id deduplicated by the MCP App and resumes from `coordinator_route_context_get`. Failures before commit abort the pending rollover and restore the old physical conversation; the old route remains canonical throughout verification. Manual takeover is rejected while an automatic rollover is pending.

The intended state machine is:

```text
active gN
  -> prepare gN+1 (active unchanged)
  -> branch candidate
  -> verify exact URL/project
  -> bind candidate MCP App to gN+1
  -> verify X polling
  -> native successor coordinator_x_mount preflight
  -> commit route gN+1
  -> durable successor bootstrap / complete
```

### Address switching

Planned Telegram UX:

- `/chats` — show discovered/registered logical destinations;
- `/to <route>` — change the default destination for ordinary messages;
- `@<route> message` — address one message without changing the default;
- route takeover command from the active ChatGPT coordinator when a new conversation becomes canonical.

### Browser activation

After logical routing exists, the browser should stop being permanently pinned to one chat. It should open the active conversation for the requested route, wait for the X listener heartbeat, deliver/ACK the event, and may idle-stop later.

The browser is only a supported-host activator/navigation layer. Message text continues to move through Bridge + MCP App `ui/message`; no DOM textarea bot or reverse-engineered protected ChatGPT write API is part of this design.

## Route Context continuity

Logical routes also have a durable compact checkpoint in `route-contexts.json` next to the route registry. The checkpoint is independent of any one ChatGPT conversation and is intended to carry role, current goals, decisions/invariants, live repo/runtime coordinates, open work, and the next action across chat rollover.

Coordinator tools:

- `coordinator_route_context_get` returns the current checkpoint plus a bootstrap message for a logical route.
- `coordinator_route_context_update` atomically replaces the checkpoint and supports `expected_revision` to prevent lost updates.
- `coordinator_route_takeover` now returns the checkpoint/bootstrap payload together with the new generation X channel, so a replacement physical conversation can resume the logical route without treating the old transcript as the source of truth.

Keep Route Context compact and authoritative. Prefer live repository/runtime evidence when it supersedes a stale checkpoint, then update the checkpoint after the milestone.
