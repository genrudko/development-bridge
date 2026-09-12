from __future__ import annotations

from typing import Any


def tool_mutates(tool_name: str, advertised_tools: list[dict[str, Any]]) -> bool:
    """Return advertised mutation truth, failing closed for missing/unknown metadata."""
    for item in advertised_tools:
        if not isinstance(item, dict) or item.get("name") != tool_name:
            continue
        metadata = item.get("x_blender_hub")
        if isinstance(metadata, dict) and metadata.get("mutating") is False:
            return False
        return True
    return True


def effective_journal(
    tool_name: str,
    advertised_tools: list[dict[str, Any]],
    supplied: dict[str, Any] | None,
) -> dict[str, Any]:
    """Preserve caller metadata but derive the mutation flag from Hub evidence."""
    journal = dict(supplied or {})
    journal["mutation"] = tool_mutates(tool_name, advertised_tools)
    return journal
