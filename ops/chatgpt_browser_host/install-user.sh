#!/usr/bin/env bash
set -euo pipefail

HOME_DIR="${HOME:-$(getent passwd "$(id -un)" | cut -d: -f6)}"
USER_NAME="${USER:-$(id -un)}"
SRC_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="${HOME_DIR}/.local/lib/development-bridge/browser-host"
UNIT_DIR="${HOME_DIR}/.config/systemd/user"
ENV_DIR="${HOME_DIR}/.config/development-bridge"

install -d -m 700 "$LIB_DIR" "$UNIT_DIR" "$ENV_DIR"
install -m 700 "$SRC_DIR/browser_host.py" "$LIB_DIR/browser_host.py"
install -m 600 "$SRC_DIR/chatgpt-browser-host.service" "$UNIT_DIR/chatgpt-browser-host.service"

if [[ ! -e "$ENV_DIR/browser-host.env" ]]; then
  install -m 600 "$SRC_DIR/browser-host.env.example" "$ENV_DIR/browser-host.env"
  echo "Created $ENV_DIR/browser-host.env; set BROWSER_HOST_TARGET_URL before starting."
fi

echo "Installed browser host runtime and user unit."
echo "For boot without an SSH session, enable linger once: sudo loginctl enable-linger $USER_NAME"
