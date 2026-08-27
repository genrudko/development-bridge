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
