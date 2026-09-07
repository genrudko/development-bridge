from __future__ import annotations

import re

import pytest

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.models import ViewRefSummary
from app.fusion_cad.views import (
    CAMERA_REVISION_PATTERN,
    SECTION_REVISION_PATTERN,
    VISIBILITY_REVISION_PATTERN,
    ViewRefStore,
    camera_revision,
    canonicalize_section_payload,
    canonicalize_visibility_payload,
    normalize_camera_context,
    section_revision,
    visibility_revision,
)


def _camera_raw(**overrides):
    payload = {
        "eye": [10.0, 20.0, 30.0],
        "target": [0.0, 0.0, 0.0],
        "up": [0.0, 0.0, 1.0],
        "projection": "perspective",
        "fov_deg": 45.0,
        "viewport_width": 1920,
        "viewport_height": 1080,
    }
    payload.update(overrides)
    return payload


def _visibility_raw(**overrides):
    payload = [
        {
            "kind": "occurrence",
            "full_path_name": "Root:Left",
            "is_visible": True,
            "effective_visibility": True,
        },
        {
            "kind": "body",
            "full_path_name": "Root:Left:Body1",
            "is_visible": True,
            "effective_visibility": True,
        },
    ]
    if overrides.get("hide_body"):
        payload[1] = {
            "kind": "body",
            "full_path_name": "Root:Left:Body1",
            "is_visible": False,
            "effective_visibility": False,
        }
    return payload


def _bind_record(store: ViewRefStore, view_ref: str = "view_1", **kwargs):
    camera = kwargs.get("camera") or normalize_camera_context(_camera_raw())
    visibility = kwargs.get("visibility")
    if visibility is None:
        visibility = canonicalize_visibility_payload(_visibility_raw())
    section = kwargs.get("section")
    if section is None:
        section = canonicalize_section_payload(None)
    return store.bind(
        view_ref=view_ref,
        document_ref=kwargs.get("document_ref", "doc_1"),
        model_revision=kwargs.get("model_revision", "rev_1"),
        camera=camera,
        visibility_state=visibility,
        section_state=section,
        image=kwargs.get(
            "image", "https://example.test/desktop-results/exports/resource1"
        ),
        width=kwargs.get("width"),
        height=kwargs.get("height"),
    )


def _full_current_context(**tweaks):
    camera = normalize_camera_context(_camera_raw())
    visibility = canonicalize_visibility_payload(_visibility_raw())
    section = canonicalize_section_payload(None)
    ctx = {
        "document_ref": "doc_1",
        "model_revision": "rev_1",
        "camera_revision": camera_revision(camera),
        "visibility_revision": visibility_revision(visibility),
        "section_revision": section_revision(section),
        "viewport_width": 1920,
        "viewport_height": 1080,
    }
    ctx.update(tweaks)
    return ctx


# ---------------------------------------------------------------------------
# Deterministic camera context canonicalization
# ---------------------------------------------------------------------------


def test_normalize_camera_context_returns_deterministic_context():
    camera = normalize_camera_context(_camera_raw())
    assert camera.eye == (10.0, 20.0, 30.0)
    assert camera.target == (0.0, 0.0, 0.0)
    assert camera.up == (0.0, 0.0, 1.0)
    assert camera.projection == "perspective"
    assert camera.fov_deg == 45.0
    assert camera.viewport_width == 1920
    assert camera.viewport_height == 1080


def test_normalize_camera_context_rounds_floats_deterministically():
    camera = normalize_camera_context(
        _camera_raw(eye=[10.0000001, 20.0000004, 30.0000004])
    )
    assert camera.eye == (10.0, 20.0, 30.0)


def test_normalize_camera_context_requires_all_fields_fail_closed():
    for missing in ("eye", "target", "up", "projection", "viewport_width"):
        raw = _camera_raw()
        raw.pop(missing)
        with pytest.raises(FusionCadError) as exc:
            normalize_camera_context(raw)
        assert exc.value.code == ErrorCode.INVALID_ARGUMENT


def test_perspective_requires_fov_fail_closed():
    raw = _camera_raw(fov_deg=None)
    with pytest.raises(FusionCadError) as exc:
        normalize_camera_context(raw)
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT


def test_orthographic_allows_null_fov():
    camera = normalize_camera_context(
        _camera_raw(projection="orthographic", fov_deg=None)
    )
    assert camera.projection == "orthographic"
    assert camera.fov_deg is None


def test_camera_revision_is_deterministic_and_patterned():
    rev_a = camera_revision(normalize_camera_context(_camera_raw()))
    rev_b = camera_revision(normalize_camera_context(_camera_raw()))
    assert rev_a == rev_b
    assert re.match(CAMERA_REVISION_PATTERN, rev_a)


def test_different_eye_changes_camera_revision():
    rev_a = camera_revision(normalize_camera_context(_camera_raw()))
    rev_b = camera_revision(
        normalize_camera_context(_camera_raw(eye=[11.0, 20.0, 30.0]))
    )
    assert rev_a != rev_b


def test_viewport_dimension_change_changes_camera_revision():
    rev_a = camera_revision(normalize_camera_context(_camera_raw()))
    rev_b = camera_revision(
        normalize_camera_context(_camera_raw(viewport_width=1921))
    )
    assert rev_a != rev_b


def test_visibility_and_section_revisions_are_deterministic_and_sorted():
    vis = canonicalize_visibility_payload(_visibility_raw())
    vis_rev = visibility_revision(vis)
    assert re.match(VISIBILITY_REVISION_PATTERN, vis_rev)
    # Reversed order must produce identical revision (sorted deterministically)
    reversed_raw = list(reversed(_visibility_raw()))
    vis_rev2 = visibility_revision(canonicalize_visibility_payload(reversed_raw))
    assert vis_rev2 == vis_rev

    sec = canonicalize_section_payload(None)
    sec_rev = section_revision(sec)
    assert re.match(SECTION_REVISION_PATTERN, sec_rev)
    assert section_revision(canonicalize_section_payload(None)) == sec_rev


def test_visibility_change_changes_visibility_revision():
    vis_a = canonicalize_visibility_payload(_visibility_raw())
    vis_b = canonicalize_visibility_payload(_visibility_raw(hide_body=True))
    assert visibility_revision(vis_a) != visibility_revision(vis_b)


def test_visibility_global_object_visibility_flag_change_invalidates_revision():
    vis_a = canonicalize_visibility_payload({
        "global": {"object_visibility": {"isAllObjectsVisible": True}},
        "entries": _visibility_raw(),
    })
    vis_b = canonicalize_visibility_payload({
        "global": {"object_visibility": {"isAllObjectsVisible": False}},
        "entries": _visibility_raw(),
    })
    assert visibility_revision(vis_a) != visibility_revision(vis_b)
    # The global flag is part of the canonical state so identical entries with a
    # different global display setting can never hash identically.
    assert vis_a["global"] != vis_b["global"]


def test_visibility_duplicate_component_names_in_different_occurrences_not_colliding():
    # Two occurrences "Occ1"/"Occ2" reference the same component "Part1" and its
    # body "Body1": component-name-only keys would collide. Occurrence-qualified
    # full paths and native tokens must distinguish them.
    entry_occ1 = [
        {
            "kind": "body",
            "full_path_name": "Root:Occ1:Part1:Body1",
            "is_visible": True,
            "effective_visibility": True,
            "native_token": "AQAA-occ1-body1",
        }
    ]
    entry_occ2 = [
        {
            "kind": "body",
            "full_path_name": "Root:Occ2:Part1:Body1",
            "is_visible": True,
            "effective_visibility": True,
            "native_token": "AQAA-occ2-body1",
        }
    ]
    vis_a = canonicalize_visibility_payload(entry_occ1)
    vis_b = canonicalize_visibility_payload(entry_occ2)
    assert visibility_revision(vis_a) != visibility_revision(vis_b)
    # Hiding the body in only one occurrence is a distinct state.
    vis_occ1_hidden = canonicalize_visibility_payload([
        {
            "kind": "body",
            "full_path_name": "Root:Occ1:Part1:Body1",
            "is_visible": False,
            "effective_visibility": False,
            "native_token": "AQAA-occ1-body1",
        }
    ])
    assert visibility_revision(vis_occ1_hidden) != visibility_revision(vis_b)


# ---------------------------------------------------------------------------
# Deterministic section state (Findings 4)
# ---------------------------------------------------------------------------


def _section_transform_base():
    return [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def _section_payload(transform, is_visible=True, ident="sec_1"):
    return canonicalize_section_payload({
        "active": True,
        "type": "section",
        "global_visible": True,
        "sections": [
            {
                "id": ident,
                "name": "Plane1",
                "is_visible": is_visible,
                "transform": transform,
            }
        ],
    })


def test_section_visible_state_and_moved_transform_change_section_revision():
    base = _section_payload(_section_transform_base())
    moved = _section_payload([
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        10.0, 20.0, 30.0, 1.0,
    ])
    assert section_revision(base) != section_revision(moved)
    hidden = _section_payload(_section_transform_base(), is_visible=False)
    assert section_revision(base) != section_revision(hidden)
    assert base["active"] is True
    assert hidden["active"] is False
    assert base["count"] == 1
    assert base["sections"][0]["id"] == "sec_1"
    assert base["sections"][0]["transform"] == _section_transform_base()


def test_section_canonicalize_rejects_malformed_section_item():
    # A name-only identity is accepted as the stable identity fallback.
    named = canonicalize_section_payload({
        "active": True,
        "sections": [{"name": "NamedOnly", "is_visible": True, "transform": None}],
    })
    assert named["sections"][0]["id"] == "NamedOnly"
    # A section without any usable identity (no id/name/entityToken) fails closed.
    with pytest.raises(FusionCadError) as exc:
        canonicalize_section_payload({
            "active": True,
            "sections": [{"is_visible": True, "transform": None}],
        })
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT
    with pytest.raises(FusionCadError) as exc:
        canonicalize_section_payload({
            "active": True,
            "sections": [
                {
                    "id": "sec_1",
                    "is_visible": True,
                    "transform": [1.0, 0.0, 0.0],
                }
            ],
        })
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT
    with pytest.raises(FusionCadError) as exc:
        canonicalize_section_payload({
            "active": True,
            "sections": [{"id": "sec_1", "transform": None}],
        })
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT


def test_section_no_sections_remains_deterministic_disabled():
    sec = canonicalize_section_payload(None)
    assert sec["active"] is False
    assert sec["sections"] == []
    assert sec["count"] == 0


# ---------------------------------------------------------------------------
# ViewRefStore binding, immutability, and freshness
# ---------------------------------------------------------------------------


def test_bind_stores_immutable_record_and_identical_context_is_fresh():
    store = ViewRefStore()
    record = _bind_record(store, view_ref="view_abc")
    assert store.get("view_abc") is record
    assert record.view_ref == "view_abc"
    assert record.document_ref == "doc_1"
    assert record.model_revision == "rev_1"
    assert record.camera_revision.startswith("cam_")
    assert record.visibility_revision.startswith("vis_")
    assert record.section_revision.startswith("sec_")
    assert record.viewport_width == 1920
    assert record.viewport_height == 1080
    # Identical context asserts fresh
    assert store.assert_fresh("view_abc", current_context=_full_current_context()) is record


def test_bind_refuses_overwrite_same_view_ref():
    store = ViewRefStore()
    _bind_record(store, view_ref="view_x")
    with pytest.raises(FusionCadError) as exc:
        _bind_record(store, view_ref="view_x")
    assert exc.value.code == ErrorCode.PRECONDITION_FAILED


def test_assert_fresh_unknown_view_ref_returns_stale():
    store = ViewRefStore()
    _bind_record(store, view_ref="view_ok")
    with pytest.raises(FusionCadError) as exc:
        store.assert_fresh("view_missing", current_context=_full_current_context())
    assert exc.value.code == ErrorCode.VIEW_STALE


def test_stale_on_model_revision_change():
    store = ViewRefStore()
    _bind_record(store, view_ref="view_m")
    ctx = _full_current_context(model_revision="rev_2")
    with pytest.raises(FusionCadError) as exc:
        store.assert_fresh("view_m", current_context=ctx)
    assert exc.value.code == ErrorCode.VIEW_STALE


def test_stale_on_camera_revision_change():
    store = ViewRefStore()
    _bind_record(store, view_ref="view_c")
    changed = camera_revision(normalize_camera_context(_camera_raw(eye=[1.0, 0.0, 0.0])))
    ctx = _full_current_context(camera_revision=changed)
    with pytest.raises(FusionCadError) as exc:
        store.assert_fresh("view_c", current_context=ctx)
    assert exc.value.code == ErrorCode.VIEW_STALE


def test_stale_on_visibility_revision_change():
    store = ViewRefStore()
    _bind_record(store, view_ref="view_v")
    changed_vis = canonicalize_visibility_payload(_visibility_raw(hide_body=True))
    ctx = _full_current_context(visibility_revision=visibility_revision(changed_vis))
    with pytest.raises(FusionCadError) as exc:
        store.assert_fresh("view_v", current_context=ctx)
    assert exc.value.code == ErrorCode.VIEW_STALE


def test_stale_on_viewport_dimension_change():
    store = ViewRefStore()
    _bind_record(store, view_ref="view_w")
    ctx = _full_current_context(viewport_width=1921)
    with pytest.raises(FusionCadError) as exc:
        store.assert_fresh("view_w", current_context=ctx)
    assert exc.value.code == ErrorCode.VIEW_STALE


def test_stale_on_section_state_change():
    store = ViewRefStore()
    _bind_record(store, view_ref="view_s")
    changed_sec = canonicalize_section_payload({"active": False, "type": "front"})
    ctx = _full_current_context(section_revision=section_revision(changed_sec))
    with pytest.raises(FusionCadError) as exc:
        store.assert_fresh("view_s", current_context=ctx)
    assert exc.value.code == ErrorCode.VIEW_STALE


def test_assert_fresh_missing_required_dimension_fails_closed():
    store = ViewRefStore()
    _bind_record(store, view_ref="view_missing_dim")
    # Omit camera_revision: cannot prove camera freshness -> fail closed
    ctx = _full_current_context()
    del ctx["camera_revision"]
    with pytest.raises(FusionCadError) as exc:
        store.assert_fresh("view_missing_dim", current_context=ctx)
    assert exc.value.code == ErrorCode.VIEW_STALE


def test_assert_fresh_rejects_wrong_document_despite_identical_hashes():
    store = ViewRefStore()
    _bind_record(store, view_ref="view_doc", document_ref="doc_A")
    camera = normalize_camera_context(_camera_raw())
    visibility = canonicalize_visibility_payload(_visibility_raw())
    section = canonicalize_section_payload(None)
    ctx = {
        # Same model rev and identical camera/visibility/section hashes as the
        # bound view, but the active/current document identity differs.
        "document_ref": "doc_B",
        "model_revision": "rev_1",
        "camera_revision": camera_revision(camera),
        "visibility_revision": visibility_revision(visibility),
        "section_revision": section_revision(section),
        "viewport_width": 1920,
        "viewport_height": 1080,
    }
    with pytest.raises(FusionCadError) as exc:
        store.assert_fresh("view_doc", current_context=ctx)
    assert exc.value.code == ErrorCode.WRONG_DOCUMENT


def test_assert_fresh_missing_document_ref_fails_closed():
    store = ViewRefStore()
    _bind_record(store, view_ref="view_nodoc")
    ctx = _full_current_context()
    del ctx["document_ref"]
    with pytest.raises(FusionCadError) as exc:
        store.assert_fresh("view_nodoc", current_context=ctx)
    assert exc.value.code == ErrorCode.VIEW_STALE


def test_stable_identical_context_freshness_shared_across_records():
    store = ViewRefStore()
    _bind_record(store, view_ref="view_a1")
    _bind_record(store, view_ref="view_a2")
    store.assert_fresh("view_a1", current_context=_full_current_context())
    store.assert_fresh("view_a2", current_context=_full_current_context())
    # Both records share the same camera/visibility/section revisions
    rec1 = store.get("view_a1")
    rec2 = store.get("view_a2")
    assert rec1.camera_revision == rec2.camera_revision
    assert rec1.visibility_revision == rec2.visibility_revision
    assert rec1.model_revision == rec2.model_revision


def test_set_image_promotes_placeholder_to_real_external_uri_once():
    store = ViewRefStore()
    record = _bind_record(store, view_ref="view_uri")
    assert record.image == "https://example.test/desktop-results/exports/resource1"
    promoted = store.set_image(
        "view_uri", "https://example.test/desktop-results/exports/emitted-real-uri"
    )
    assert promoted is store.get("view_uri")
    assert promoted.image == "https://example.test/desktop-results/exports/emitted-real-uri"
    # Every other immutable field is preserved
    assert promoted.model_revision == record.model_revision
    assert promoted.camera_revision == record.camera_revision
    assert promoted.visibility_revision == record.visibility_revision
    assert promoted.section_revision == record.section_revision
    with pytest.raises(FusionCadError) as exc:
        store.set_image("view_missing", "https://example.test/x")
    assert exc.value.code == ErrorCode.REF_STALE


def test_viewref_summary_public_metadata_matches_summary_shape():
    store = ViewRefStore()
    record = _bind_record(
        store,
        view_ref="view_summary",
        image="https://example.test/desktop-results/exports/emitted-real-uri",
    )
    summary = record.to_summary()
    assert isinstance(summary, ViewRefSummary)
    # Public shape exactly matches ViewRefSummary fields
    public = summary.model_dump(exclude_none=True)
    assert set(public.keys()) == {
        "view_ref",
        "model_revision",
        "camera_revision",
        "visibility_revision",
        "width",
        "height",
        "image",
    }
    assert public["view_ref"] == "view_summary"
    assert public["model_revision"] == "rev_1"
    assert public["width"] == 1920
    assert public["height"] == 1080
    # The public image equals the real emitted image URI; no fabricated
    # resource://views/... placeholder may ever surface.
    assert public["image"] == "https://example.test/desktop-results/exports/emitted-real-uri"
    assert not public["image"].startswith("resource://")