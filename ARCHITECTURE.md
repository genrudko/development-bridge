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

The package boundaries under `app/` are:

- `api`: tool registration, schemas, results, and errors;
- `projects`: project and repository models and registries;
- `capabilities`: authorization and repository capability policy;
- `audit`: audit events and sinks;
- `files`: bounded repository-scoped file access;
- `git`: the single Git process boundary and Git services;
- `changes`: validated, revision-guarded changes;
- `tasks` and `jobs`: registered execution profiles and durable jobs;
- `integrations`: optional external integrations such as GitHub.

The Core packages for API results, projects, capabilities, audit, Git read,
files, and integrations are implemented. The File Service provides bounded
repository-scoped listing, UTF-8 text reads, and text search without following
symbolic links. The Git Service provides structured, bounded log, show, diff,
refs, and repository status operations through the single Git process boundary.
The Changes service validates self-contained plans, calculates its own strong
working-tree revision, serializes application per repository, and persists
idempotency receipts without changing the Git index, refs, or objects. Task and
job packages remain reserved for their approved later stages. Destructive file
changes are restricted to tracked files; Stage 4 does not maintain a separate
backup or rollback store.

## Dependency direction

MCP tool adapters depend on application services. Application services
depend on domain models and narrow filesystem/process interfaces. Domain
services must not depend on MCP types.

GitHub is not part of the core dependency graph. The legacy `github_status`
tool reaches PyGithub through a lazy optional integration boundary. Core startup and local Git operations do not require the
SDK or GitHub availability.

## Runtime isolation

The Git repository is separate from the existing production directory at
`/home/eodadmin/development-mcp`. Preparing this repository does not alter the
running systemd unit, Caddy configuration, production environment, or current
workspace repositories.
