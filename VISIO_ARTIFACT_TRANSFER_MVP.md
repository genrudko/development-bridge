# Visio Bridge — artifact transfer MVP (2026-10-09)

## Status

- **Implemented in an isolated local worktree**, branch `feature/visio-artifact-transfer-mvp`.
- Regressions: 162 passing Python tests. Server registry/import/managed-loader compilation passed.
- A temporary service override was successfully tested: the Visio Bridge started on port 18792 and `visio-workstation` re-registered.
- **Live Windows extension deployment NOT accepted**: the explicit `visio_managed_update` invocation was blocked by the platform before it ran. No alternate channel was used.
- The override was **removed**, and the existing Visio Bridge service was restarted against its original code. No production source, GitHub `main`, or end-user files were changed.
- Consequently **no live file transfer or native Visio open has yet succeeded**; tested end-to-end transfer uses a fake DesktopNode and real VSDX test fixture.

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

## Explicit remaining gates

1. Approve and run the **server-pinned** `visio_managed_update` through the approved administrative workflow; do not call the protected raw `__openai_visio_managed_update` or bypass tool restrictions.
2. Once the node advertises all three tools, activate the isolated server worktree (reversible systemd override) in a controlled window.
3. Publish the known `test5_master.vsdx` smoke fixture to the allowed outbox and run `visio_transfer_artifact`; verify SHA-256 and that the expected page opens read-only, macros disabled.
4. Repeat against a genuine generated `.vsdm`. Only then accept the live roundtrip.

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
