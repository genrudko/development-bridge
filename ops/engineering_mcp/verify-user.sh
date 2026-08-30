#!/usr/bin/env bash
set -euo pipefail

units=(engineering-hub engineering-drawio engineering-schematika engineering-power engineering-kicad engineering-spice)
for unit in "${units[@]}"; do
    enabled=$(systemctl --user is-enabled "$unit.service" 2>/dev/null || true)
    active=$(systemctl --user is-active "$unit.service" 2>/dev/null || true)
    printf '%-32s enabled=%-10s active=%s\n' "$unit" "$enabled" "$active"
done

ss -ltn 2>/dev/null | grep -E '127\.0\.0\.1:879[2-7]' || true
