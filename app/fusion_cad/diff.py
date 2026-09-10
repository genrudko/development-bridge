"""Minimal P0 semantic preview diff; the reusable StructuralDiff is P1."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def minimal_semantic_diff(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> dict[str, Any]:
    before_counts = dict(before.get("counts") or {})
    after_counts = dict(after.get("counts") or {})
    categories = sorted(set(before_counts) | set(after_counts))
    before_refs = {str(ref) for ref in before.get("refs") or ()}
    after_refs = {str(ref) for ref in after.get("refs") or ()}
    return {
        "before": {
            "structural_hash": before.get("structural_hash"),
            "counts": before_counts,
        },
        "after": {
            "structural_hash": after.get("structural_hash"),
            "counts": after_counts,
        },
        "counts": {
            key: int(after_counts.get(key, 0)) - int(before_counts.get(key, 0))
            for key in categories
        },
        "refs": {
            "added": sorted(after_refs - before_refs),
            "removed": sorted(before_refs - after_refs),
        },
    }
