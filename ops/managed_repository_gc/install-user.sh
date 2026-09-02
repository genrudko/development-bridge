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
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
install -m 0600 "$SRC_DIR/development-bridge-managed-gc.service" "$UNIT_DIR/development-bridge-managed-gc.service"
install -m 0600 "$SRC_DIR/development-bridge-managed-gc.timer" "$UNIT_DIR/development-bridge-managed-gc.timer"
systemctl --user daemon-reload
systemctl --user enable --now development-bridge-managed-gc.timer
systemctl --user status development-bridge-managed-gc.timer --no-pager || true
