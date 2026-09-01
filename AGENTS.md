# Development Bridge Agent Rules

## Scope

This repository implements Development Bridge.
Do not modify external production deployments unless explicitly requested.

## Economy Mode

Treat model/tool round-trips, coordinator chat context, and live ChatGPT Web traffic as scarce resources.

- Plan before calling tools. Prefer one bounded work cycle: inspect exact state -> make the smallest scoped change -> run targeted verification -> emit a concise result.
- Do not conduct a conversational shell session. Batch related read-only probes and related edits/tests into one bounded job when they share the same decision boundary.
- For work lasting more than a few seconds, prefer durable execution. Do not poll jobs at short intervals; use event-driven wake when available, otherwise sparse checkpoints.
- Search/list first, then read only relevant files or ranges. Do not re-read unchanged files, repository status, schemas, or logs unless new evidence requires it.
- Keep output bounded with grep/tail/sed, explicit limits, diff --stat/diff --check, and targeted tests. Do not dump full logs or generated files into coordinator chat unless the result itself requires them.
- Reuse known tool schemas and runtime state. Do not repeat discovery or capability checks unless the runtime actually changed.
- Report only meaningful checkpoints: blocker, decision, verification result, commit/deploy result, or final outcome. Do not narrate every tool call.
- Treat ChatGPT Web / Browser Host interactions as especially expensive. Finish design, code review, and offline tests first; prefer one deliberate live acceptance. Never retry live UI actions during rate-limit/backoff.
- If you delegate to another LLM executor, pass one bounded outcome with exact scope, invariants, tests, stop conditions, and this Economy Mode. Do not make the coordinator dispatch each substep.

### VPS-first and tool-call discipline

- Treat the VPS as the default execution environment for repository work. File inspection, `grep`/`rg`, Git reads, builds, tests, log filtering, and ordinary diagnostics belong on the VPS whenever they can answer the question there.
- Do not spend an MCP/ChatGPT/browser round-trip on work that can be completed by one bounded VPS command or durable repository job. Bridge tools are for orchestration, durable lifecycle, registered-repository access, privileged Bridge-native operations, and evidence that cannot be obtained safely from the executor shell.
- Do not repeat the same tool call, schema lookup, status read, log query, or capability probe without a new reason. A repeat is justified only by a state-changing event, new evidence, a documented retryable failure, or an explicit need for data the previous result did not contain.
- Batch reads and diagnostics that share one decision boundary. Prefer one bounded `repository_exec`/`run_command` that gathers the exact Git state, filtered logs, relevant files, and test evidence over a sequence of near-identical calls.
- A generic busy signal is not proof that a particular job is still running. Inspect the durable job by ID before attributing repository occupancy to it.

### Coding-executor operating contract

- Every coding agent receives one complete bounded engineering outcome, not an interactive sequence of micro-steps. The task must include scope, invariants, acceptance tests, stop conditions, and explicit permissions for commit/push/deploy/PR actions.
- Read this `AGENTS.md` before editing. Inspect only the files and context required for the current decision; do not opportunistically refactor unrelated code.
- Work locally on the VPS first. Use repository files, Git, tests, linters, build tools, and bounded logs directly. Do not ask the coordinator to proxy ordinary shell work through repeated tool calls.
- Do not push, merge, deploy, create or update a PR, rewrite remotes, or alter repository topology unless the current task explicitly authorizes that exact action.
- Do not retry a failed executor run automatically. First classify whether the failure is repository/test evidence, executor infrastructure, auth/quota, or a proven retryable transient. A second executor job requires new evidence or an explicit coordinator decision.
- Before handoff, run a mandatory debug sweep, not just the first green test: reproduce the original failure/acceptance condition, exercise the normal success path, exercise the nearest relevant failure/edge path, inspect bounded logs/output for unexpected warnings, run targeted regression tests plus the closest affected tests, and run `git diff --check` plus final status/diff review. If a live UI/E2E is required, run it only after offline review/tests are green and only once unless new evidence justifies a repeat.
- Treat the debug sweep as an attempt to falsify the fix. If it exposes a defect, repair it and repeat only the affected offline checks before the final full bounded verification. Do not hand a known flaky or partially diagnosed result to the coordinator as complete.
- Executor output is evidence, not acceptance. The coordinator reviews the diff, verification evidence, and permissions before any privileged Bridge-native write.
- Detailed executor guidance is in `docs/operations/executor-operating-contract.md`.

## Evidence-First Bridge Semantics

Treat Development Bridge behavior as something to verify from its tools/runtime/code, not infer from shell symptoms or the compact surface.

- A compact tool surface does not mean a capability is unavailable. Before declaring a Bridge capability missing, use `bridge_search -> bridge_schema -> bridge_call` for hidden capabilities.
- Shell credentials are not evidence of Bridge authentication. `gh` being unauthenticated or an ordinary shell `git push` lacking credentials does not prove Bridge cannot write; Bridge credentials are intentionally kept out of executor shells and applied inside Bridge-native operations.
- Use Bridge-native write paths when they exist. Do not use shell `git push`, `gh auth`, ad-hoc PAT files, embedded credentials, or credential workarounds to replace `git_push` / GitHub host tools.
- Do not mutate `origin`, other remotes, workspace registration, repository aliases, or repository topology merely as a diagnostic experiment. Record the current topology first and change it only after evidence proves that topology is the root cause.
- Keep GitHub identity and Git push semantics separate. GitHub identity/status helpers may resolve the repository from `origin`; `git_push` executes the exact unchanged push plan against the configured remote named in that plan. Never infer an origin-only push restriction from identity behavior.
- An error code is evidence, not a diagnosis. For failures such as `GIT_PUSH_REJECTED`, `GIT_PUSH_PLAN_INVALID`, `REVISION_CONFLICT`, or `POLICY_VIOLATION`, capture the exact tool, error code/details, relevant plan/revision, local and remote branch/head, and remote URL before naming the cause.
- Test one hypothesis with the smallest discriminating check. If evidence disproves it, discard the hypothesis; do not stack a workaround on top of it.
- If the operator says infrastructure or credentials are already configured, verify hidden capabilities, config, and live runtime before contradicting that statement based on shell behavior.
- A blocker must be proven. A blocker report must name the exact tool and error code/details, list the facts already checked, and explain why no safe Bridge-native path remains. "Looks like no access" is not a blocker.

## Workflow

- Work only inside current repository.
- Commit completed milestones.
- Keep changes incremental.
- Do not skip tests.
- Do not start the next phase before the current phase is accepted.

## Safety

Never:
- modify /etc/systemd without explicit request;
- modify production development-mcp;
- expose secrets;
- commit tokens;
- change SSH configuration.

## Architecture

Follow:
- tools are MCP adapters only;
- business logic belongs in services;
- repository selection through registry;
- no global workspace state.
