Fusion Bridge GUI
=================

Normal workflow (both applications are manual):
1. Launch Autodesk Fusion 360 manually.
2. Close Fusion's modal "Scripts and Add-Ins" dialog if it is open.
3. Then launch START_FUSION_GUI.cmd manually.

The GUI automatically supervises Reference, Eyes, and Hands after a saved
desktop-node token exists. There is no separate Hands launcher and no extra
Start step on later runs. If the GUI opens before Fusion is ready, leave it
open: each provider waits and recovers independently.

First run:
- run START_FUSION_GUI.cmd from the extracted package; it installs or upgrades
  the curated launcher bundle under
  LocalAppData\DevelopmentBridgeFusion\launcher and runs that managed copy;
- the bootstrap creates .venv and installs mcp==2.0.0 if needed;
- the same one-time bootstrap installs missing qualified Eyes and Hands runtimes
  under LocalAppData\DevelopmentBridgeFusion. Eyes is pinned PERISCOPE; Hands is
  the exact pinned Shimmer archive/server/add-in. Provider installer failures are
  logged to bootstrap-install.log and degrade only that optional provider;
- the Shimmer runtime lives under DevelopmentBridgeFusion\shimmer-sidecar:
  fusion-mcp.exe is in venv\Scripts, the package is in
  venv\Lib\site-packages\fusion_mcp, and the exact SHA-named extracted source
  remains under extract-<sha>;
- the installed add-in is under AppData\Roaming\Autodesk\Autodesk Fusion 360\
  API\AddIns\Fusion360MCP\fusion_mcp_addin;
- keep fusion_hands_runtime.py and the fusion_shimmer_overlay directory beside
  this GUI (the distributed package includes them);
- paste the desktop-node token, leave "Remember on this PC" enabled, and use
  Retry / Start once. Windows DPAPI encrypts the token for this Windows user.

Status rows report Reference (Autodesk MCP / fusion-workstation), Eyes
(PERISCOPE / fusion-eyes), and Hands (Shimmer / fusion-hands). A missing or
mismatched optional runtime degrades only that provider. Unknown listeners on
18768 or 18769 fail closed and are not adopted or killed.

Stop leaves the GUI open and terminates only child processes created by this
GUI. Closing the GUI does the same. Neither action closes Fusion, saves or
closes a Fusion document, or changes a Fusion document.

Security:
- the token is never stored as plaintext;
- the token is passed to relay children only through their process environment;
- Forget token deletes the DPAPI-protected local token file.

Fallback:
START_FUSION_AGENT.ps1 remains available for the Reference relay only.

Palette / operator dialogue:
- the installed Fusion add-in exposes the Russian "Диалог с CAD-агентом" Palette;
- owner messages, timestamps and read receipts are durable through the Bridge Palette state;
- ✓ means sent; ✓✓ means the agent actually polled/read that owner message;
- Stop-after-step / Resume controls do not save or close the Fusion document.

Turn continuity:
- normal long-running work may continue automatically through the bound Development
  Bridge route; a fresh continuation turn ACKs its visible cont_* reference before work;
- a missing browser visual refresh is not proof of a failed continuation; Bridge durable
  state / ACK evidence is authoritative;
- retries are allowed only for proven pre-submit/not-submitted delivery failures.
- bridge_restart uses the same resilient cont_* continuation/ACK contract after a service restart;
- coordinator overflow is recovered through coordinator_ack batched_messages rather than being silently truncated.
