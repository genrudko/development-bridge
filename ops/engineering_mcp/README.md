# Engineering MCP lazy runtime

This directory captures the VPS-side Engineering Bridge runtime that fronts Draw.io,
Schematika IEC, PyPowsybl, KiCad and ngspice behind one compact MCP facade.

## Runtime contract

- `engineering-hub.service` is the only backend-facing service enabled at boot.
- Backend services on ports `8792` through `8796` are deliberately **disabled**.
- The hub starts a backend with `systemctl --user start` only after a connection miss.
  The request is retried only when no TCP connection was established, so a mutation is
  not replayed after uncertain delivery.
- Each backend is stopped after 180 seconds without a hub request.
- Existing stateful MCP sessions are recreated transparently after an idle stop.
- Per-service `MemoryHigh`/`MemoryMax` bounds prevent an engineering experiment from
  consuming the whole VPS.

The hub itself listens on `127.0.0.1:8797`. External routing/auth remains outside these
files. The real capability prefix and the PyPowsybl public address are deliberately not
stored in Git.

## Install / refresh

Prerequisites (tool checkouts, virtualenvs, Node, Chromium and workspaces) must already
exist under the paths used by the unit files. Then:

```bash
cp ops/engineering_mcp/power.env.example ~/.config/engineering-mcp/power.env
# edit MCP_PUBLIC_ADDRESS only if there is no existing power.env / legacy unit
ops/engineering_mcp/install-user.sh
ops/engineering_mcp/verify-user.sh
```

`install-user.sh` preserves an existing `MCP_PUBLIC_ADDRESS` from the old power unit on
first migration, refuses to run without the private capability-prefix file, installs the
versioned hub/UI and units, disables all five backends at boot, and enables the hub.

A healthy idle state is `engineering-hub=active` with the five backend services inactive.
Calling a backend through the Engineering Bridge should make only that service active;
after roughly three minutes it should return to inactive.
