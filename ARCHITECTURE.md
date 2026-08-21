# Architecture

## Migration result

Development Bridge uses MCP Streamable HTTP, a Starlette application, and
Uvicorn. Tool definitions are thin adapters under `app/tools` and are composed
by the explicit tool registry.

The original process-wide `WORKSPACE` tools and dispatcher have been removed.
Every repository operation resolves explicit `project_id` and `repository_id`
values through the immutable registry.

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
- `integrations`: boundary for future optional external integrations.

The Core packages for API results, projects, capabilities, audit, Git read,
and files are implemented. The File Service provides bounded
repository-scoped listing, UTF-8 text reads, and text search without following
symbolic links. The Git Service provides structured, bounded log, show, diff,
refs, and repository status operations through the single Git process boundary.
The Changes service validates self-contained plans, calculates its own strong
working-tree revision, serializes application per repository, and persists
idempotency receipts without changing the Git index, refs, or objects. Task and
job packages provide immutable repository task profiles and a durable SQLite
queue with one worker, cancellation, restart recovery, lifecycle audit, and
bounded live output. Destructive file changes are restricted to tracked files;
Stage 4 does not maintain a separate backup or rollback store.

The Git Write service owns explicit path staging, index-only commits, push
planning, and guarded non-force pushes. It shares a cross-process repository
mutation lock with the Changes service, so filesystem plans cannot race index
or ref mutations. Commit and push receipts live under the repository Git
directory and make retried writes idempotent without process-global state.
Push plans inspect the configured remote directly, bind exact local and remote
object IDs, and must be re-created after either side changes. Git write uses one
repository capability, `git_write`; arbitrary commands, arguments, refspecs,
identity, and environment input are outside the API.

## Dependency direction

MCP tool adapters depend on application services. Application services
depend on domain models and narrow filesystem/process interfaces. Domain
services must not depend on MCP types.

Task processes use fixed executable and argument tuples from validated startup
configuration. Clients select only a registered task ID; arbitrary shell,
command, argument, environment, and working-directory input is not accepted.

External hosted-service SDKs are not part of the core dependency graph. The
current API performs local repository operations and remote Git pushes through
the Git executable; it does not expose a global integration-status tool.

## Runtime isolation

The Git repository is separate from the existing production directory at
`/home/eodadmin/development-mcp`. Preparing this repository does not alter the
running systemd unit, Caddy configuration, production environment, or current
workspace repositories.
