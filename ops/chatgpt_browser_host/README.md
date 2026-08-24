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

When a ChatGPT conversation reaches its practical end, register the new conversation as the next generation of the same logical route. Pending events belong to the logical route, not to the old physical conversation, so rollover does not require Telegram reconfiguration.

### Address switching

Planned Telegram UX:

- `/chats` — show discovered/registered logical destinations;
- `/to <route>` — change the default destination for ordinary messages;
- `@<route> message` — address one message without changing the default;
- route takeover command from the active ChatGPT coordinator when a new conversation becomes canonical.

### Browser activation

After logical routing exists, the browser should stop being permanently pinned to one chat. It should open the active conversation for the requested route, wait for the X listener heartbeat, deliver/ACK the event, and may idle-stop later.

The browser is only a supported-host activator/navigation layer. Message text continues to move through Bridge + MCP App `ui/message`; no DOM textarea bot or reverse-engineered protected ChatGPT write API is part of this design.
