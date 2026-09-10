from __future__ import annotations

from app.fusion_cad.validation import P0_VALIDATION_PROFILES, validate_model_evidence


def _entity(ref: str, **facts: object) -> dict[str, object]:
    return {"ref": ref, **facts}


def test_profiles_are_exact_and_unconstrained_sketch_is_contextual() -> None:
    evidence = {
        "sketches": [
            _entity(
                "ent_sketch_1",
                valid=True,
                health="healthy",
                fully_constrained=False,
                constraints_count=0,
                profiles_count=1,
                open_profiles_count=1,
            )
        ],
        "timeline": {"available": True, "rolled_back": False},
    }

    assert P0_VALIDATION_PROFILES == (
        "parametric_health",
        "model_hygiene",
        "reference_integrity",
        "text_integrity",
        "pre_mutation",
    )
    health = validate_model_evidence(evidence, profiles=("parametric_health",))
    assert health.verdict == "WARN"
    assert {f.check_id for f in health.findings} == {
        "sketch_constraint_inventory",
        "sketch_profile_inventory",
    }
    assert all(f.severity == "warn" for f in health.findings)

    references = validate_model_evidence(
        evidence, profiles=("reference_integrity",)
    )
    assert references.verdict == "GREEN"
    assert references.findings == ()


def test_pre_mutation_broken_feature_and_reference_are_red() -> None:
    report = validate_model_evidence(
        {
            "features": [
                _entity("ent_feature_1", valid=False, health="error")
            ],
            "references": [
                _entity("ent_feature_1", target_ref="ent_body_1", state="broken")
            ],
            "timeline": {"available": True, "rolled_back": False},
        },
        profiles=("pre_mutation",),
    )

    assert report.verdict == "RED"
    assert {f.check_id for f in report.findings} == {
        "feature_health",
        "reference_integrity",
    }
    assert all(f.severity == "error" for f in report.findings)
    assert all(f.suggested_action for f in report.findings)


def test_exact_health_body_and_timeline_evidence() -> None:
    report = validate_model_evidence(
        {
            "features": [_entity("ent_feature_1", valid=True, health="healthy")],
            "sketches": [
                _entity(
                    "ent_sketch_1",
                    valid=True,
                    health="healthy",
                    fully_constrained=True,
                    constraints_count=4,
                    profiles_count=1,
                    open_profiles_count=0,
                )
            ],
            "references": [_entity("ent_feature_1", state="resolved")],
            "bodies": [
                _entity(
                    "ent_body_1",
                    valid=True,
                    empty=False,
                    volume=0.0,
                    bbox=[0, 0, 0, 1, 1, 0],
                )
            ],
            "timeline": {"available": True, "rolled_back": True},
        },
        profiles=("parametric_health", "reference_integrity"),
    )

    assert report.verdict == "RED"
    by_id = {finding.check_id: finding for finding in report.findings}
    assert by_id["body_sanity"].evidence["volume"] == 0.0
    assert by_id["timeline_health"].evidence["rolled_back"] is True
    assert "feature_health" in report.checks_run
    assert "sketch_health" in report.checks_run
    assert "reference_integrity" in report.checks_run
    assert "body_sanity" in report.checks_run
    assert "sketch_constraint_inventory" in report.checks_run
    assert "sketch_profile_inventory" in report.checks_run
    assert "timeline_health" in report.checks_run


def test_azure_stale_generations_are_evidence_only_and_input_is_unchanged() -> None:
    bodies = [
        _entity(
            f"ent_azure_{index}",
            name=f"AZURE_LEFT_TEXT_{index:02d}",
            logical_id="AZURE_LEFT_TEXT",
            generation=index,
            current=index == 47,
            bridge_generated=True,
            role="text_output",
            provenance_valid=True,
            volume=10.0,
            bbox=[0, 0, 0, 10, 2, 1],
        )
        for index in range(1, 48)
    ]
    evidence = {"bodies": bodies, "text_outputs": []}
    before = [dict(body) for body in bodies]

    report = validate_model_evidence(evidence, profiles=("model_hygiene",))

    assert bodies == before
    repeated = next(f for f in report.findings if f.check_id == "repeated_generation")
    assert repeated.severity == "warn"
    assert len(repeated.entity_refs) == 46
    assert "ent_azure_47" not in repeated.entity_refs
    assert repeated.evidence["current_generation_count"] == 1
    assert repeated.evidence["stale_generation_count"] == 46
    assert "delete" not in (repeated.suggested_action or "").lower()


def test_hygiene_heuristics_cover_required_classes_without_repair() -> None:
    report = validate_model_evidence(
        {
            "bodies": [
                _entity(
                    "ent_body_1",
                    name="Bridge Text 01",
                    bridge_generated=True,
                    orphaned=True,
                    role="text_output",
                    provenance_valid=False,
                    legacy_generated=True,
                    volume=10.0,
                    bbox=[0, 0, 0, 1, 2, 3],
                ),
                _entity(
                    "ent_body_2",
                    name="Bridge Text 02",
                    bridge_generated=True,
                    orphaned=False,
                    role="solid",
                    provenance_valid=True,
                    volume=10.000001,
                    bbox=[0, 0, 0, 1, 2, 3.000001],
                ),
            ],
            "text_outputs": [
                _entity("ent_text_1", source_ref=None, output_refs=["ent_missing"])
            ],
        },
        profiles=("model_hygiene", "text_integrity"),
    )

    assert {
        "orphaned_generated_output",
        "role_provenance_inconsistency",
        "near_identical_body",
        "legacy_generated_body",
        "dangling_text_output",
    } <= {f.check_id for f in report.findings}
    assert all("delete" not in (f.suggested_action or "").lower() for f in report.findings)


def test_checks_filter_and_public_evidence_are_sanitized() -> None:
    report = validate_model_evidence(
        {
            "features": [
                _entity(
                    "ent_feature_1",
                    valid=False,
                    health="error",
                    native_token="secret-native-token",
                    internal_hint={"entityToken": "nested-secret"},
                    exception="ValueError: private failure",
                )
            ]
        },
        profiles=("parametric_health",),
        checks=("feature_health",),
    )

    assert report.checks_run == ("feature_health",)
    serialized = report.model_dump_json()
    assert "secret-native-token" not in serialized
    assert "nested-secret" not in serialized
    assert "private failure" not in serialized
