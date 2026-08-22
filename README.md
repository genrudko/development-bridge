# Development Bridge

Development Bridge is the successor repository for the former
`development-mcp` service. The staged Development Bridge v1 migration is
complete and the preserved global-workspace API has been removed.

Stages 1 through 7 are implemented. The Streamable HTTP transport exposes the
development API with explicit project and repository selection plus an
optional repository-independent Community Knowledge evidence API.

Private remote deployments can enable the built-in single-owner OAuth server.
It follows MCP protected-resource and authorization-server discovery, supports
public and confidential DCR clients, and protects the entire MCP and artifact
HTTP surface with resource-bound Bearer tokens. OAuth remains disabled by
default for local development.

## Current APIs

The Bridge exposes:

- Core: `bridge_info`, `project_list`, `project_describe`, `repository_status`,
  and `repository_clone`;
- Files: `file_list`, `file_read`, and `file_search`;
- Git read: `git_log`, `git_show`, `git_diff`, and `git_refs`;
- Git workspace: `git_fetch`, `git_branch_create`, `git_branch_switch`, and
  `git_fast_forward`;
- Changes: `change_plan` and `change_apply`;
- Tasks and jobs: `task_list`, `task_start`, `job_status`, `job_output`,
  `job_cancel`, `job_artifact_list`, `job_artifact_view`, and
  `job_artifact_export`;
- Ad-hoc execution: `repository_exec` for structured executable/argv runs in
  repositories with `execute`, using the same durable jobs and artifacts;
- Git write: `git_stage`, `git_commit`, `git_push_plan`, and `git_push`.
- GitHub host: repository status, checks, issues, pull requests, reviews,
  exact-head merge, and Actions runs/jobs/logs/artifacts/lifecycle.
- Community Knowledge: `knowledge_source_list`, `knowledge_search`,
  `knowledge_message`, `knowledge_thread`, `knowledge_source_add`, and
  `knowledge_source_sync`; `knowledge_attachment_open` lazily snapshots one
  corpus-validated attachment, while `knowledge_attachment_export` issues a
  short-lived external URL plus standard MCP file resource blocks for the same
  immutable snapshot.

## Managed external repositories

Projects combine repositories declared in `bridge.yaml` with managed external
clones. `repository_clone` accepts only a public HTTPS Git URL and installs a
completed shallow, single-branch clone under
`$XDG_DATA_HOME/development-bridge/repositories` (or
`~/.local/share/development-bridge/repositories`), with an optional
`managed_repositories.root` override. An atomically written JSON manifest makes
these registrations available after restart; `bridge.yaml` is never rewritten.

Managed clones are reference repositories: `read` and `git_read` are enabled,
while file/Git writes and task execution are disabled. Existing Files, Git Read,
repository status, and `git_fetch` APIs operate on them immediately. Use
`git_fetch` for later remote updates; no separate pull or sync API is added.
An optional `repository_clone.ref` selects an initial branch or tag through the
fixed `git clone --branch` invocation and is persisted as clone intent. It does
not promise arbitrary commit-SHA checkout support.

## Community Knowledge

Community Knowledge is an optional, repository-independent evidence contour.
The primary product workflow is link-first:

```text
public Telegram URL
        ↓
knowledge_source_add
        ↓
Telegram MTProto through an authorized Telethon session
        ↓
bounded history batches → normalized SQLite corpus + FTS5
        ↓
knowledge_source_sync / knowledge_search / message / thread
```

Telegram Desktop JSON remains an offline/fallback workflow:

```text
Telegram Desktop JSON export
        ↓
local one-shot importer
        ↓
normalized SQLite corpus + FTS5
        ↓
KnowledgeService
        ↓
thin knowledge_* MCP tools
        ↓
ChatGPT analysis
```

Set `knowledge.database_path` and the nested Telegram credentials/session path
outside every registered Git repository. After the one-time local Telegram
authorization, `knowledge_source_add` needs only a public `t.me` URL and imports
one bounded batch. Repeated `knowledge_source_sync` calls continue older history
and later fetch new messages plus a bounded recent edit window. Import and sync
store attachment metadata only. `knowledge_attachment_open` downloads one
selected Telegram attachment on demand and reuses its immutable local snapshot.
Private invite joining, bulk media download, background polling, Bot API, and
scraping are absent.

Attachment snapshots use configurable runtime storage outside Git. Images are
returned as MCP image content, UTF-8 text/config/log files as bounded text, and
PDFs as bounded extracted text without OCR. Videos retain the raw original and,
when `ffmpeg` and `ffprobe` are installed, include bounded metadata and up to
eight preview frames. Other binary files remain available from the OAuth-
protected raw route without execution or automatic extraction.

External file delivery is opt-in through `server.public_base_url`, which must
be a canonical HTTPS origin. `knowledge_attachment_export` creates no file
copy: it issues a random process-local token with a configurable 10-minute
default TTL. The repeatable `/mcp/knowledge/exports/{token}` route uses
`private, no-store` and reveals neither corpus identity nor a filesystem path.
Service restart invalidates outstanding export tokens.

The shared MCP API file-resource helper emits a `ResourceLink` for every file
and, up to the conservative 4 MiB inline limit, an
`EmbeddedResource<BlobResourceContents>` containing byte-exact base64. The
knowledge export adapter uses this helper without exposing its cached local
path; larger files retain the HTTPS export as fallback.

Archives also remain outside Git. The fallback JSON import is a local CLI
operation; MCP clients cannot supply filesystem paths or trigger file imports.
Stored sources and messages use platform-neutral identifiers so another
provider can be added without turning the repository API into a social-network
client.

The corpus is an evidence source, not an automatically trustworthy source of
truth. Search and lookup preserve source, author, timestamp, message ID, reply
relationships, topic metadata, permalink, and a stable reference. Community
claims should be compared with code, documentation, logs, measurements, and
other evidence before they are treated as reproducible facts.

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
working tree. Visual review follows the bounded path job artifact → immutable
snapshot → `job_artifact_view` → MCP `ImageContent` → visual review. Inline
viewing supports PNG, JPEG, and WebP snapshots up to 8 MiB; larger artifacts
remain available through the existing authenticated HTTP download route.
For arbitrary binary artifacts, `job_artifact_export` emits a native MCP
`ResourceLink` plus byte-exact `EmbeddedResource` up to 4 MiB. Its short-lived,
bearer-free capability URL remains the fallback for larger files, uses the same
bounded process-local token primitive as knowledge exports, and never creates a
second artifact copy.

`task_start` remains the canonical reusable-command API. `repository_exec` is
the ad-hoc engineering path: it always runs in the selected repository root,
does not use a shell, and accepts no cwd, environment, stdin, or privilege
override. Its execution specification and idempotency digest are stored in the
job database, so queued runs retain their meaning across restart.

GitHub host integration is optional and reads
`DEVELOPMENT_BRIDGE_GITHUB_TOKEN` only from the runtime environment. Repository
identity is derived from the registered Git `origin`; tools cannot supply an
owner, repository, or arbitrary API URL. Managed external repositories retain
GitHub read access through `git_read` but cannot mutate host state because they
lack `git_write`. Git push remains `git_push`; the GitHub service owns issues,
PRs, reviews, checks, merge, and Actions. Actions artifacts are snapshotted as
original ZIP bytes and use the same native resource handoff and short-lived
capability fallback as other Bridge files.

## Repository scope

This repository does not contain runtime state. In particular, it excludes
environment files, credentials, virtual environments, logs, job and OAuth
databases, knowledge databases, artifact snapshots, and community archives.

See [ARCHITECTURE.md](ARCHITECTURE.md), [MIGRATION.md](MIGRATION.md), and
[DEVELOPMENT.md](DEVELOPMENT.md) before making changes.
