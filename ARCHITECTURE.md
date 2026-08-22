# Architecture

## Migration result

Development Bridge uses MCP Streamable HTTP, a Starlette application, and
Uvicorn. Tool definitions are thin adapters under `app/tools` and are composed
by the explicit tool registry.

The original process-wide `WORKSPACE` tools and dispatcher have been removed.
Every repository operation resolves explicit `project_id` and `repository_id`
values through an immutable registry snapshot. A managed-repository service can
atomically publish a replacement snapshot after a completed clone; there is no
global current repository.

## Development Bridge v1 target

The approved target model is:

```text
Bridge
├── Project
│   └── Repository
│       ├── Files
│       ├── Git state and workspace operations
│       ├── Controlled changes
│       └── Registered tasks, jobs, and artifacts
└── Community Knowledge (optional, repository-independent)
    └── normalized local SQLite/FTS5 evidence corpus
```

Repository-scoped calls carry explicit `project_id` and `repository_id`
values. There is no mutable global current repository.

The package boundaries under `app/` are:

- `api`: tool registration, schemas, results, and errors;
- `projects`: project and repository models and registries;
- `capabilities`: authorization and repository capability policy;
- `audit`: audit events and sinks;
- `files`: bounded repository-scoped file access;
- `git`: the single Git process boundary and Git services;
- `changes`: validated, revision-guarded changes;
- `tasks` and `jobs`: registered execution profiles, durable jobs, and
  immutable artifact snapshots;
- `knowledge`: Telegram JSON import, normalized corpus persistence, FTS search,
  exact lookup, neighborhoods, bounded reply reconstruction, and link-first
  MTProto synchronization;
- `integrations`: boundary for future optional external integrations.

The Core packages for API results, projects, capabilities, audit, Git read,
and files are implemented. The File Service provides bounded
repository-scoped listing, UTF-8 text reads, and text search without following
symbolic links. The Git Service provides structured, bounded log, show, diff,
refs, repository status, fetch, branch creation and switching, and upstream
fast-forward operations through the single Git process boundary.
The Changes service validates self-contained plans, calculates its own strong
working-tree revision, serializes application per repository, and persists
idempotency receipts without changing the Git index, refs, or objects. Its
revision combines HEAD, index state, tracked working-tree drift, and untracked
non-ignored files; Git-ignored content is excluded. Task and job packages
provide immutable repository task profiles and a durable SQLite queue with one
worker, cancellation, restart recovery, lifecycle audit, bounded live output,
and immutable job-specific artifact snapshots. Destructive file changes are
restricted to tracked files; the Changes service does not maintain a separate
backup or rollback store.

The Git Write service owns explicit path staging, index-only commits, push
planning, and guarded non-force pushes. It shares a cross-process repository
mutation lock with the Changes service, so filesystem plans cannot race index
or ref mutations. Commit and push receipts live under the repository Git
directory and make retried writes idempotent without process-global state.
Push plans inspect the configured remote directly, bind exact local and remote
object IDs, and must be re-created after either side changes. Git write uses one
repository capability, `git_write`; arbitrary commands, arguments, refspecs,
identity, and environment input are outside the API.

Configured repositories remain startup configuration. Managed external
repositories are cloned with fixed argv into staging below a separate data
root, validated as Git worktrees, atomically installed, and then registered in
the current process. A bounded, atomically replaced JSON manifest persists only
validated IDs, public HTTPS origin, depth, and creation time. Local paths are
always derived from the managed root and IDs. Managed clones expose only
`read`/`git_read`; `git_fetch` is their update operation, while changes, Git
writes, and task execution continue to fail through the capability policy.

## Dependency direction

MCP tool adapters depend on application services. Application services
depend on domain models and narrow filesystem/process interfaces. Domain
services must not depend on MCP types.

The MCP API boundary also owns a generic file-resource helper. Given an
already-authorized path and caller-provided URI/metadata, it returns a standard
`ResourceLink` and optionally a byte-exact base64
`EmbeddedResource<BlobResourceContents>` under a caller-selected inline limit.
It does not construct URLs or know about Knowledge, Telegram, or OpenAI APIs.

Task processes use fixed executable and argument tuples from validated startup
configuration. Clients select only a registered task ID; arbitrary shell,
command, argument, environment, and working-directory input is not accepted.

External hosted-service SDKs are not part of the core dependency graph. The
current API performs local repository operations and remote Git pushes through
the Git executable; it does not expose a global integration-status tool.

## Remote authorization

Remote private deployments use the OAuth authorization primitives supplied by
the pinned MCP Python SDK. Development Bridge implements only the durable
single-owner provider boundary: DCR client records, pending approvals,
one-time authorization codes, audience-bound access tokens, and rotating
refresh tokens. OAuth state is stored in a dedicated SQLite database outside
registered repositories. Opaque codes and tokens are stored only as digests;
the owner verifier is supplied through the deployment environment.

The canonical MCP resource and its artifact download subtree share one Bearer
token and the single `bridge` scope. Discovery, client registration,
authorization, token, revocation, and the owner approval page are the only
public OAuth routes. There is no user registry, RBAC, external IAM, or token
passthrough.

## Runtime isolation

Runtime configuration, credentials, job state, OAuth state, and artifact
snapshots live outside registered Git repositories. Community archive exports
and the knowledge SQLite corpus are runtime state and follow the same rule.
A deployed Bridge may run
directly from a registered source checkout for dogfooding, but service state
must not be written into that checkout. This keeps repository operations and
runtime persistence separate while still allowing Development Bridge to manage
and test its own source repository.

## Community evidence boundary

The Telegram Desktop importer is an explicit local CLI, not an MCP tool. It
normalizes messages and attachment metadata without copying media, and updates
the FTS5 index transactionally on repeated imports. MCP exposes only bounded,
read-only knowledge operations. These operations intentionally omit
`project_id` and `repository_id`: the corpus is external evidence, not a Git
checkout and not mutable global workspace state.

The MVP uses the standard-library JSON decoder, so one export document is held
in memory while its messages are written incrementally in one SQLite
transaction; it does not materialize a second in-memory message corpus. Live
sync, social-network login, background scheduling, semantic ranking, media
download, and automated truth scoring remain outside this contour.

The primary link-first path adds one narrow transport boundary:

```text
knowledge_source_add / knowledge_source_sync MCP adapters
                    ↓
TelegramKnowledgeService (batch/cursor policy and corpus writes)
                    ↓
TelegramAdapter
                    ↓
Telethon MTProto client and external session file
```

`source_sync_state` stores only the provider entity identity and bounded sync
cursors in the existing knowledge database. Initial synchronization walks from
the newest batch toward older IDs. Once history is complete, synchronization
requests IDs newer than the cursor and refreshes a small recent window for
edits. Telegram RPC exceptions are normalized at the adapter/service boundary;
MCP adapters never import or call Telethon directly.

Attachment access is a lazy layer over the normalized corpus. Stable
provider-derived identities remain valid across message refreshes, while an
additive SQLite snapshot table records opaque storage name, SHA-256, actual
size, MIME, safe filename, timestamp, and source/message/provider provenance.
The attachment service validates this corpus identity before the Telegram
adapter re-fetches the original message and downloads matching media. Files are
atomically placed in content-addressed runtime storage with directory mode 0700
and file mode 0600. Import, sync, search, and normal message lookup never
download media. The OAuth-protected HTTP route serves cached snapshots only and
never exposes a filesystem path or proxies a live Telegram stream.

The optional export layer reuses those exact snapshot bytes. A bounded
process-local registry maps cryptographically random, expiring tokens to one
corpus attachment identity. `knowledge_attachment_export` constructs an
absolute URL only from canonical HTTPS `server.public_base_url` plus the
configured MCP endpoint. Its token route deliberately does not require the MCP
OAuth bearer, but serves only a valid registry grant and never accepts source
IDs, media IDs, or filesystem paths from the downloader.
