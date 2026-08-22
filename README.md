# Development Bridge

Development Bridge is the successor repository for the former
`development-mcp` service. The staged Development Bridge v1 migration is
complete and the preserved global-workspace API has been removed.

Stages 1 through 7 are implemented. The Streamable HTTP transport exposes one
repository-scoped API with explicit project and repository selection.

Private remote deployments can enable the built-in single-owner OAuth server.
It follows MCP protected-resource and authorization-server discovery, supports
public and confidential DCR clients, and protects the entire MCP and artifact
HTTP surface with resource-bound Bearer tokens. OAuth remains disabled by
default for local development.

## Current APIs

The Bridge exposes:

- Core: `bridge_info`, `project_list`, `project_describe`, and
  `repository_status`;
- Files: `file_list`, `file_read`, and `file_search`;
- Git read: `git_log`, `git_show`, `git_diff`, and `git_refs`;
- Git workspace: `git_fetch`, `git_branch_create`, `git_branch_switch`, and
  `git_fast_forward`;
- Changes: `change_plan` and `change_apply`;
- Tasks and jobs: `task_list`, `task_start`, `job_status`, `job_output`,
  `job_cancel`, and `job_artifact_list`;
- Git write: `git_stage`, `git_commit`, `git_push_plan`, and `git_push`.

The Core API uses immutable project and repository registries loaded from a
validated Bridge configuration. It has no global current repository. The Stage 2 File
Service adds repository-scoped `file_list`, `file_read`, and `file_search`
with bounded paths, symlink handling, file sizes, traversal, and output. The
Stage 3 Git Read API provides `git_log`, `git_diff`, `git_show`, and `git_refs`.
All four use explicit repository selection,
structured results, the `GIT_READ` capability, and bounded output. The Stage 4
Changes API adds `change_plan` and `change_apply` for revision-guarded UTF-8
file creation, replacement, deletion, and rename. Plans are self-contained,
repository-scoped, bounded, and idempotent across retries. Replacement,
deletion, and rename are limited to tracked files so Git remains the recovery
boundary; creation requires an absent path. Stage 5 adds registered repository
tasks and durable asynchronous jobs through `task_list`, `task_start`,
`job_status`, `job_output`, and `job_cancel`. Jobs execute fixed configured
argv without a shell, persist in SQLite, expose bounded live output, recover
clear states after restart, and run with concurrency one.

Stage 6 completes the repository-scoped development cycle with `git_stage`,
`git_commit`, `git_push_plan`, and `git_push`. These tools require the
`git_write` capability. Staging accepts only explicit literal repository paths;
commits use only the already prepared index and never run an implicit add.
Optional revision, HEAD, and index guards reject concurrent changes when used.
Push plans bind the current named branch and exact local and remote heads into
a deterministic plan ID. Push revalidates that snapshot and permits only
branch creation or fast-forward updates; it never performs merge, rebase,
checkout, or force push. Commit and push writes are idempotent across retries.
Stage 7 removed all remaining global-workspace tools and their configuration,
dispatch, tests, and dependencies. No compatibility aliases or parallel legacy
API remain.

The post-migration operational surface also includes explicit Git workspace
operations (`git_fetch`, branch creation and switching, and upstream-only
fast-forward) plus immutable job artifact snapshots. Declared artifacts are
captured into job-specific storage and exposed through `job_artifact_list` and
the authenticated HTTP artifact route; they are never served from the mutable
working tree.

## Repository scope

This repository does not contain runtime state. In particular, it excludes
environment files, credentials, virtual environments, logs, job and OAuth
databases, artifact snapshots, and archives.

See [ARCHITECTURE.md](ARCHITECTURE.md), [MIGRATION.md](MIGRATION.md), and
[DEVELOPMENT.md](DEVELOPMENT.md) before making changes.
