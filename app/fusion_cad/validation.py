from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from app.fusion_cad.models import ValidationFinding, ValidationReport

P0_VALIDATION_PROFILES = (
    "parametric_health",
    "model_hygiene",
    "reference_integrity",
    "text_integrity",
    "pre_mutation",
)

_PROFILE_CHECKS = {
    "parametric_health": (
        "feature_health",
        "sketch_health",
        "body_sanity",
        "sketch_constraint_inventory",
        "sketch_profile_inventory",
        "timeline_health",
    ),
    "model_hygiene": (
        "repeated_generation",
        "orphaned_generated_output",
        "role_provenance_inconsistency",
        "near_identical_body",
        "legacy_generated_body",
    ),
    "reference_integrity": ("reference_integrity",),
    "text_integrity": ("dangling_text_output",),
    "pre_mutation": (
        "feature_health",
        "sketch_health",
        "reference_integrity",
        "body_sanity",
        "timeline_health",
    ),
}

_SAFE_EVIDENCE_KEYS = frozenset(
    {
        "available",
        "bbox",
        "bridge_generated",
        "constraints_count",
        "current_generation_count",
        "empty",
        "fully_constrained",
        "generation_count",
        "health",
        "legacy_generated",
        "logical_id",
        "open_profiles_count",
        "orphaned",
        "profiles_count",
        "provenance_valid",
        "role",
        "rolled_back",
        "stale_generation_count",
        "state",
        "valid",
        "volume",
        "volume_delta",
        "bbox_max_delta",
    }
)


def _safe_evidence(raw: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    selected = keys or tuple(_SAFE_EVIDENCE_KEYS)
    clean: dict[str, Any] = {}
    for key in selected:
        if key not in _SAFE_EVIDENCE_KEYS or key not in raw:
            continue
        value = raw[key]
        if value is None or isinstance(value, (bool, int, float, str)):
            clean[key] = value
        elif key == "bbox" and isinstance(value, (list, tuple)):
            clean[key] = [float(item) for item in value if isinstance(item, (int, float))]
    return clean


def _refs(*items: Mapping[str, Any]) -> tuple[str, ...]:
    refs = []
    for item in items:
        ref = item.get("ref")
        if isinstance(ref, str) and ref.startswith("ent_") and ref not in refs:
            refs.append(ref)
    return tuple(refs)


def _finding(
    check_id: str,
    severity: str,
    message: str,
    *,
    items: Sequence[Mapping[str, Any]] = (),
    evidence: Mapping[str, Any] | None = None,
    action: str | None = None,
) -> ValidationFinding:
    return ValidationFinding(
        check_id=check_id,
        severity=severity,
        message=message,
        entity_refs=_refs(*items),
        evidence=_safe_evidence(evidence or {}),
        suggested_action=action,
    )


def _bbox_values(body: Mapping[str, Any]) -> tuple[float, ...] | None:
    bbox = body.get("bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) == 6:
        try:
            values = tuple(float(value) for value in bbox)
        except (TypeError, ValueError):
            return None
        return values if all(math.isfinite(value) for value in values) else None
    return None


def _near_identical(a: Mapping[str, Any], b: Mapping[str, Any]) -> tuple[float, float] | None:
    try:
        av = float(a.get("volume"))
        bv = float(b.get("volume"))
    except (TypeError, ValueError):
        return None
    ab = _bbox_values(a)
    bb = _bbox_values(b)
    if ab is None or bb is None or not math.isfinite(av) or not math.isfinite(bv):
        return None
    volume_delta = abs(av - bv)
    bbox_delta = max(abs(left - right) for left, right in zip(ab, bb, strict=True))
    volume_scale = max(abs(av), abs(bv), 1.0)
    bbox_scale = max(*(abs(value) for value in ab + bb), 1.0)
    if volume_delta <= 1e-5 * volume_scale and bbox_delta <= 1e-5 * bbox_scale:
        return volume_delta, bbox_delta
    return None


def validate_model_evidence(
    evidence: Mapping[str, Any],
    *,
    profiles: Sequence[str] = P0_VALIDATION_PROFILES,
    checks: Sequence[str] = (),
    snapshot_id: str | None = None,
    model_revision: str | None = None,
) -> ValidationReport:
    """Classify normalized, read-only Fusion facts under deterministic P0 policy."""
    selected_profiles = tuple(dict.fromkeys(profiles))
    unknown = [profile for profile in selected_profiles if profile not in _PROFILE_CHECKS]
    if unknown or not selected_profiles:
        raise ValueError("Validation profiles must be non-empty P0 profile names")

    available_checks = tuple(
        dict.fromkeys(
            check
            for profile in selected_profiles
            for check in _PROFILE_CHECKS[profile]
        )
    )
    if checks:
        unknown_checks = [check for check in checks if check not in available_checks]
        if unknown_checks:
            raise ValueError("Requested checks are not enabled by selected profiles")
        checks_run = tuple(dict.fromkeys(checks))
    else:
        checks_run = available_checks

    features = [x for x in evidence.get("features", ()) if isinstance(x, Mapping)]
    sketches = [x for x in evidence.get("sketches", ()) if isinstance(x, Mapping)]
    references = [x for x in evidence.get("references", ()) if isinstance(x, Mapping)]
    bodies = [x for x in evidence.get("bodies", ()) if isinstance(x, Mapping)]
    text_outputs = [x for x in evidence.get("text_outputs", ()) if isinstance(x, Mapping)]
    findings: list[ValidationFinding] = []
    pre_mutation = "pre_mutation" in selected_profiles

    if "feature_health" in checks_run:
        for feature in features:
            health = str(feature.get("health", "unknown")).lower()
            if feature.get("valid") is False or health in {"error", "failed", "broken"}:
                findings.append(_finding(
                    "feature_health", "error" if pre_mutation else "warn",
                    "Feature health evidence indicates an invalid or broken feature",
                    items=(feature,), evidence=feature,
                    action="Inspect and resolve the feature before mutation",
                ))

    if "sketch_health" in checks_run:
        for sketch in sketches:
            health = str(sketch.get("health", "unknown")).lower()
            if sketch.get("valid") is False or health in {"error", "failed", "broken"}:
                findings.append(_finding(
                    "sketch_health", "error" if pre_mutation else "warn",
                    "Sketch health evidence indicates an invalid or broken sketch",
                    items=(sketch,), evidence=sketch,
                    action="Inspect and resolve the sketch before mutation",
                ))

    if "reference_integrity" in checks_run:
        for reference in references:
            if str(reference.get("state", "unknown")).lower() in {
                "broken", "missing", "stale", "ambiguous", "unresolved"
            }:
                findings.append(_finding(
                    "reference_integrity", "error" if pre_mutation else "warn",
                    "Reference evidence is not safely resolved",
                    items=(reference,), evidence=reference,
                    action="Resolve the reference explicitly before mutation",
                ))

    if "body_sanity" in checks_run:
        for body in bodies:
            volume = body.get("volume")
            invalid_volume = not isinstance(volume, (int, float)) or not math.isfinite(float(volume)) or float(volume) <= 0.0
            if body.get("valid") is False or body.get("empty") is True or invalid_volume:
                findings.append(_finding(
                    "body_sanity", "error",
                    "Body is invalid, empty, or has non-positive volume",
                    items=(body,), evidence=body,
                    action="Inspect body construction and confirm valid solid geometry",
                ))

    if "sketch_constraint_inventory" in checks_run:
        for sketch in sketches:
            if sketch.get("fully_constrained") is False:
                findings.append(_finding(
                    "sketch_constraint_inventory", "warn",
                    "Sketch is not fully constrained in this profile context",
                    items=(sketch,), evidence=sketch,
                    action="Review constraint intent before geometry-sensitive changes",
                ))

    if "sketch_profile_inventory" in checks_run:
        for sketch in sketches:
            if int(sketch.get("open_profiles_count") or 0) > 0:
                findings.append(_finding(
                    "sketch_profile_inventory", "warn",
                    "Sketch contains open profiles in this profile context",
                    items=(sketch,), evidence=sketch,
                    action="Review whether open profiles are intentional",
                ))

    if "timeline_health" in checks_run:
        timeline = evidence.get("timeline")
        timeline = timeline if isinstance(timeline, Mapping) else {"available": False}
        if timeline.get("available") is False or timeline.get("rolled_back") is True:
            findings.append(_finding(
                "timeline_health", "error" if pre_mutation or timeline.get("rolled_back") else "warn",
                "Timeline is unavailable or rolled back",
                evidence=timeline,
                action="Restore a healthy timeline state before mutation",
            ))

    if "repeated_generation" in checks_run:
        generations: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for body in bodies:
            logical_id = body.get("logical_id")
            if isinstance(logical_id, str) and logical_id:
                generations[logical_id].append(body)
        for logical_id, group in sorted(generations.items()):
            if len(group) <= 1:
                continue
            current = [body for body in group if body.get("current") is True]
            stale = [body for body in group if body.get("current") is not True]
            findings.append(_finding(
                "repeated_generation", "warn",
                "Multiple logical generations were observed",
                items=stale,
                evidence={
                    "logical_id": logical_id,
                    "generation_count": len(group),
                    "current_generation_count": len(current),
                    "stale_generation_count": len(stale),
                },
                action="Review generation provenance and choose retained outputs explicitly",
            ))

    if "orphaned_generated_output" in checks_run:
        for body in bodies:
            if body.get("bridge_generated") is True and body.get("orphaned") is True:
                findings.append(_finding(
                    "orphaned_generated_output", "warn",
                    "Bridge-generated output has no current logical owner",
                    items=(body,), evidence=body,
                    action="Review ownership and provenance before any cleanup",
                ))

    if "role_provenance_inconsistency" in checks_run:
        for body in bodies:
            inconsistent = body.get("provenance_valid") is False or (
                body.get("bridge_generated") is True and not body.get("role")
            )
            if inconsistent:
                findings.append(_finding(
                    "role_provenance_inconsistency", "warn",
                    "Role and provenance evidence are inconsistent",
                    items=(body,), evidence=body,
                    action="Review and correct metadata through an explicit mutation",
                ))

    if "near_identical_body" in checks_run:
        for index, left in enumerate(bodies):
            for right in bodies[index + 1:]:
                delta = _near_identical(left, right)
                if delta is not None:
                    findings.append(_finding(
                        "near_identical_body", "warn",
                        "Bodies have near-identical bounding boxes and volumes",
                        items=(left, right),
                        evidence={"volume_delta": delta[0], "bbox_max_delta": delta[1]},
                        action="Compare candidates and resolve duplication intentionally",
                    ))

    if "legacy_generated_body" in checks_run:
        for body in bodies:
            if body.get("legacy_generated") is True:
                findings.append(_finding(
                    "legacy_generated_body", "warn",
                    "Legacy generated body evidence was observed",
                    items=(body,), evidence=body,
                    action="Review legacy output provenance before any migration",
                ))

    if "dangling_text_output" in checks_run:
        known_refs = {ref for item in bodies + text_outputs for ref in _refs(item)}
        for output in text_outputs:
            output_refs = output.get("output_refs")
            dangling = output.get("source_ref") in (None, "") or (
                isinstance(output_refs, (list, tuple))
                and any(ref not in known_refs for ref in output_refs)
            )
            if dangling:
                findings.append(_finding(
                    "dangling_text_output", "warn",
                    "Text output is missing its source or a referenced output",
                    items=(output,), evidence=output,
                    action="Review text lineage and recreate links explicitly if required",
                ))

    verdict = "RED" if any(f.severity == "error" for f in findings) else (
        "WARN" if any(f.severity == "warn" for f in findings) else "GREEN"
    )
    return ValidationReport(
        verdict=verdict,
        profiles=selected_profiles,
        checks_run=checks_run,
        findings=findings,
        summary=f"Validation {verdict}: {len(findings)} finding(s)",
        snapshot_id=snapshot_id,
        model_revision=model_revision,
    )
