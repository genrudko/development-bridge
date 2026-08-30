#!/usr/bin/env bash
set -euo pipefail

USER_UID=$(id -u)
if [[ -z "${HOME:-}" ]]; then
    HOME=$(getent passwd "$USER_UID" | cut -d: -f6)
    export HOME
fi
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$USER_UID}
export DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}

SRC_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
USER_CONFIG="${HOME}/.config/engineering-mcp"
UNIT_DIR="${HOME}/.config/systemd/user"
RUNTIME_DIR="${HOME}/services/engineering-mcp/hub"
POWER_ENV="${USER_CONFIG}/power.env"
BACKENDS=(engineering-drawio engineering-schematika engineering-power engineering-kicad engineering-spice)

mkdir -p "$USER_CONFIG" "$UNIT_DIR" "$RUNTIME_DIR" "${HOME}/mcp-workspaces/hub/tmp"

# Preserve the current power capability URL if an older unit still embeds it.
if [[ ! -s "$POWER_ENV" && -f "$UNIT_DIR/engineering-power.service" ]]; then
    current_address=$(sed -n 's/^Environment=MCP_PUBLIC_ADDRESS=//p' "$UNIT_DIR/engineering-power.service" | tail -n 1)
    if [[ -n "$current_address" ]]; then
        umask 077
        printf 'MCP_PUBLIC_ADDRESS=%s\n' "$current_address" > "$POWER_ENV"
    fi
fi

if [[ ! -s "$POWER_ENV" ]]; then
    echo "Missing $POWER_ENV; copy power.env.example and set MCP_PUBLIC_ADDRESS first." >&2
    exit 2
fi
if [[ ! -s "$USER_CONFIG/capability-prefix" ]]; then
    echo "Missing $USER_CONFIG/capability-prefix; refusing to replace the hub runtime." >&2
    exit 2
fi

install -m 0644 "$SRC_DIR/hub/server.py" "$RUNTIME_DIR/server.py"
install -m 0644 "$SRC_DIR/hub/artifact-app.html" "$RUNTIME_DIR/artifact-app.html"
for source in "$SRC_DIR"/systemd/*.service; do
    install -m 0600 "$source" "$UNIT_DIR/$(basename "$source")"
done

systemctl --user daemon-reload
for unit in "${BACKENDS[@]}"; do
    systemctl --user disable "$unit.service" >/dev/null 2>&1 || true
    systemctl --user stop "$unit.service" >/dev/null 2>&1 || true
done
systemctl --user enable --now engineering-hub.service

echo "Engineering hub installed. Backends are disabled at boot and start on demand."
echo "Backend idle timeout: 180 seconds."
