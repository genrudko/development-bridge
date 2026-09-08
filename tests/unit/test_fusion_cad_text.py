from __future__ import annotations

import json
import re

import pytest
from pydantic import ValidationError

from app.fusion_cad.models import (
    ENTITY_REF_PATTERN,
    TEXT_REF_PATTERN,
    EffectiveVisibility,
    FontUsage,
    TextLineage,
)
from app.fusion_cad.scripts import FusionCadScriptBundle
from app.fusion_cad.text import (
    collapse_text_generations,
    normalize_text_lineage,
    single_current_generation,
)

# Canonical Task 11 Unicode roundtrip payload fixture (Cyrillic + emoji).
UNICODE_TEXT = "РАСПИСАНИЕ ПЫТОК 😈"
UNICODE = UNICODE_TEXT


# =========================================================================
# Opaque TextRef model
# =========================================================================


def test_text_ref_generated_id_is_opaque_and_documented():
    """A generated TextRef must match the opaque pattern and never equal a
    native entity id/token."""
    logical_ref = "text_a1b2c3d4e5f6"
    assert re.match(TEXT_REF_PATTERN, logical_ref) is not None
    # Opaque: the ref must be distinct from any native Fusion entity id.
    native_id = "sketch_17_text_entity_9"
    assert logical_ref != native_id
    # A text_ prefixed ref is a logical TextRef, not an entity-scoped ref.
    assert re.match(ENTITY_REF_PATTERN, logical_ref) is None
    # But an ent_ prefixed TextRef is also accepted (documented pattern).
    assert re.match(TEXT_REF_PATTERN, "ent_text_abc") is not None
    assert re.match(ENTITY_REF_PATTERN, "ent_text_abc") is not None


def test_text_ref_rejects_native_token_and_invalid_text_ref():
    # A raw native Fusion id must never satisfy the opaque TextRef pattern.
    assert re.match(TEXT_REF_PATTERN, "native::adsk::SketchText::token") is None
    assert re.match(TEXT_REF_PATTERN, "not-a-ref") is None


def test_unicode_payload_roundtrips_through_script_bundle():
    """UTF-8 must survive request -> script payload -> result unchanged."""
    bundle = FusionCadScriptBundle()
    script = bundle.build(
        "mutate",
        {"operation": "text_create", "text": UNICODE, "height_mm": 6.0},
    )
    compile(script, "<fusion-cad>", "exec")
    # The script embeds the exact Unicode text with ensure_ascii=False JSON.
    assert UNICODE in script
    # Roundtrip through JSON decoding preserves the exact characters.
    for line in script.splitlines():
        if line.startswith("PAYLOAD_RAW = "):
            raw = line[len("PAYLOAD_RAW = "):]
            decoded = json.loads(json.loads(raw) if raw.startswith('"') else raw)
            assert decoded["text"] == UNICODE
            break
    else:
        pytest.fail("PAYLOAD_RAW not found in rendered script")


# =========================================================================
# Font usage model: requested / used / explicit fallback reason
# =========================================================================


def test_font_usage_requested_used_without_fallback():
    font = FontUsage(requested="Arial", used="Arial", fallback_reason=None)
    assert font.requested == "Arial"
    assert font.used == "Arial"
    assert font.fallback_reason is None


def test_font_usage_explicit_fallback_reason():
    font = FontUsage(
        requested="Noto Sans CJK",
        used="Arial",
        fallback_reason="font_not_found: Noto Sans CJK unavailable; substituted with Arial",
    )
    assert font.fallback_reason is not None
    assert "Noto Sans CJK" in font.fallback_reason


def test_font_usage_fallback_requires_explicit_reason():
    # A fallback used-font that differs from requested MUST carry an explicit reason.
    with pytest.raises(ValidationError):
        FontUsage(requested="Times", used="Arial", fallback_reason=None)


def test_font_usage_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        FontUsage(requested="Arial", used="Arial", fallback_reason=None, extra="x")


# =========================================================================
# Text lineage: TextRef -> sketch -> SketchText -> feature -> outputs with
# exactly one current generation
# =========================================================================


def _create_lineage(logical_ref, generation, is_current, **over):
    base = {
        "logical_ref": logical_ref,
        "generation": generation,
        "is_current": is_current,
        "sketch": "ent_sk_1",
        "sketch_text_id": "ent_sketch_text_abc",
        "feature": "ent_feat_1",
        "outputs": ["ent_body_out_1"],
        "text": UNICODE,
        "font_requested": "Arial",
        "font_used": "Arial",
        "fallback_reason": None,
        "height_mm": 6.0,
    }
    base.update(over)
    return base


def test_font_usage_validator_accepted_via_model_from_lineage():
    # The lineage carries font fields that satisfy strict FontUsage semantics.
    lineage = TextLineage(
        logical_ref="text_a1b2c3d4e5f6",
        generation=1,
        is_current=True,
        sketch="ent_sk_1",
        sketch_text_id="ent_sketch_text_abc",
        feature=None,
        outputs=[],
        text=UNICODE,
        font_requested="Arial",
        font_used="Arial",
        fallback_reason=None,
        height_mm=6.0,
    )
    assert lineage.logical_ref.startswith("text_")
    assert lineage.is_current is True
    assert lineage.font_used == "Arial"


def test_single_current_generation_after_update():
    """After an update, exactly one generation is marked current."""
    lineages = [
        _create_lineage("text_abc123", 1, False, text="OLD", font_requested="Arial", font_used="Arial", fallback_reason=None),
        _create_lineage("text_abc123", 2, True, text=UNICODE, font_requested="Arial", font_used="Arial", fallback_reason=None),
    ]
    current = single_current_generation(lineages)
    assert current is not None
    assert current["generation"] == 2
    assert current["is_current"] is True
    assert current["text"] == UNICODE


def test_single_current_generation_allows_legacy_without_multiple_current():
    lineages = [
        _create_lineage("text_abc123", 1, True),
        _create_lineage("text_abc123", 2, True),
    ]
    with pytest.raises(ValueError):
        single_current_generation(lineages)


def test_collapse_text_generations_keeps_one_current_and_legacy_list():
    lineages = [
        _create_lineage("text_abc123", 1, False, text="AZURE_LEFT_TEXT_01", font_requested="Arial", font_used="Arial", fallback_reason=None),
        _create_lineage("text_abc123", 2, True, text="AZURE_LEFT_TEXT_02", font_requested="Arial", font_used="Arial", fallback_reason=None),
    ]
    result = collapse_text_generations(lineages)
    assert result["current"]["generation"] == 2
    assert len(result["legacy"]) == 1
    assert result["legacy"][0]["generation"] == 1
    assert result["has_multiple_current"] is False


def test_normalize_text_lineage_one_current_generation():
    raw = {
        "logical_ref": "text_abc123",
        "generation": 2,
        "is_current": True,
        "sketch": "ent_sk_1",
        "sketch_text_id": "ent_sketch_text_002",
        "feature": "ent_feat_extrude",
        "outputs": ["ent_body_text_2"],
        "text": UNICODE,
        "font_requested": "Arial",
        "font_used": "Arial",
        "fallback_reason": None,
        "height_mm": 6.0,
    }
    normalized = normalize_text_lineage(raw)
    assert normalized["logical_ref"].startswith("text_")
    assert normalized["is_current"] is True
    assert normalized["text"] == UNICODE
    assert normalized["font"]["requested"] == "Arial"
    assert normalized["font"]["used"] == "Arial"
    assert normalized["font"]["fallback_reason"] is None


def test_effective_visibility_local_and_hierarchical():
    # Top-level local visible -> effective visible.
    eff_root = EffectiveVisibility(
        type="body", ref="ent_body_1", local_visible=True, effective_visible=True
    )
    assert eff_root.effective_visible is True

    # Child hidden because parent hidden (hierarchical).
    eff_child = EffectiveVisibility(
        type="body",
        ref="ent_body_2",
        local_visible=True,
        effective_visible=False,
        parent_visible=False,
    )
    assert eff_child.effective_visible is False
    assert eff_child.parent_visible is False
