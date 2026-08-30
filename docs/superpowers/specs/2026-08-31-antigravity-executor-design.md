# Antigravity Executor Integration Design

Date: 2026-08-31
Status: proposed design approved in chat; implementation pending written-spec review

## Goal

Add Google Antigravity CLI (`agy`) as an optional Development Bridge code executor alongside the existing Codex path. ChatGPT remains the coordinator. Executor choice is per bounded task and may be automatic or explicitly overridden.

## Non-goals

- Do not replace Codex.
- Do not make Antigravity the default for every task.
- Do not add browser-based ChatGPT transport dependencies.
- Do not enable paid overage/credit spending automatically.
- Do not expose Google account credentials, OAuth codes, or token material through Bridge logs, job output, or repository files.

## Architecture

Flow:

`ChatGPT -> Development Bridge -> executor selector -> {Antigravity | Codex}`

The selector owns only routing policy. Each executor adapter owns process launch, bounded input/output, timeout handling, and result normalization.

Antigravity should initially be integrated as a local VPS CLI executor using the installed `agy` binary. The first milestone should reuse the existing durable repository job model rather than introducing a second scheduler.

## Authentication

Official Antigravity CLI supports a remote SSH OAuth flow. On first launch over SSH, `agy` prints an authorization URL. The operator opens that URL locally, completes Google sign-in/2FA, receives an authorization code, and pastes it back into the SSH terminal.

This is the preferred bootstrap path for the VPS. Development Bridge must not automate, intercept, proxy, persist, or log the operator's 2FA challenge or authorization code.

If the authenticated session expires, executor health should report `auth_required` and stop. Re-authentication remains an explicit operator action.

Official reference:
- https://antigravity.google/docs/cli/install/

## Installation

Official Linux installer places `agy` in `~/.local/bin/agy`:

`curl -fsSL https://antigravity.google/cli/install.sh | bash`

Installation is a one-time operator-visible deployment action. Bridge should verify the resulting binary/version before registering the executor as available.

## Quota-aware routing

Antigravity exposes model quota state through `/usage` (`/quota`). The integration should treat quota as a routable resource rather than assume unlimited availability.

Minimum normalized executor state:

- `available`: binary and runtime callable
- `authenticated`: account session usable
- `busy`: active bounded task exists
- `model`: selected/current model if discoverable
- `quota_state`: `ok | low | exhausted | unknown`
- `remaining_fraction`: optional numeric value when machine-readable evidence is available
- `reset_time`: optional absolute reset time
- `last_error`: bounded diagnostic
- `last_success_at`: timestamp

Routing rules for milestone 1:

1. Explicit executor override wins if that executor is available, authenticated, and not quota-exhausted.
2. Automatic routing may select Antigravity when its quota state is `ok` and the task is suitable.
3. `low` quota should prefer Codex unless Antigravity was explicitly requested.
4. `exhausted` must not trigger retry loops; record reset timing if available and route elsewhere.
5. `unknown` is not equivalent to `ok`; automatic routing should fail conservative and prefer the known-good executor.
6. No automatic paid-overage enablement.

Official quota reference:
- https://antigravity.google/docs/cli/commands/usage

## Executor suitability

Milestone 1 should keep routing simple and observable. Antigravity is suitable for bounded repository implementation/review tasks that can run non-interactively or through a controlled CLI session. Codex remains the fallback and the preferred executor whenever Antigravity auth/quota/runtime state is uncertain.

Do not add speculative model-quality scoring in the first milestone. Collect execution evidence first.

## Safety and repository boundaries

- Preserve the current repository registry and durable job semantics.
- Never expose Bridge-native GitHub credentials to executor shells.
- Never allow an executor to rewrite Git remotes as a workaround.
- Respect AGENTS.md and per-task repository constraints.
- Pass one bounded task with explicit scope, invariants, tests, and stop conditions.
- Bound stdout/stderr and execution time.
- Treat executor output as evidence, not authority; coordinator remains responsible for review/acceptance.

## Proposed components

1. **Antigravity runtime probe**
   - locate `agy`
   - report version
   - distinguish missing binary vs auth-required vs callable runtime

2. **Antigravity executor adapter**
   - launch one bounded task in the selected repository
   - pass task prompt and repository constraints
   - normalize exit/result metadata
   - never echo secrets

3. **Executor status/quota probe**
   - obtain fresh quota information using supported CLI behavior
   - prefer a documented or stable machine-readable path if available
   - if only TUI output is available, do not implement brittle screen scraping as production behavior; mark quota `unknown` until a robust interface is found

4. **Executor selector**
   - explicit override plus conservative automatic fallback
   - no hidden paid-overage behavior

5. **Bridge surface**
   - compact executor status for coordinator use
   - executor choice recorded in job metadata/output
   - avoid adding many top-level tools if hidden capability/structured command fits existing compact-surface policy

## Error handling

- Binary missing -> `unavailable`
- Authentication required -> `auth_required`, operator action required
- Quota exhausted -> `quota_exhausted`, no retry loop
- Quota unknown -> conservative fallback to Codex for automatic routing
- CLI crash/timeout -> one bounded failure result, no blind retry
- Repository/test failure -> ordinary executor failure evidence; do not misclassify as Antigravity infrastructure failure

## Testing

Offline tests before any live Antigravity task:

- binary missing / binary present probe
- auth-required classification from fixture output
- quota `ok/low/exhausted/unknown` normalization
- explicit override routing
- conservative automatic fallback
- no retry when exhausted
- no secret/token leakage in normalized output
- bounded timeout/output behavior
- existing full Development Bridge suite remains green

Live acceptance after offline verification:

1. Operator completes one SSH OAuth/2FA login if required.
2. Bridge confirms Antigravity is authenticated and callable.
3. Read quota/status once.
4. Run one harmless bounded repository task with no Git push or deployment.
5. Confirm result normalization and executor attribution.
6. Do not repeat live acceptance if it passes.

## Rollout

Milestone 1: install/auth + runtime probe + explicit Antigravity execution + conservative quota-aware selector.

Milestone 2, only after evidence: improve automatic executor selection using observed reliability/cost/latency. Do not build speculative orchestration before milestone 1 is accepted.
