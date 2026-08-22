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

## Import a community archive

Configure an external runtime database:

```yaml
knowledge:
  database_path: /home/user/.local/state/development-bridge/knowledge.sqlite3
```

Then import a Telegram Desktop JSON export locally:

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
