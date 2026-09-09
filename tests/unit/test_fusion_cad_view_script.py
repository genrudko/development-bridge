from __future__ import annotations

from app.fusion_cad.scripts import FusionCadScriptBundle


def _view_script(operation: str, **extra) -> str:
    payload = {"node_id": "desk-1", "operation": operation}
    payload.update(extra)
    return FusionCadScriptBundle().build("view", payload)


# ---------------------------------------------------------------------------
# Finding 2: dimension-aware screenshot via saveAsImageFile
# ---------------------------------------------------------------------------


def test_view_script_screenshot_uses_dimension_aware_save_as_image_file():
    script = _view_script("screenshot", width=640, height=480)
    assert "saveAsImageFile" in script
    assert "saveAsyncImageFile" not in script
    # The unsupported capturePngFile path must be fully gone.
    assert "capturePngFile" not in script
    # Requested dimensions are forwarded to the verified Fusion API and checked.
    assert "save_fn(path, int(width), int(height))" in script
    assert "screenshot width must be a positive integer" in script
    assert "screenshot height must be a positive integer" in script
    assert "saved is not True" in script
    # The returned metadata uses the requested output dimensions, not only the
    # raw active viewport size.
    assert 'context["width"] = int(width)' in script
    assert 'context["height"] = int(height)' in script


# ---------------------------------------------------------------------------
# Finding 6: no unsupported/implausible camera/viewport calls; camera copy model
# ---------------------------------------------------------------------------


def test_view_script_removes_unsupported_legacy_api_calls():
    script = _view_script("camera_read")
    for legacy in (
        "capturePngFile",
        "zoomToFit",
        "setViewType",
        "camera.apply",
        "camera.fov",
    ):
        assert legacy not in script, f"unsupported/implausible call still present: {legacy}"


def test_view_script_assigns_camera_copy_back_and_validates_before_mutation():
    script = _view_script(
        "camera_set",
        eye={"x": 1.0, "y": 2.0, "z": 3.0, "frame": {"space": "world"}},
        target={"x": 0.0, "y": 0.0, "z": 0.0, "frame": {"space": "world"}},
        up={"x": 0.0, "y": 0.0, "z": 1.0, "frame": {"space": "world"}},
        fov=45.0,
    )
    # Official model: mutate the copy, then assign it back.
    assert "viewport.camera = camera" in script
    # Pre-mutation validation for finite/non-degenerate camera values.
    assert "camera_set eye must not equal camera target" in script
    assert "camera_set up vector must be non-zero" in script
    assert "camera_set up vector must not be parallel to the view direction" in script
    assert "camera_set fov must be a finite positive number (degrees)" in script
    # Public fov degrees are converted to radians for perspectiveAngle.
    assert "camera.perspectiveAngle = math.radians(fov_deg)" in script
    # Finite coordinate checks happen before any mutation is applied.
    assert "coordinates must be finite; exact view hashing fails closed" in script
    assert 'frame.get("space") not in (None, "world")' in script


def test_view_script_standard_view_uses_verified_view_orientations_and_gohome():
    script = _view_script("standard_view", view_type="top")
    assert "goHome" in script
    assert "go_home(False)" in script
    assert "ViewOrientations" in script
    assert "kTopViewOrientation" in script
    assert "kIsoLeftTopViewOrientation" in script
    assert "camera.viewOrientation = view_orient" in script
    assert "viewport.camera = camera" in script
    # The unsupported setViewType path must be gone.
    assert "setViewType" not in script
    # The unsupported zoomToFit path must be gone (fit uses Viewport.fit).
    assert "zoomToFit" not in script
    assert "fit_fn()" in script


def test_view_script_zoom_entity_uses_bounding_box_framing_and_fails_closed_for_ortho():
    script = _view_script("zoom_entity", target="ent_1")
    # No invented Viewport.zoomTo API.
    assert "zoomTo(" not in script
    assert "viewport.zoomTo" not in script
    # Verified camera fit/extents/bounding box framing on a copy.
    assert "boundingBox" in script
    assert "radius" in script
    assert "math.sin(half_angle)" in script
    assert "viewport.camera = camera" in script
    # Orthographic exact framing cannot be proven -> fail closed.
    assert "Exact zoom_entity framing is unavailable for orthographic cameras" in script
    assert "CAPABILITY_UNAVAILABLE" in script


def test_view_script_orient_to_face_mutates_copy_then_assigns_back():
    script = _view_script("orient_to_face", target="ent_1")
    assert "camera.apply" not in script
    assert "viewport.camera = camera" in script
    assert "orient_to_face target face normal is degenerate" in script


# ---------------------------------------------------------------------------
# Finding 4: deterministic section capture via SectionAnalysis
# ---------------------------------------------------------------------------


def test_view_script_captures_section_analyses_and_fails_closed_when_missing():
    script = _view_script("camera_read")
    assert 'getattr(design, "analyses", None)' in script
    assert "sectionAnalyses" in script
    assert "isVisible" in script
    assert "transform.asArray" in script
    assert "Design.analyses.sectionAnalyses unavailable" in script
    assert "SectionAnalysis" in script
    # Deterministic identity (entityToken/id/name) is required per section.
    assert "stable identity (entityToken/id/name)" in script
    # A moved section transform changes the captured state.
    assert "transform must be 4x4 (16 values)" in script


# ---------------------------------------------------------------------------
# Finding 5: global object visibility + occurrence-qualified per-object capture
# ---------------------------------------------------------------------------


def test_view_script_captures_object_visibility_global_state_and_fails_closed():
    script = _view_script("camera_read")
    assert "objectVisibility" in script
    assert "isAllObjectsVisible" in script
    assert "Design.objectVisibility (Object Visibility display settings) unavailable" in script
    assert "authoritative global visibility cannot be captured and must fail closed" in script
    # Per-object effective visibility uses stable occurrence-qualified paths and
    # native tokens, not component-name-only keys.
    assert "full_path_name" in script
    assert "native_token" in script
    assert "meshBodies" in script
    assert "constructionPlanes" in script
    assert "constructionAxes" in script
    assert "constructionPoints" in script
# ---------------------------------------------------------------------------
# Task 8 Codex re-review: four verified API/freshness findings
# ---------------------------------------------------------------------------


def test_view_script_orient_to_face_uses_brep_face_surface_evaluator_normal():
    script = _view_script("orient_to_face", target="ent_1")
    assert 'getattr(entity, "evaluator", None)' in script
    assert "getNormalAtPoint" in script
    assert "normal_ok" in script
    assert 'getattr(entity, "normal", None)' not in script


def test_view_script_always_captures_all_boolean_object_visibility_flags():
    script = _view_script("camera_read")
    assert "for name in sorted(dir(ov))" in script
    assert 'name.endswith("Visible")' in script
    # Dynamic discovery must augment the known list, not run only as a fallback
    # when the fixed whitelist happened to produce no flags.
    dynamic = script.index("for name in sorted(dir(ov))")
    fallback = script.rfind("if not flags:", 0, dynamic)
    assert fallback == -1


# ---------------------------------------------------------------------------
# Task 9: single verified screen-space pick strategy
# ---------------------------------------------------------------------------

def test_view_pick_uses_viewport_raycast_only_and_fails_closed_on_stale_view():
    script = _view_script(
        "pick",
        view_ref="view_123",
        x=0.5,
        y=0.5,
        coordinate_space="normalized",
        filters=["face", "edge", "body"],
        _pick_expected={
            "document_ref": "doc_1",
            "model_fingerprint": "abc",
            "camera": {},
            "visibility": {},
            "section": {},
            "image_width": 1920,
            "image_height": 1080,
        },
    )
    assert "viewToModelSpace" in script
    assert "findBRepUsingRay" in script
    assert "BRepEntityTypes" in script
    assert "VIEW_STALE" in script
    assert "activeSelections" not in script
    assert "native-preselect" not in script
    assert "visible_entities_only" in script
    assert "coordinate_space" in script
    assert "normalized pick coordinates must be within [0, 1]" in script


def test_view_pick_handles_orthographic_and_perspective_rays_explicitly():
    script = _view_script(
        "pick",
        view_ref="view_123",
        x=100,
        y=80,
        coordinate_space="pixel",
        filters=["face"],
        _pick_expected={"document_ref": "doc_1", "model_fingerprint": "abc"},
    )
    assert "OrthographicCameraType" in script
    assert "PerspectiveCameraType" in script
    assert "model_point" in script
    assert "camera.eye" in script
    assert "camera.target" in script


def test_view_pick_normalized_endpoint_maps_to_last_valid_viewport_pixel():
    script = _view_script(
        "pick",
        view_ref="view_123",
        x=1.0,
        y=1.0,
        coordinate_space="normalized",
        filters=["face"],
        _pick_expected={"document_ref":"doc_1","model_fingerprint":"abc"},
    )
    assert "max(viewport.width - 1, 1)" in script
    assert "max(viewport.height - 1, 1)" in script
    assert "return x * float(viewport.width), y * float(viewport.height)" not in script


def test_view_pick_distance_is_measured_from_actual_raycast_origin():
    script = _view_script(
        "pick",
        view_ref="view_123",
        x=0.5,
        y=0.5,
        coordinate_space="normalized",
        filters=["face"],
        _pick_expected={"document_ref":"doc_1","model_fingerprint":"abc"},
    )
    assert "float(hit.x)-float(origin.x)" in script
    assert "float(hit.y)-float(origin.y)" in script
    assert "float(hit.z)-float(origin.z)" in script
    assert "float(hit.x)-float(camera.eye.x)" not in script
