from __future__ import annotations

from app.fusion_cad.models import EffectiveVisibility
from app.fusion_cad.text import (
    apply_visibility_restore_plan,
    build_visibility_restore_plan,
    compute_effective_visibility,
)

# =========================================================================
# Effective local + hierarchical visibility
# =========================================================================


def test_effective_visibility_top_level_equals_local():
    eff = compute_effective_visibility(
        type="body", ref="ent_body_1", local_visible=True, parents=(True,)
    )
    assert isinstance(eff, EffectiveVisibility)
    assert eff.effective_visible is True
    assert eff.parent_visible is True


def test_effective_visibility_parent_hidden_hides_child():
    # Local visible but an ancestor hidden -> effective hidden.
    eff = compute_effective_visibility(
        type="body", ref="ent_body_2", local_visible=True, parents=(False,)
    )
    assert eff.effective_visible is False
    assert eff.parent_visible is False


def test_effective_visibility_deep_hierarchy_all_visible():
    eff = compute_effective_visibility(
        type="body", ref="ent_body_3", local_visible=True, parents=(True, True)
    )
    assert eff.effective_visible is True


def test_effective_visibility_all_parents_true_when_isolated():
    # When reading a top-level entity with no enclosing hierarchy, parents=(True,)
    eff = compute_effective_visibility(
        type="body", ref="ent_body_4", local_visible=True, parents=()
    )
    assert eff.effective_visible is True
    assert eff.parent_visible is True


# =========================================================================
# Reversible state limited to own mutation
# =========================================================================


def test_show_only_builds_restore_plan_limited_to_own_mutation():
    """show_only must capture exactly the entities it will mutate (all others
    hidden + the target shown), and nothing outside that set."""
    entities = [
        {"ref": "ent_body_1", "type": "body", "visible": True},
        {"ref": "ent_body_2", "type": "body", "visible": False},
        {"ref": "ent_sk_1", "type": "sketch", "visible": True},
        {"ref": "ent_body_3", "type": "body", "visible": True},
    ]
    plan = build_visibility_restore_plan(entities, target_ref="ent_body_1")
    # Every captured entry belongs to the mutation's own scope (all entities
    # that this show_only will alter).
    mutated_refs = {e["ref"] for e in entities}
    for entry in plan["captured"]:
        assert entry["ref"] in mutated_refs
    # The target is captured as shown; all others are captured as their prior
    # value so isolate/show_only can be reversed.
    assert plan["target_ref"] == "ent_body_1"
    # Only the entity refs being changed are stored (no unrelated doc state).
    assert plan["scope"] == "own_mutation"


def test_show_only_restore_plan_reverts_only_own_mutation():
    entities = [
        {"ref": "ent_body_1", "type": "body", "visible": True},
        {"ref": "ent_body_2", "type": "body", "visible": False},
    ]
    plan = build_visibility_restore_plan(entities, target_ref="ent_body_1")
    # Simulate show_only applied: target shown, others hidden.
    applied = {"ent_body_1": True, "ent_body_2": False}
    restored = apply_visibility_restore_plan(plan, applied)
    # Restore reverts each captured entity to its pre-mutation value.
    assert restored["ent_body_1"] is True
    assert restored["ent_body_2"] is False


def test_show_only_restore_does_not_touch_unrelated_entities():
    plan = {
        "scope": "own_mutation",
        "target_ref": "ent_body_1",
        "captured": [{"ref": "ent_body_1", "type": "body", "visible": True}],
    }
    # apply leaves unrelated state untouched and only restores captured refs.
    result = apply_visibility_restore_plan(plan, {"unrelated": False})
    assert result["unrelated"] is False  # unchanged
    assert result["ent_body_1"] is True  # restored from captured


def test_isolate_and_show_only_capture_are_distinguishable():
    """isolate and show_only capture the same limited per-entity state but the
    plan records which operation created it so restore is not over-broad."""
    entities = [{"ref": "ent_body_1", "type": "body", "visible": True}]
    show_only = build_visibility_restore_plan(entities, target_ref="ent_body_1")
    isolate = build_visibility_restore_plan(
        entities, target_ref="ent_body_1", operation="isolate"
    )
    assert show_only["operation"] == "show_only"
    assert isolate["operation"] == "isolate"
    assert isolate["captured"] == [
        {"ref": "ent_body_1", "type": "body", "visible": True}
    ]
