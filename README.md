# Development Bridge

Development Bridge is the successor repository for the existing
`development-mcp` service. The repository currently contains the preserved
legacy MCP implementation and the structural foundation for the staged
Development Bridge v1 migration.

Stages 1 through 6 of Development Bridge v1 are implemented alongside the
remaining legacy API. The Streamable HTTP transport remains available so later
stages can be integrated and verified independently.

## Current APIs

The copied MCP exposes:

- `workspace_status`, `read_file`, and `apply_patch`;
- `git_status` and `git_branch` (legacy read helpers);
- `search_workspace`;
- `github_status`.

The legacy tools continue to use `WORKSPACE`. The v1 Core API uses immutable
project and repository registries loaded from a validated Bridge configuration.
It exposes `bridge_info`, `project_list`, `project_describe`, and
`repository_status` without a global current repository. The Stage 2 File
Service adds repository-scoped `file_list`, `file_read`, and `file_search`
with bounded paths, symlink handling, file sizes, traversal, and output. The
Stage 3 Git Read API replaces the legacy `git_log` and `git_diff` names and
adds `git_show` and `git_refs`. All four use explicit repository selection,
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
The old global-workspace `git_commit` and `git_push` implementations were
removed rather than retained as parallel APIs.

## Repository scope

This repository does not contain production state. In particular, it excludes
environment files, credentials, virtual environments, logs, archives, and the
engineering repositories previously stored below `development-mcp/workspace`.

See [ARCHITECTURE.md](ARCHITECTURE.md), [MIGRATION.md](MIGRATION.md), and
[DEVELOPMENT.md](DEVELOPMENT.md) before making changes.
