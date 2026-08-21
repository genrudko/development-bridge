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
