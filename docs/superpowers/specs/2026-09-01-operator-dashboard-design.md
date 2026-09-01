# Development Bridge Operator Dashboard Design

**Status:** proposed production design for owner review.

## Context

The compact Development Bridge MCP App already exposes health, VPS resource usage, logical-route identity, and durable semantic work progress. Its configured widget domain is `https://mcp.vigilante.website`, and the public domain is already reverse-proxied by Caddy to the Bridge Starlette application on localhost.

The compact card should remain a small ChatGPT-native indicator. The public domain should become the owner-facing, password-protected, read-only operator dashboard that shows richer live state directly from the VPS without spending ChatGPT/MCP round-trips merely to render status.

## Goals

1. Make `https://mcp.vigilante.website/` the entry point for a full Development Bridge operator dashboard.
2. Keep the existing MCP endpoint and OAuth behavior unchanged.
3. Reuse Bridge's existing durable state and services rather than creating a second job/progress/wake state machine.
4. Provide live progress, current/recent jobs, executor attribution, Git state, coordinator wake state, and VPS resource state.
5. Provide a read-only live terminal view from bounded durable-job stdout/stderr.
6. Require an owner password before any dashboard data is returned.
7. Keep v1 strictly read-only: no arbitrary shell input and no operational buttons that mutate Bridge, Git, jobs, routes, or services.
8. Keep routine dashboard rendering VPS-first and independent of ChatGPT Web, Work, Browser Host, and MCP tool calls.

## Non-goals

- No interactive SSH/web shell in v1.
- No `Cancel`, `Retry`, `Push`, `Merge`, `Restart`, `Deploy`, route mutation, or executor-start controls in v1.
- No second job queue, progress store, coordinator outbox, or executor scheduler.
- No scraping ChatGPT Web for dashboard state.
- No periodic executor probe that consumes quota or creates external work merely to refresh the page.
- No replacement of MCP OAuth with the operator password; MCP and operator-dashboard authentication are separate surfaces.
- No new public listener or public port. Caddy remains the TLS edge and Bridge remains bound to localhost.

## Architecture

The operator dashboard is served by the existing Bridge Starlette process. This avoids another daemon, another health lifecycle, and another local port.

```text
Browser
  -> HTTPS / Caddy
  -> mcp.vigilante.website
  -> 127.0.0.1:8789 Development Bridge
       |- /mcp ... existing MCP + OAuth
       |- /ops/ ... operator dashboard HTML
       |- /ops/login ... owner password session
       |- /ops/api/snapshot ... authenticated JSON
       `- /ops/api/events ... authenticated SSE
```

The root path `/` redirects to `/ops/`. This makes the existing MCP App domain click land on the full dashboard without changing the public origin.

The dashboard backend is a focused read-only service. It composes snapshots from existing Bridge objects and small new read-only queries. It must not call MCP tools internally.

## Authentication

### Configuration

Add disabled-by-default operator-dashboard settings:

```yaml
operator_dashboard:
  enabled: false
  path: /ops
  password_hash: null
  session_secret: null
  session_ttl_seconds: 43200
  event_interval_seconds: 1.0
  recent_jobs_limit: 25
  terminal_tail_bytes: 32768
```

`password_hash` and `session_secret` are secrets supplied only through the VPS runtime configuration/environment. They are never committed.

Enabling the dashboard requires both values. Startup fails closed if the feature is enabled with incomplete authentication configuration.

### Password storage

Use Python stdlib `hashlib.scrypt`; do not add an authentication dependency solely for this feature.

The stored representation is versioned and self-contained:

```text
scrypt$N$r$p$salt_b64$digest_b64
```

Provide an operator-only CLI helper that prompts with `getpass`, confirms the password, generates a random salt, and prints only the resulting hash. The plaintext password never enters chat, argv, repository files, or logs.

### Session

On successful login, issue a signed stateless cookie named `__Host-dbridge_ops` with `Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/`, and an absolute expiry bounded by `session_ttl_seconds`.

The cookie payload contains only version, issued-at, expiry, and a random session nonce. Sign it with HMAC-SHA256 using `session_secret`; compare signatures with `hmac.compare_digest`. No bearer token is exposed to JavaScript.

### Login abuse control

Track failed login attempts in memory by effective client IP. Trust `X-Forwarded-For` only when the direct peer is loopback (the established Caddy topology); otherwise use `request.client.host`.

Permit at most 5 failed attempts per IP in a rolling 10-minute window. A successful login clears the counter for that IP. Rate-limit state is intentionally ephemeral and resets on Bridge restart.

### HTTP hardening

Every operator response uses `Cache-Control: private, no-store`. Dashboard pages and APIs set:

```text
default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'
```

No CORS headers are added to operator endpoints.

## Read-only snapshot model

Create an `OperatorDashboardService` that returns a bounded serializable snapshot. The service receives existing container services and small focused read-only providers.

### Bridge

Expose service name/version/API version, process uptime, compact/internal tool counts, and total project/repository counts.

### Route and progress

Use `RouteRegistry` and `RouteProgressStore` directly. Expose requested/default route, route title/channel/generation, and the existing progress operation ID/status/phase/current/next/detail/percent/revision. No new progress model is introduced.

### Jobs

Add a bounded read-only `JobStore.recent(limit, project_id=None, repository_id=None)` query ordered newest-first. It returns at most the configured limit and never includes full stdout/stderr.

Snapshot job data includes job ID, project/repository, task ID, lifecycle status, timestamps, exit code/failure reason, and executor/model/quota attribution. The first queued/running job is the current job; if none is active, the newest terminal job is the last job.

A dashboard read must never change admission, queue order, cancellation, timeout, or worker state.

### Executor

Routine dashboard refresh must not invoke `agy`, Codex, Work, ChatGPT Web, or another external executor probe.

For the current job, display persisted executor/model/quota attribution. If a fresh Antigravity quota cache already exists, the dashboard may display it through the existing quota parser, but it must not trigger a probe to refresh it.

### Git

Resolve the active repository from the current job, falling back to the newest recent job. If no job identifies a repository, Git state is absent rather than guessed.

Use a read-only Git snapshot provider cached for at least 5 seconds per repository. It reports branch, HEAD, clean/dirty, changed-file count, upstream, and ahead/behind when computable from existing local refs. It performs no fetch, pull, remote mutation, credential access, or network call.

### Coordinator wake

Add a read-only `CoordinatorService.operator_snapshot(channel_id)` that exposes state, continuation ID, delivery attempts/max attempts, transport-delivered flag/time, last transport name/disposition, owner-input-required flag, queued/batched counts, and relevant cooldown/backoff remaining time.

It does not claim, ACK, retry, authorize browser preflight, or mutate pending state. The dashboard service calls it for the selected route/channel only.

### VPS system state

Reuse/centralize existing `/proc`/disk metrics from the compact dashboard and add bounded observations: memory total/available, swap, root disk, load average, Bridge process uptime, ReviewGPT Chromium/Xvfb owned-process counts, and configured direct-wake transport summary. Optional metric failures render unavailable instead of failing the whole dashboard.

## Live terminal

The v1 Terminal tab is a read-only execution mirror, not SSH.

Source data is the durable current job's bounded `stdout` and `stderr` already captured by `JobStore`; the browser cannot send terminal input.

When output changes, SSE emits a `terminal` event with job ID/status, bounded UTF-8 tails for stdout/stderr, truncation flags, and timestamp. Only changed terminal data is emitted. Environment variables, command-line secrets, credentials, cookies, OAuth material, signed URLs, and arbitrary files are never included.

If no job is active, show the last job output once and mark the terminal idle. A future separately designed feature may mirror a controlled PTY/tmux session; that is outside v1 because it changes the exposure and threat model.

## Server-sent events

`GET /ops/api/events` is authenticated and uses `text/event-stream`.

The server loop emits an initial `snapshot`, recomputes lightweight state every configured interval, emits snapshot/terminal only when changed, emits a heartbeat comment every 15 seconds while idle, and exits promptly on disconnect/shutdown.

SSE is preferred over WebSockets because v1 is server-to-browser only. `GET /ops/api/snapshot` remains for initial load and diagnostics.

## User interface

The owner console uses local static CSS/JS only; no CDN dependencies.

### Header

Show Development Bridge status, current route, project/repository, executor/model, and active-job elapsed time.

### Overview

Semantic durable progress is primary: title/status, explicit milestone bar, completed/total/percent, phase, current, next, and detail. Never infer percent from elapsed time, CPU, log volume, or token use.

### Terminal

Monospace read-only stdout/stderr mirror. Preserve newlines, bound retained DOM text, auto-scroll only when the user is already near the bottom, and identify stderr visibly.

### Jobs

Show recent jobs with status, repository, executor/model, duration, and terminal reason. Selecting a historical job changes only the read-only view.

### Git

Show branch, abbreviated HEAD, clean/dirty, changed-file count, upstream, and ahead/behind. No diff body in v1.

### Wake

Show selected route/channel, continuation state, ReviewGPT disposition, attempts, awaiting-ACK state, and owner-input-required warning.

### System

Show RAM, swap, disk, load, process uptime, and ReviewGPT browser/Xvfb process counts.

## Relationship to the compact MCP App

The compact MCP App remains lightweight and continues to use its existing MCP resource-state mechanism. Because `openai/widgetDomain` already points to `https://mcp.vigilante.website`, serving `/` as a redirect to `/ops/` makes the domain click open the protected full dashboard.

The compact widget does not poll operator APIs and never carries dashboard credentials.

## Error handling

- Disabled dashboard: `/` and `/ops/*` return 404; `/mcp` remains unchanged.
- Unauthenticated HTML redirects to `/ops/login`; unauthenticated API/SSE returns 401 without data.
- Invalid/expired/tampered cookie is cleared and treated as unauthenticated.
- Repeated bad password returns 429 after the bounded limit.
- Optional source failure degrades only that panel.
- Job output decodes UTF-8 with replacement, matching current job semantics.
- SSE disconnect stores no retry state; EventSource can reconnect with the same authenticated cookie.

## Security invariants

1. Dashboard v1 has no arbitrary command execution path.
2. Dashboard v1 has no Bridge/Git/GitHub/job/coordinator mutation API except login/logout session handling.
3. Password plaintext is never persisted or logged.
4. Session secret/hash are never included in snapshots, exceptions, or audit payloads.
5. Job environment, Bridge credentials, OAuth tokens, ChatGPT cookies, and signed artifact URLs are never exposed.
6. Git inspection is local read-only and performs no network operation.
7. Dashboard refresh never invokes an executor or ChatGPT/Work/browser operation.
8. Existing `/mcp`, OAuth, coordinator wake, artifact, and desktop-node routes retain current authorization semantics.
9. Bridge remains bound to localhost behind Caddy; no new public service port is introduced.

## Testing

### Offline

Required coverage:

1. settings fail closed on incomplete enabled auth configuration;
2. scrypt hash/verify accepts correct password and rejects wrong/malformed values;
3. signed sessions enforce expiry/signature and reject tampering;
4. rate limiting trusts forwarded IP only behind loopback proxy;
5. unauthenticated root/dashboard leaks no snapshot data;
6. authenticated snapshot is bounded and contains Bridge/route/progress/job/Git/wake/system fields;
7. `JobStore.recent` is bounded/newest-first and read-only;
8. coordinator operator snapshot does not claim/increment/ACK;
9. Git provider performs no network command and respects cache;
10. SSE sends initial state, changed state/output only, and heartbeat while idle;
11. terminal output is bounded and carries truncation flags;
12. dashboard routes coexist with MCP OAuth/resource routes without changing current contract tests;
13. compact MCP App metadata still uses the same public domain;
14. local static assets and no-store/security headers are enforced.

Run targeted dashboard/auth/transport tests, nearest job/coordinator/compact/OAuth regressions, then the full Bridge suite under the existing bounded verification policy.

### Debug sweep

Before handoff follow `docs/operations/executor-operating-contract.md` and try to falsify the feature with correct/wrong passwords, expired/tampered cookies, rate-limit boundary, no-job state, queued/running/succeeded/failed jobs, stdout+stderr+truncation, clean/dirty/no-upstream Git, pending/delivered/owner-input-required wake fixtures, SSE reconnect/disconnect, and disabled-dashboard MCP health.

No public live test occurs until offline review/tests are green.

## Deployment and live acceptance

Deployment is a separate operator-visible gate after code review.

1. Install code/config with dashboard disabled.
2. Guarded idle restart; prove existing MCP health.
3. Operator runs the password-hash helper interactively on VPS; plaintext never enters chat.
4. Store hash plus separately generated session secret in established runtime config/environment.
5. Enable dashboard and guarded-restart while idle.
6. Verify `/mcp` and OAuth unchanged.
7. Open `https://mcp.vigilante.website/`, log in, and verify idle Overview/System/Wake.
8. Run one harmless bounded durable job and verify live progress/job/terminal SSE.
9. Run one harmless intentional failure and verify failed state without breaking the stream.
10. Open the compact MCP App domain and verify it lands on the same protected dashboard.
11. Logout and prove API/SSE unauthenticated behavior.
12. Confirm no new public listener and no persistent dashboard helper process outside Bridge/Caddy.

## Rollback

Set `operator_dashboard.enabled=false` and guarded-restart Bridge. Operator routes disappear while MCP, coordinator, jobs, and compact MCP App continue unchanged. No dashboard database or migration exists.
