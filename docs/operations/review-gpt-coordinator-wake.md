# ReviewGPT Coordinator Wake Operator Runbook

## Production role

`review-gpt` is the accepted primary direct wake transport for the Development Bridge coordinator. It runs on the VPS and creates a tiny committed user turn in the exact authoritative ChatGPT Project conversation. Work / Cloud Browser is a proven independent fallback path, not the default per-job transport.

The durable continuation state remains owned by `CoordinatorService`; ReviewGPT is only a delivery backend. Never create a second wake outbox or resend an uncertain submission through another transport.

## Exact target identity

Every direct wake must use both:

- the registered conversation UUID; and
- the authoritative Project route URL, e.g. `https://chatgpt.com/g/<project>/c/<conversation-id>`.

Do not replace the Project URL with a guessed canonical `/c/<conversation-id>` route. Preflight must navigate the authoritative route and verify the exact conversation identity. ReviewGPT accepts both plain and Project conversation URL forms for same-thread identity, but Bridge production targeting remains authoritative-Project-URL first.

## On-demand browser lifecycle

The ReviewGPT Chromium/Xvfb runtime is on-demand:

1. start the configured user browser/Xvfb units for probe/delivery;
2. navigate/preflight the exact Project route;
3. send only after exact-thread, idle/native-not-generating checks pass;
4. require a deterministic committed-turn receipt;
5. stop Chromium/Xvfb after the attempt;
6. verify no owned browser/Xvfb processes remain when diagnosing resource leakage.

Do not keep a persistent Chromium process merely to save startup time. Persistent browser experiments accumulated excessive tabs/processes/RSS and are not the accepted production topology.

## Wake payload and ACK

The user turn stays tiny and references the durable continuation ID. On a fresh model turn, call `coordinator_ack(<continuation_id>)` before continuing other work, process any returned `batched_messages`, then inspect the durable job/result once.

Do not paste full job output into the wake prompt. The job database remains the source of execution evidence.

## Authentication recovery

If ChatGPT authentication expires, the ReviewGPT profile may redirect an exact Project route to the ChatGPT home page and show session-expired/OAuth-invalidated state. Treat this as operator input, not a reason to resend or rewrite routes.

Recovery procedure:

1. stop automatic retry/resend;
2. expose the existing ReviewGPT Chromium profile to the operator using the established local/X11 method; never expose cookies/tokens or a public unauthenticated VNC endpoint;
3. operator logs into ChatGPT manually;
4. stop the temporary interactive browser cleanly so the profile persists;
5. run one read-only exact-Project preflight with no send;
6. require `ready=true` before resuming direct wakes;
7. confirm the on-demand browser/Xvfb shuts down after the probe.

## Failure semantics

- `delivered`: committed receipt proves the exact user turn; wait for model ACK.
- `not_submitted`: only a proven clean pre-submit failure may enter bounded retry policy.
- `uncertain`: submission may have occurred; automatic resend and cross-transport fallback are forbidden.
- `owner_input_required`: stop and surface operator browser/auth action.

A terminal job may be either `succeeded` or `failed`; both are valid wake triggers according to the waiter policy. Do not infer that a generic repository `JOB_BUSY` result means the particular wake job is still running; inspect that durable job ID directly.

## VPS-first diagnostics

Diagnose delivery from VPS evidence before touching ChatGPT UI:

- durable job status/output by exact job ID;
- coordinator pending/continuation state;
- filtered service log lines for that continuation ID;
- deterministic receipt existence and timestamp;
- browser/Xvfb unit state and owned process count.

Batch these checks into one bounded VPS command where practical. Do not issue repeated equivalent Bridge tool calls or UI probes unless state changed or the previous result was retryably incomplete.

Use live ChatGPT/UI inspection only when VPS evidence cannot establish the required browser/auth/thread state.

## Accepted live evidence (2026-09-01)

Production acceptance after Project-route fixes:

- 5/5 sequential real terminal-job wakes delivered to the same physical Project conversation;
- first-to-fifth committed-wake span: more than 70 minutes;
- each observed delivery used one delivery attempt and produced its own committed receipt;
- no duplicate or out-of-order wake was observed;
- Chromium/Xvfb returned to inactive with zero owned processes after checked deliveries;
- a separate intentional `exit 7` / `nonzero_exit` job also delivered correctly, proving the failure-terminal path;
- no repeated manual login was required after the initial profile re-authentication.

Work / Cloud Browser independently passed a 5/5 soak including a failure-terminal event, but consumed observable Work quota and therefore remains a fallback/independent recovery path rather than the primary routine transport.

## Change gate

Before changing ReviewGPT wake code or runtime behavior:

1. design/review offline;
2. run targeted tests and neighboring regression tests;
3. perform the coding-executor debug sweep from `docs/operations/executor-operating-contract.md`;
4. restart Bridge only through the guarded idle restart path;
5. run one read-only preflight;
6. run the smallest necessary live acceptance once.

Do not use repeated live ChatGPT sends as a debugging loop.
