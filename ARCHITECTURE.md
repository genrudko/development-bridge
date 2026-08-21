# Architecture

## Baseline state

The current code is a preserved copy of the active `development-mcp` Python
application. It uses MCP Streamable HTTP, a Starlette application, and Uvicorn.
Tool definitions and handlers are grouped under `app/tools` and dispatched by
`app/tools/__init__.py`.

All filesystem, Git, search, and execution tools currently depend on one
process-wide `WORKSPACE`. This limitation is retained only to establish a
faithful migration baseline.

## Development Bridge v1 target

The approved target model is:

```text
Bridge
└── Project
    └── Repository
        ├── Files
        ├── Git state
        ├── Controlled changes
        └── Registered tasks and jobs
```

Repository-scoped calls will carry explicit `project_id` and `repository_id`
values. There will be no mutable global current repository.

The future package boundaries are reserved under `app/`:

- `api`: tool registration, schemas, results, and errors;
- `projects`: project and repository models and registries;
- `capabilities`: authorization and repository capability policy;
- `audit`: audit events and sinks;
- `files`: bounded repository-scoped file access;
- `git`: the single Git process boundary and Git services;
- `changes`: validated, revision-guarded changes;
- `tasks` and `jobs`: registered execution profiles and durable jobs;
- `integrations`: optional external integrations such as GitHub.

These packages are placeholders in the baseline commit. They contain no v1
implementation yet.

## Dependency direction

MCP tool adapters will depend on application services. Application services
will depend on domain models and narrow filesystem/process interfaces. Domain
services must not depend on MCP types.

GitHub is not part of the core dependency graph. The legacy module still uses
PyGithub to preserve current behavior; it will be moved behind an optional
integration boundary during the staged migration.

## Runtime isolation

The Git repository is separate from the existing production directory at
`/home/eodadmin/development-mcp`. Preparing this repository does not alter the
running systemd unit, Caddy configuration, production environment, or current
workspace repositories.

