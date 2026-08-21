# Development Bridge

Development Bridge is the successor repository for the existing
`development-mcp` service. The repository currently contains the preserved
legacy MCP implementation and the structural foundation for the staged
Development Bridge v1 migration.

This baseline is intentionally not Development Bridge v1. It preserves the
current Streamable HTTP transport and the existing MCP tool names so that each
future migration stage can be integrated and verified independently.

## Current baseline

The copied MCP exposes:

- `workspace_status`, `read_file`, and `apply_patch`;
- `git_status`, `git_diff`, `git_branch`, `git_log`, `git_commit`, and
  `git_push`;
- `search_workspace` and `run_command`;
- `github_status`.

The baseline uses one `WORKSPACE` environment variable. Multi-project and
multi-repository behavior is planned but is not implemented in this commit.

## Repository scope

This repository does not contain production state. In particular, it excludes
environment files, credentials, virtual environments, logs, archives, and the
engineering repositories previously stored below `development-mcp/workspace`.

See [ARCHITECTURE.md](ARCHITECTURE.md), [MIGRATION.md](MIGRATION.md), and
[DEVELOPMENT.md](DEVELOPMENT.md) before making changes.

