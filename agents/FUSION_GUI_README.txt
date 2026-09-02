Fusion Bridge GUI
=================

Normal launch: double-click START_FUSION_GUI.cmd.

First run:
- the bootstrap creates .venv and installs mcp==2.0.0 if needed;
- paste the desktop-node token in the GUI;
- leave "Remember on this PC" enabled;
- Windows DPAPI encrypts the token for the current Windows user.

Later runs:
- double-click START_FUSION_GUI.cmd;
- click Start; no token lookup/paste is needed.

GUI shows:
- local Fusion MCP port status;
- Bridge network reachability;
- relay process state;
- Fusion-to-Bridge connected state;
- live relay log with local HH:MM:SS.mmm timestamps;
- result-delivery health and pending outbox state. Full-resolution screenshots
  automatically use verified external spill when too large for inline delivery.

Security:
- token is never stored as plaintext;
- token is passed to the child agent only through its process environment;
- Forget token deletes the DPAPI-protected local token file.

Fallback:
START_FUSION_AGENT.ps1 remains available and no longer runs Test-NetConnection.
