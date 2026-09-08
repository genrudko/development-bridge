from __future__ import annotations

from app.fusion_cad.scripts import FusionCadScriptBundle


def _run(payload, runtime):
    script = FusionCadScriptBundle.build("transaction", payload)
    scope = {"__name__": "__main__", **runtime}
    exec(compile(script, "<task13-transaction>", "exec"), scope)  # noqa: S102
    return scope["_output"]


def test_preview_applies_snapshot_validates_then_aborts_without_durable_evidence():
    events = []
    state = {"fingerprint": "fp_base", "refs": ["ent_body_existing"], "metadata": []}
    before = {
        "structural_hash": "h_base",
        "counts": {"bodies": 1, "sketches": 0},
        "refs": ["ent_body_existing"],
    }

    def fingerprint(_payload):
        return state["fingerprint"], {}, "doc_1"

    def begin(_payload):
        events.append("begin")

    def apply(plan):
        events.append(("apply", plan))
        state.update(
            fingerprint="fp_preview",
            refs=["ent_body_existing", "ent_sketch_preview"],
            metadata=["provenance"],
        )
        return {
            "refs": ["ent_sketch_preview"],
            "provenance": {"transaction_id": "tx_spike"},
        }

    def snapshot(_payload):
        events.append("snapshot")
        return {
            "structural_hash": "h_preview",
            "counts": {"bodies": 1, "sketches": 1},
            "refs": list(state["refs"]),
        }

    def validate(_payload):
        events.append("validate")
        return {"status": "passed", "errors": []}

    def abort(_payload):
        events.append("abort")
        state.update(fingerprint="fp_base", refs=["ent_body_existing"], metadata=[])

    plan = [
        {
            "action_type": "text_create",
            "text": "ПЫТОК",
            "provenance": {"transaction_id": "tx_spike"},
        }
    ]
    result = _run(
        {
            "operation": "preview",
            "transaction_id": "tx_spike",
            "document_ref": "doc_1",
            "expected_fingerprint": "fp_base",
            "plan": plan,
            "baseline_snapshot": before,
        },
        {
            "_transaction_fingerprint_primitive": fingerprint,
            "_transaction_begin_primitive": begin,
            "_transaction_apply_plan_primitive": apply,
            "_transaction_snapshot_primitive": snapshot,
            "_transaction_validate_primitive": validate,
            "_transaction_abort_primitive": abort,
        },
    )
    assert events == ["begin", ("apply", plan), "snapshot", "validate", "abort"]
    assert state == {
        "fingerprint": "fp_base",
        "refs": ["ent_body_existing"],
        "metadata": [],
    }
    assert result["data"]["preview_refs"] == ["ent_sketch_preview"]
    assert result["data"]["preview_refs_durable"] is False
    assert result["diff"]["refs"]["added"] == ["ent_sketch_preview"]


def test_commit_rechecks_then_replays_exact_plan_once_with_no_metadata_followup():
    events = []
    state = {"fingerprint": "fp_base"}
    plan = [
        {
            "action_type": "text_create",
            "text": "ПЫТОК",
            "metadata_writes": [{"name": "provenance"}],
        }
    ]

    def fingerprint(_payload):
        events.append("fingerprint")
        return state["fingerprint"], {}, "doc_1"

    def begin(_payload):
        events.append("begin")

    def apply(received):
        events.append(("apply", received))
        state["fingerprint"] = "fp_committed"
        return {
            "refs": ["ent_text_committed"],
            "provenance": {"transaction_id": "tx_spike"},
            "same_operation_provenance": True,
        }

    def finish(_payload):
        events.append("commit")

    result = _run(
        {
            "operation": "commit",
            "transaction_id": "tx_spike",
            "document_ref": "doc_1",
            "expected_fingerprint": "fp_base",
            "plan": plan,
        },
        {
            "_transaction_fingerprint_primitive": fingerprint,
            "_transaction_begin_primitive": begin,
            "_transaction_apply_plan_primitive": apply,
            "_transaction_commit_primitive": finish,
        },
    )
    assert events == ["fingerprint", "begin", ("apply", plan), "commit", "fingerprint"]
    assert result["data"]["replayed_plan"] == plan
    assert result["data"]["same_command_provenance"] is True


def test_commit_rejects_nonopaque_generated_refs():
    state = {"fingerprint": "fp_base"}

    def fingerprint(_payload):
        return state["fingerprint"], {}, "doc_1"

    def apply(_plan):
        state["fingerprint"] = "fp_committed"
        return {
            "refs": ["native-token-secret"],
            "provenance": {"transaction_id": "tx_spike"},
            "same_operation_provenance": True,
        }

    result = _run(
        {
            "operation": "commit",
            "transaction_id": "tx_spike",
            "document_ref": "doc_1",
            "expected_fingerprint": "fp_base",
            "plan": [{"action_type": "text_create"}],
        },
        {
            "_transaction_fingerprint_primitive": fingerprint,
            "_transaction_begin_primitive": lambda payload: None,
            "_transaction_apply_plan_primitive": apply,
            "_transaction_commit_primitive": lambda payload: None,
        },
    )
    assert result["status"] == "failed"
    assert result["error"]["code"] == "FUSION_API_ERROR"
    assert "native-token-secret" not in str(result)
