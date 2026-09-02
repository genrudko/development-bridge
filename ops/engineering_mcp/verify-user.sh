#!/usr/bin/env bash
set -euo pipefail

USER_UID=$(id -u)
if [[ -z "${HOME:-}" ]]; then
    HOME=$(getent passwd "$USER_UID" | cut -d: -f6)
    export HOME
fi
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$USER_UID}
export DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}

units=(engineering-hub engineering-drawio engineering-schematika engineering-power engineering-kicad engineering-spice)
for unit in "${units[@]}"; do
    enabled=$(systemctl --user is-enabled "$unit.service" 2>/dev/null || true)
    active=$(systemctl --user is-active "$unit.service" 2>/dev/null || true)
    printf '%-32s enabled=%-10s active=%s\n' "$unit" "$enabled" "$active"
done

ss -ltn 2>/dev/null | grep -E '127\.0\.0\.1:879[2-7]' || true
