# Fusion CAD Agent acceptance

## Task 13 transaction preview/replay gate

Status: **deferred live**. The offline fake-runtime implementation and tests do
not prove Autodesk Fusion command-preview, abort, replay, single-Undo, or ref
lifecycle behavior. `transaction.preview_replay` must remain `degraded` or
`unavailable` until the coordinator completes and records the sequence below on
a disposable real Fusion model.

Mandatory live sequence, in order:

1. Capture semantic baseline A, including structural hash, counts, stable
   pre-existing opaque refs, and relevant Bridge metadata.
2. Begin a transaction at A and stage the exact Task 13 logical Unicode text
   creation plan, including its Task 10/11 provenance metadata.
3. Preview once. Capture semantic preview B, generated opaque preview refs,
   provenance/metadata, validation, and the minimal semantic preview diff.
4. Abort the preview. Capture A2 and prove A2 is semantically equal to A.
5. Resolve the pre-existing refs after abort and prove they remain valid.
6. Prove every preview-only ref and preview-only metadata/provenance record is
   absent after abort.
7. Replay the exact staged declarative plan once and commit C. Prove C is
   semantically equivalent to the accepted preview B and that geometry plus
   metadata/provenance used the same Fusion command/transaction, with no hidden
   post-commit metadata command.
8. Undo exactly once. Capture A3 and prove A3 is semantically equal to A.
9. Begin and stage again, make a manual model edit, then commit. Prove commit
   returns `REVISION_CONFLICT` and applies none of the staged plan.
10. Prove preview abort left no hidden side state that affects subsequent
    operations.

Only after all ten checks pass may the coordinator change
`transaction.preview_replay` to `supported`. This document does not claim that
the live sequence has run.
