from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


def canonical_sort_key(item: Any) -> str:
    """Generate a deterministic string sort key for any item."""
    if isinstance(item, (dict, list, tuple)):
        try:
            return json.dumps(
                item, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            )
        except (TypeError, ValueError):
            return str(item)
    return str(item)


def sort_canonical_items(items: Sequence[Any]) -> list[Any]:
    """Deterministically sort a sequence of canonicalized items."""
    try:
        return sorted(items, key=canonical_sort_key)
    except (TypeError, ValueError):
        return list(items)


def canonicalize_value(
    val: Any,
    *,
    path: tuple[str, ...] = (),
    unordered_collections: frozenset[str] = frozenset(),
) -> Any:
    """Recursively canonicalize semantic model data for deterministic hashing.

    Rules:
    - Primitives (None, bool, int, str) returned as is.
    - Floats rounded to 6 decimal places (-0.0 normalized to 0.0).
    - Mapping keys are deterministically sorted.
    - Sets and frozensets are sorted by stable canonical JSON serialization.
    - Lists and tuples preserve order by default (matrices, vectors, points,
      component paths, topology sequences remain ordered).
    - If path[-1] is explicitly in unordered_collections, the sequence is sorted.
    """
    if val is None or isinstance(val, (bool, int, str)):
        return val
    if isinstance(val, float):
        rounded = round(val, 6)
        return 0.0 if rounded == 0.0 else rounded
    if isinstance(val, Mapping):
        return {
            k: canonicalize_value(
                val[k],
                path=(*path, str(k)),
                unordered_collections=unordered_collections,
            )
            for k in sorted(val.keys())
        }
    if isinstance(val, (set, frozenset)):
        canonical_items = [
            canonicalize_value(
                x,
                path=(*path, "item"),
                unordered_collections=unordered_collections,
            )
            for x in val
        ]
        return sort_canonical_items(canonical_items)
    if isinstance(val, (list, tuple)):
        canonical_items = [
            canonicalize_value(
                x,
                path=(*path, str(idx)),
                unordered_collections=unordered_collections,
            )
            for idx, x in enumerate(val)
        ]
        if path and path[-1] in unordered_collections:
            sorted_items = sort_canonical_items(canonical_items)
            return type(val)(sorted_items)
        return type(val)(canonical_items)
    return str(val)
