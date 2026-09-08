"""Pure logical-text and visibility transformations (no Fusion imports)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.fusion_cad.models import (
    ENTITY_REF_PATTERN,
    EffectiveVisibility,
    FontUsage,
    TextLineage,
)

_ENTITY_REF_RE = re.compile(ENTITY_REF_PATTERN)


def compute_effective_visibility(
    *, type: str, ref: str, local_visible: bool, parents: Sequence[bool] = ()
) -> EffectiveVisibility:
    if _ENTITY_REF_RE.fullmatch(ref) is None:
        raise ValueError(f"invalid opaque entity ref: {ref!r}")
    parent_visible = all(value is True for value in parents)
    return EffectiveVisibility(
        type=type,
        ref=ref,
        local_visible=local_visible,
        parent_visible=parent_visible,
        effective_visible=local_visible and parent_visible,
    )


def build_visibility_restore_plan(
    entities: Sequence[Mapping[str, Any]],
    target_ref: str,
    operation: str = "show_only",
) -> dict[str, Any]:
    if _ENTITY_REF_RE.fullmatch(target_ref) is None:
        raise ValueError(f"invalid opaque target ref: {target_ref!r}")
    captured: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entity in entities:
        ref = entity.get("ref")
        if not isinstance(ref, str) or _ENTITY_REF_RE.fullmatch(ref) is None:
            raise ValueError(f"invalid opaque entity ref: {ref!r}")
        if ref in seen:
            raise ValueError(f"duplicate visibility ref: {ref}")
        seen.add(ref)
        captured.append(
            {
                "ref": ref,
                "type": str(entity.get("type") or entity.get("kind") or "entity"),
                "visible": bool(entity.get("visible", True)),
            }
        )
    if target_ref not in seen:
        raise ValueError("target_ref is not present in the mutation scope")
    if operation not in {"show_only", "isolate"}:
        raise ValueError("restore plans are limited to show_only or isolate")
    return {
        "scope": "own_mutation",
        "operation": operation,
        "target_ref": target_ref,
        "captured": captured,
    }


def apply_visibility_restore_plan(
    plan: Mapping[str, Any], current_state: Mapping[str, Any]
) -> dict[str, Any]:
    if plan.get("scope") != "own_mutation" or not isinstance(plan.get("captured"), list):
        raise ValueError("unverified visibility restore plan")
    restored = dict(current_state)
    seen: set[str] = set()
    for entry in plan["captured"]:
        if not isinstance(entry, Mapping):
            raise TypeError("invalid visibility restore entry")
        ref = entry.get("ref")
        if not isinstance(ref, str) or _ENTITY_REF_RE.fullmatch(ref) is None or ref in seen:
            raise ValueError("invalid or duplicate visibility restore ref")
        if not isinstance(entry.get("visible"), bool):
            raise TypeError("visibility restore value must be boolean")
        seen.add(ref)
        restored[ref] = entry["visible"]
    return restored


def single_current_generation(
    lineages: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    current = [item for item in lineages if item.get("is_current") is True]
    if len(current) != 1:
        raise ValueError(f"expected exactly one current generation, found {len(current)}")
    return current[0]


def collapse_text_generations(
    lineages: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    ordered = sorted(lineages, key=lambda item: int(item.get("generation", 0)))
    current = [item for item in ordered if item.get("is_current") is True]
    return {
        "current": current[-1] if current else None,
        "legacy": [item for item in ordered if item.get("is_current") is not True],
        "has_multiple_current": len(current) > 1,
    }


def normalize_text_lineage(raw: Mapping[str, Any]) -> dict[str, Any]:
    lineage = TextLineage.model_validate(raw)
    font = FontUsage(
        requested=lineage.font_requested,
        used=lineage.font_used,
        fallback_reason=lineage.fallback_reason,
    )
    result = lineage.model_dump(mode="json", exclude={"font_requested", "font_used", "fallback_reason"})
    result["font"] = font.model_dump(mode="json")
    return result
