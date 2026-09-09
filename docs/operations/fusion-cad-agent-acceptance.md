# Fusion CAD Agent acceptance

## Task 13 transaction preview/replay gate

Status: **LIVE ACCEPTED** on the disposable Fusion test documents on
`fusion-workstation` (the same Fusion 2704.1.53 runtime used for the Task 9
live gate). The acceptance used exact `FusionCadScriptBundle` rendered sources
from the P0 worktree, verified byte-for-byte by SHA-256 before execution; it
was not a hand-written substitute for the production transaction script.

### Accepted sequence

1. Captured semantic baseline A with authoritative model fingerprint, counts,
   stable pre-existing entity identity, and Bridge metadata state.
2. Began/staged the deterministic Unicode SketchText plan with the Task 10/11
   provenance write in the same staged operation.
3. Preview produced semantic B with exactly one additional sketch/timeline
   feature and preview-only provenance/ref evidence.
4. `PTransaction.Abort` restored A2 exactly to A; the authoritative fingerprint
   and semantic counts matched the original baseline.
5. Pre-existing identity remained resolvable after abort.
6. Preview-only entity identity and provenance were absent after abort.
7. Exact replay commit produced stable C with true Unicode
   `BRIDGE_PTX_Ω_ТЕСТ`; geometry and provenance were committed by the same
   PTransaction path, with no post-commit metadata command.
8. On a clean discriminator run, commit followed immediately by exactly one
   Undo restored A3 exactly to A. The earlier diagnostic where MCP commands were
   inserted between commit and Undo was rejected because those commands occupied
   upper command-stack frames; it is not acceptance evidence.
9. After a controlled manual edit changed the authoritative fingerprint, replay
   with the old baseline returned `REVISION_CONFLICT`, `applied=false`, before
   staged geometry/provenance was applied. The model retained only the manual edit.
10. Subsequent production reads showed no hidden preview side state.

### Runtime/API evidence and capability policy

- Primary runtime: `Application.executeTextCommand` using fixed safe commands
  `PTransaction.Start "bridge_cad_transaction"`, `PTransaction.Abort`, and
  `PTransaction.Commit`.
- The real Fusion API corrections discovered by this gate are checkpointed in
  `9743b71ce36ff3383ed11d3320b2d0e9933e528a`; authoritative fingerprints use
  the real `Products.itemByProductType("DesignProductType")`/Design cast shape,
  valid empty collections, and TimelineObject-associated persistent entities.
- Capability probing now has a per-runtime, empty, fixed-name
  `PTransaction.Start -> Abort` discriminator. `transaction.preview_replay` is
  `supported` only when that discriminator succeeds; API presence alone remains
  `degraded` and the service does not bypass a degraded state.
- `revision.external_change_detection` is `supported` only when the production
  authoritative fingerprint is readable and stable twice on the active runtime;
  mutation/commit paths still re-read and compare the authoritative fingerprint
  immediately before apply. Task 14 repeats the manual-change conflict invariant
  on the Schedule copy.

Task 13 is accepted. P0 itself remains open until the Task 14 whole-phase review
and Schedule-copy golden acceptance are complete.
