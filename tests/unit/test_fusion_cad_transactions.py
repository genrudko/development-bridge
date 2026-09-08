from __future__ import annotations

import pytest

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.transactions import TransactionState, TransactionStore

SPIKE_ACTION = {
    "action_type": "text_create",
    "text": "ПЫТОК",
    "font": "Arial",
    "height_mm": 4.0,
    "position": {"x": 1.0, "y": 2.0, "z": 0.0},
    "alignment": "left",
    "flip_x": False,
    "flip_y": False,
    "role": "decorative_text",
}


def test_state_machine_preview_returns_to_staged_and_commit_is_single_use():
    store = TransactionStore()
    tx = store.begin("tx_spike", "doc_1", "rev_7", "fp_7", {"structural_hash": "h7"})
    assert tx.state is TransactionState.NEW

    staged = store.stage("tx_spike", SPIKE_ACTION)
    assert staged.state is TransactionState.STAGED
    plan_hash = staged.plan_hash

    previewed = store.begin_preview("tx_spike", "fp_7")
    assert previewed.state is TransactionState.PREVIEWED
    restored = store.finish_preview(
        "tx_spike",
        preview={"refs": ["ref_text_preview"], "structural_hash": "h8"},
    )
    assert restored.state is TransactionState.STAGED
    assert restored.plan_hash == plan_hash

    committing = store.begin_commit("tx_spike", "fp_7")
    assert committing.plan == (SPIKE_ACTION,)
    committed = store.finish_commit("tx_spike", {"refs": ["ref_text_final"]})
    assert committed.state is TransactionState.COMMITTED
    with pytest.raises(FusionCadError) as exc:
        store.begin_commit("tx_spike", "fp_7")
    assert exc.value.code == ErrorCode.TRANSACTION_CONFLICT


def test_stale_and_terminal_operations_fail_closed_and_rollback_aborts():
    store = TransactionStore()
    store.begin("tx_stale", "doc_1", "rev_1", "fp_1", {})
    store.stage("tx_stale", SPIKE_ACTION)
    with pytest.raises(FusionCadError) as exc:
        store.begin_preview("tx_stale", "fp_external")
    assert exc.value.code == ErrorCode.REVISION_CONFLICT

    aborted = store.rollback("tx_stale")
    assert aborted.state is TransactionState.ABORTED
    with pytest.raises(FusionCadError) as exc:
        store.stage("tx_stale", SPIKE_ACTION)
    assert exc.value.code == ErrorCode.TRANSACTION_CONFLICT


def test_plan_and_evidence_are_defensively_copied_for_exact_replay_identity():
    action = dict(SPIKE_ACTION)
    store = TransactionStore()
    store.begin("tx_copy", "doc_1", "rev_1", "fp_1", {"counts": {"bodies": 0}})
    staged = store.stage("tx_copy", action)
    action["text"] = "changed-after-stage"
    assert staged.plan[0]["text"] == "ПЫТОК"
    assert store.get("tx_copy").plan_hash == staged.plan_hash
