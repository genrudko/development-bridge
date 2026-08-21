# Development Bridge

Development Bridge is the successor repository for the existing
`development-mcp` service. The repository currently contains the preserved
legacy MCP implementation and the structural foundation for the staged
Development Bridge v1 migration.

Stages 1 through 5 of Development Bridge v1 are implemented alongside the
remaining legacy API. The Streamable HTTP transport remains available so later
stages can be integrated and verified independently.

## Current APIs

The copied MCP exposes:

- `workspace_status`, `read_file`, and `apply_patch`;
- `git_status`, `git_branch`, `git_commit`, and `git_push`;
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

## Repository scope

This repository does not contain production state. In particular, it excludes
environment files, credentials, virtual environments, logs, archives, and the
engineering repositories previously stored below `development-mcp/workspace`.

See [ARCHITECTURE.md](ARCHITECTURE.md), [MIGRATION.md](MIGRATION.md), and
[DEVELOPMENT.md](DEVELOPMENT.md) before making changes.
