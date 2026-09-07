from __future__ import annotations

from app.fusion_cad.inspect import normalize_relation


# =========================================================================
# Task 7 bounded repair: coplanar must report explicit angular + linear
# tolerances for every measured deviation used in matches.
# =========================================================================


def test_normalize_relation_coplanar_reports_angular_and_linear_tolerances():
    res = normalize_relation(
        {
            "operation": "coplanar",
            "relation": "coplanar",
            "matches": True,
            "measured": {"angle_deg": 0.0, "distance_mm": 0.0},
            "tolerance": {"value": 0.001, "unit": "mm"},
            "tolerances": {"angle_deg": 0.02, "distance_mm": 0.001},
            "target_a": "ent_fa",
            "target_b": "ent_fb",
        },
        operation="coplanar",
    )
    assert res.matches is True
    assert res.measured["angle_deg"] == 0.0
    assert res.measured["distance_mm"] == 0.0
    # Every measured deviation used in matches has an explicit tolerance.
    assert res.tolerances == {"angle_deg": 0.02, "distance_mm": 0.001}
    assert res.tolerance.unit == "mm"
    assert res.tolerance.value == 0.001
    assert set(res.measured.keys()) == set(res.tolerances.keys())


def test_normalize_relation_coplanar_contract_preserves_measured_tolerance_pairs():
    res = normalize_relation(
        {
            "operation": "coplanar",
            "relation": "coplanar",
            "matches": False,
            "measured": {"angle_deg": 1.5, "distance_mm": 0.02},
            "tolerance": {"value": 0.001, "unit": "mm"},
            "tolerances": {"angle_deg": 0.01, "distance_mm": 0.001},
            "target_a": "ent_fa",
            "target_b": "ent_fb",
        },
        operation="coplanar",
    )
    assert res.matches is False
    assert res.measured["angle_deg"] == 1.5
    assert res.measured["distance_mm"] == 0.02
    assert res.tolerances["angle_deg"] == 0.01
    assert res.tolerances["distance_mm"] == 0.001