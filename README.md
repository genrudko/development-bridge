# Development Bridge

Development Bridge is the successor repository for the existing
`development-mcp` service. The repository currently contains the preserved
legacy MCP implementation and the structural foundation for the staged
Development Bridge v1 migration.

Stage 1 of Development Bridge v1 is implemented alongside the preserved legacy
API. The Streamable HTTP transport and existing MCP tool names remain available
so later stages can be integrated and verified independently.

## Current APIs

The copied MCP exposes:

- `workspace_status`, `read_file`, and `apply_patch`;
- `git_status`, `git_diff`, `git_branch`, `git_log`, `git_commit`, and
  `git_push`;
- `search_workspace` and `run_command`;
- `github_status`.

The legacy tools continue to use `WORKSPACE`. The v1 Core API uses immutable
project and repository registries loaded from a validated Bridge configuration.
It exposes `bridge_info`, `project_list`, `project_describe`, and
`repository_status` without a global current repository. The Stage 2 File
Service adds repository-scoped `file_list`, `file_read`, and `file_search`
with bounded paths, symlink handling, file sizes, traversal, and output.

## Repository scope

This repository does not contain production state. In particular, it excludes
environment files, credentials, virtual environments, logs, archives, and the
engineering repositories previously stored below `development-mcp/workspace`.

See [ARCHITECTURE.md](ARCHITECTURE.md), [MIGRATION.md](MIGRATION.md), and
[DEVELOPMENT.md](DEVELOPMENT.md) before making changes.
