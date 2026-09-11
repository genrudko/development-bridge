# Fusion Shimmer guarded overlay

This directory is the Development Bridge source of truth for the minimal private overlay applied to the pinned MIT Shimmer provider at commit `97a06e76c289420a721590ddcab334f5f3dc3178`.

It does **not** vendor Shimmer's modeling algorithms. `addin_bridge_cad.py` adds only a private provider guard and a PTransaction envelope that delegates an explicit allow-list to Shimmer's existing in-Fusion operation registry. `server_bridge_cad.py` exposes two private MCP tools used by `fusion.cad/v1`.

`install.py` fails closed unless the Shimmer git HEAD and both registration-file preimage hashes match `manifest.json`. It validates and prepares all edits before writing. Deployment to the live Windows/Fusion installation is intentionally outside the offline implementation phase.

The overlay never saves or closes a Fusion document, never enables arbitrary-code tools, and never exposes a generic registry-dispatch MCP tool.
