# Development

## Supported environment

- Python 3.12 or newer;
- Git available on `PATH`;
- an isolated virtual environment.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp config/bridge.example.yaml bridge.local.yaml
```

Set `DEVELOPMENT_BRIDGE_CONFIG=bridge.local.yaml` and edit the file so every
configured repository points to a disposable local Git repository. Do not point
tests at the production workspace.

## Run Development Bridge

```bash
.venv/bin/python -m app.main
```

The default local endpoint is `http://127.0.0.1:8789/mcp`.

## Configure link-first Telegram knowledge

Configure an external runtime database:

```yaml
knowledge:
  database_path: /home/user/.local/state/development-bridge/knowledge.sqlite3
  attachment_directory: /home/user/.local/state/development-bridge/knowledge-attachments
  attachment_max_bytes: 536870912
  telegram:
    api_id: 12345
    api_hash: replace-with-my-telegram-api-hash
    session_path: /home/user/.local/state/development-bridge/telegram.session
    sync_batch_size: 2000
    recent_window_size: 100
```

Authorize the Telegram user account once. Telethon prompts for the phone, login
code, and the 2FA password when required:

```bash
.venv/bin/python -m app.knowledge.telegram_auth --config bridge.local.yaml
```

Afterward the normal MCP workflow requires only the public link:

```json
{"name":"knowledge_source_add","arguments":{"url":"https://t.me/example"}}
```

Continue bounded history acquisition, or later perform incremental refreshes:

```json
{"name":"knowledge_source_sync","arguments":{"source_id":"telegram-example"}}
```

`api_id`, `api_hash`, and `session_path` may instead be supplied through
`DEVELOPMENT_BRIDGE_TELEGRAM_API_ID`,
`DEVELOPMENT_BRIDGE_TELEGRAM_API_HASH`, and
`DEVELOPMENT_BRIDGE_TELEGRAM_SESSION_PATH`.

## Offline Telegram JSON fallback

Import a Telegram Desktop JSON export locally when MTProto is unavailable or an
offline archive is required:

```bash
.venv/bin/python -m app.knowledge.cli \
  --config bridge.local.yaml \
  --source-id ad5x-public \
  --source-url https://t.me/example \
  --title "AD5X Public Community" \
  /home/user/.local/share/development-bridge/knowledge-imports/ad5x/result.json
```

The import is idempotent by source and Telegram message ID. It reads attachment
metadata but does not open, copy, or store exported media files.

OAuth is disabled by default for local development. A private remote deployment
enables the built-in OAuth server with canonical HTTPS issuer and MCP resource
URLs, an OAuth SQLite database outside every registered repository, and one
`DEVELOPMENT_BRIDGE_OWNER_VERIFIER` deployment secret. The server uses DCR,
authorization code with PKCE S256, short-lived access tokens, and rotating
refresh tokens. Both `/mcp` and artifact downloads require the same `bridge`
scope and Bearer token when OAuth is enabled.

## Tests

```bash
.venv/bin/pytest
```

Tests must create temporary repositories. They must not require GitHub,
network access, production credentials, or production filesystem state.

## Integration rules

- Complete one migration stage at a time.
- Keep MCP adapters thin; place behavior in services.
- Do not introduce a global current project or repository.
- Do not execute client-provided shell strings.
- Keep GitHub and other hosted services optional.
- Add contract and boundary tests with each behavior change.
- Do not modify systemd or Caddy as part of application commits.
