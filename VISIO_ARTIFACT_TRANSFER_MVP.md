# Visio Bridge — artifact transfer MVP (2026-10-09)

## Status

- **Implemented in an isolated local worktree**, branch `feature/visio-artifact-transfer-mvp`.
- Regressions: 162 passing Python tests. Server registry/import/managed-loader compilation passed.
- A temporary service override was successfully tested: the Visio Bridge started on port 18792 and `visio-workstation` re-registered.
- **Live Windows extension deployment accepted**: the official `visio_managed_update` succeeded on a subsequent authorized invocation; Windows node published all 3 tools.
- For live acceptance, the reversible service override was **re-enabled** and all 3 native Windows file-transfer smoke tests passed. No production source, GitHub `main`, or end-user files were changed.
- **Native Visio opening verified** for VSDX, VSDM and a 3-chunk VSDX; fake DesktopNode acceptance tests remain part of regressions.

## Live acceptance (2026-10-09)

**PASSED:** Authorized Master MCP `visio_managed_update` installed Windows extension
`2026.10.09.1` on `visio-workstation`. All three new managed tools
are present. `visio_transfer_artifact` delivered and opened in actual Microsoft
Visio (read-only, macros disabled), as confirmed by independent COM
`list_open_documents` checks:

- VSDX 11,024 B: 1 chunk, SHA-256 verified, opened (1 page).
- VSDM with `visio/vbaProject.bin` 17,914 B: 1 chunk, SHA-256 verified,
  opened with macros disabled (1 page).
- VSDX 376,178 B: **3 chunks**, SHA-256 verified, opened (1 page).

A synthetic invalid OPC variant was correctly rejected by Visio, and its
replacement (unchanged OPC part set, ignorable XML whitespace) was accepted.
See `LIVE_ACCEPTANCE_20261009.txt`. The `SaveAs` problem remains separate.

## Intended API

`visio_transfer_artifact({node_id:"visio-workstation",file_name:"Pilot.vsdx",open_in_visio:true})`

The server reads **only a basename inside**
`/home/admin/.local/state/development-bridge/visio-outbox/`
(derived from the existing `result_artifact_directory` setting), and enforces a 32 MiB file limit.

The server sends 160 KiB chunks over the existing outbound authenticated desktop-node queue, with an automatically generated transfer ID and SHA-256. The node verifies size, digest and OPC ZIP CRC, stages the file in `WORKSPACE/received_artifacts/<transfer_id>/`, and writes an immutable manifest. Optional Visio open uses `Documents.OpenEx(path,394)` (read-only, macros disabled, no workspace, excluded from MRU). The document is **visible** (no hidden flag).

## Windows tool names (after an authorized managed-extension update)

- `stage_visio_artifact_chunk`
- `visio_artifact_status`
- `open_received_visio_artifact`

## Completed live gates / follow-up

1. **PASS:** Official server-pinned `visio_managed_update` applied. Raw `__openai_visio_managed_update` not called.
2. **PASS:** Windows node advertised all three tools; isolated server worktree activated through reversible override.
3. **PASS:** VSDX SHA-256/COM native open accepted, 1 page.
4. **PASS:** Macro-bearing VSDM transport and COM open with macros disabled. **Follow-up:** WTG1/KTP1 generated native VSDM is not yet created or accepted.

The usual `SaveAs` error is unrelated to this transport and still needs separate diagnosis. Do not claim this MVP resolves it.

## Rollback

To return the bridge service to the original checkout after an approved deployment:

```bash
rm -f /home/admin/.config/systemd/user/visio-bridge.service.d/visio-transfer-mvp.conf
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
systemctl --user daemon-reload
systemctl --user restart visio-bridge.service
```

No GitHub Actions and no production merge are required for offline tests.
