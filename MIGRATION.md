# Migration plan

Development Bridge will be introduced through sequential, independently
verified stages. A stage must leave the server runnable and must be reported
before work starts on the next stage.

## Stage 0.5 — repository preparation

- preserve the active MCP code as the migration baseline;
- exclude production state and secrets;
- add packaging, documentation, planned package boundaries, and test skeleton;
- make no production deployment changes.

## Stage 1 — Bridge Core Foundation

Status: complete.

Add validated settings, the project and repository registries, structured
results and errors, request IDs, audit and capability interfaces, and the
`bridge_info`, `project_list`, `project_describe`, and `repository_status`
tools.

## Stage 2 — File Service

Status: complete.

Add repository-scoped `file_list`, `file_read`, and `file_search` with path,
symlink, size, and output boundaries.

## Stage 3 — Git Read Layer

Status: complete.

Complete the shared Git service and add structured `git_diff`, `git_log`,
`git_show`, and `git_refs` operations.

## Stage 4 — Controlled Changes

Status: complete.

Add revision calculation, repository locking, validated change plans, and
idempotent application of changes.

## Stage 5 — Task and Job Engine

Status: complete.

Add registered task profiles and durable asynchronous jobs. Arbitrary shell
commands are not part of the target API.

## Stage 6 — Git Write Operations

Status: complete.

Add explicit staging, guarded commits, push plans, and non-force pushes with
revision, idempotency, capability, and audit checks.

The completed API exposes `git_stage`, `git_commit`, `git_push_plan`, and
`git_push` through explicit project and repository selection. Stage and commit
guards are optional but strict when supplied; commit always consumes only the
existing index. Push is restricted to a named local branch and an exact remote
branch snapshot, supports only creation and fast-forward, and cannot merge,
rebase, or force. The unsafe global-workspace legacy commit and push adapters
were replaced by the v1 tools under their existing names.

## Stage 7 — Legacy migration

Route existing MCP tool names through the new services. Legacy adapters remain
temporarily available and cannot bypass v1 safety controls. GitHub becomes an
optional integration rather than a core runtime dependency.

## Deployment

Migration of systemd, Caddy, credentials, and production traffic is a separate
deployment activity after the corresponding application stage is verified. It
is not part of repository preparation.
