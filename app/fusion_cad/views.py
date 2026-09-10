from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.models import (
    CAMERA_REVISION_PATTERN,
    DOCUMENT_REF_PATTERN,
    MODEL_REVISION_PATTERN,
    VIEW_REF_PATTERN,
    VISIBILITY_REVISION_PATTERN,
    ImmutableMapping,
    ViewRefSummary,
)

SECTION_REVISION_PATTERN = r"^sec_[A-Za-z0-9._-]+$"

ProjectionType = Literal["perspective", "orthographic"]

_CAMERA_REQUIRED_FIELDS = ("eye", "target", "up", "projection")
_VIEWPORT_REQUIRED_FIELDS = ("viewport_width", "viewport_height")

_SHA256_HEX_PATTERN = re.compile(r"^[a-f0-9]{16,64}$")


# ---------------------------------------------------------------------------
# Deterministic canonicalization and hashing
# ---------------------------------------------------------------------------


def _json_safe(value: Any) -> Any:
    """Convert immutable mappings/tuples into plain JSON-safe dicts/lists.

    Hashes are always computed over plain JSON; immutable wrappers never leak
    into the deterministic serialization.
    """
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(v) for v in value]
    return value


def _sha256_hex(payload: Any) -> str:
    safe = _json_safe(payload)
    serialized = json.dumps(
        safe,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _round3(value: float) -> float:
    rounded = round(float(value), 6)
    return 0.0 if rounded == 0.0 else rounded


def _as_point_tuple(raw: Any, label: str) -> tuple[float, float, float]:
    """Normalize a 3-vector (list/tuple or {x,y,z}) to a finite rounded tuple."""
    if isinstance(raw, Mapping):
        if not all(k in raw for k in ("x", "y", "z")):
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                f"Camera '{label}' must be a 3-vector (list/tuple of 3 or dict with x/y/z)",
                details={"field": label},
            )
        coords = (raw["x"], raw["y"], raw["z"])
    elif isinstance(raw, (list, tuple)) and len(raw) == 3:
        coords = tuple(raw)
    else:
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            f"Camera '{label}' must be a 3-vector (list/tuple of 3 or dict with x/y/z)",
            details={"field": label},
        )
    out: list[float] = []
    for c in coords:
        try:
            value = float(c)
        except (TypeError, ValueError):
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                f"Camera '{label}' contains a non-numeric coordinate",
                details={"field": label},
            ) from None
        if not math.isfinite(value):
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                f"Camera '{label}' contains a non-finite coordinate; exact view hashing fails closed",
                details={"field": label},
            )
        out.append(_round3(value))
    return tuple(out)  # type: ignore[return-value]


def _as_positive_int(raw: Any, label: str) -> int:
    if isinstance(raw, bool):
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            f"{label} must be a positive integer, got boolean",
            details={"field": label},
        )
    try:
        value = int(raw)
    except (TypeError, ValueError, OverflowError):
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            f"{label} must be a positive integer",
            details={"field": label},
        ) from None
    if value <= 0:
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            f"{label} must be positive, got {value}",
            details={"field": label},
        )
    return value


class CameraContext(BaseModel):
    """Canonical immutable camera context for deterministic view hashing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    eye: tuple[float, float, float]
    target: tuple[float, float, float]
    up: tuple[float, float, float]
    projection: ProjectionType
    fov_deg: float | None = None
    ortho_extent_width_cm: float | None = None
    ortho_extent_height_cm: float | None = None
    viewport_width: int = Field(..., gt=0)
    viewport_height: int = Field(..., gt=0)


def normalize_camera_context(raw: Any) -> CameraContext:
    """Canonicalize a raw Fusion camera result into an immutable CameraContext.

    Missing required data fails closed with INVALID_ARGUMENT rather than
    guessing: exact view freshness can never rely on partial camera state.
    """
    if not isinstance(raw, Mapping):
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Camera context must be a mapping",
            details={"parsed_type": type(raw).__name__},
        )

    for field in _CAMERA_REQUIRED_FIELDS:
        if field not in raw or raw[field] is None:
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                "Camera context is missing a required field for exact view freshness; failing closed",
                details={"field": field},
            )

    projection_raw = raw.get("projection")
    if projection_raw not in ("perspective", "orthographic"):
        # Accept explicit boolean aliases from Fusion runtime probes when a
        # string projection is unavailable; both must not conflict.
        is_persp = raw.get("is_perspective")
        is_ortho = raw.get("is_orthographic")
        if is_ortho is True:
            projection: ProjectionType = "orthographic"
        elif is_persp is True:
            projection = "perspective"
        else:
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                "Camera projection must be 'perspective' or 'orthographic'",
                details={"projection": projection_raw},
            )
    else:
        projection = projection_raw  # type: ignore[assignment]

    viewport_width = _as_positive_int(raw.get("viewport_width"), "viewport_width")
    viewport_height = _as_positive_int(raw.get("viewport_height"), "viewport_height")

    fov_deg: float | None = None
    if raw.get("fov_deg") is not None:
        try:
            fov_value = float(raw["fov_deg"])
        except (TypeError, ValueError):
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                "Camera fov_deg must be a finite positive number",
                details={"field": "fov_deg"},
            ) from None
        if not math.isfinite(fov_value) or fov_value <= 0:
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                "Camera fov_deg must be a finite positive number; exact view hashing fails closed",
                details={"field": "fov_deg"},
            )
        fov_deg = _round3(fov_value)
    elif projection == "perspective":
        # A perspective camera always defines a field of view: without it the
        # view bound is incomplete and must fail closed, never be guessed.
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Perspective camera requires a finite positive fov_deg; failing closed for exact view hashing",
            details={"field": "fov_deg"},
        )

    ortho_extent_width_cm: float | None = None
    ortho_extent_height_cm: float | None = None
    if projection == "orthographic":
        for field in ("ortho_extent_width_cm", "ortho_extent_height_cm"):
            if raw.get(field) is None:
                raise FusionCadError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"Orthographic camera requires {field}; exact view hashing fails closed",
                    details={"field": field},
                )
        try:
            extent_width = float(raw["ortho_extent_width_cm"])
            extent_height = float(raw["ortho_extent_height_cm"])
        except (TypeError, ValueError, OverflowError):
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                "Orthographic camera extents must be finite positive numbers",
            ) from None
        if (
            not math.isfinite(extent_width)
            or not math.isfinite(extent_height)
            or extent_width <= 0
            or extent_height <= 0
        ):
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                "Orthographic camera extents must be finite positive numbers; exact view hashing fails closed",
            )
        ortho_extent_width_cm = _round3(extent_width)
        ortho_extent_height_cm = _round3(extent_height)

    camera = CameraContext(
        eye=_as_point_tuple(raw.get("eye"), "eye"),
        target=_as_point_tuple(raw.get("target"), "target"),
        up=_as_point_tuple(raw.get("up"), "up"),
        projection=projection,
        fov_deg=fov_deg,
        ortho_extent_width_cm=ortho_extent_width_cm,
        ortho_extent_height_cm=ortho_extent_height_cm,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
    )
    # Reject degenerate up vectors (cannot define a deterministic view basis).
    if math.hypot(*camera.up) == 0.0:
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Camera up vector must be non-zero; failing closed for exact view hashing",
            details={"field": "up"},
        )
    return camera


def camera_hash(camera: CameraContext) -> str:
    """Deterministic SHA-256 over the complete canonical camera context."""
    payload: dict[str, Any] = {
        "eye": list(camera.eye),
        "target": list(camera.target),
        "up": list(camera.up),
        "projection": camera.projection,
        "fov_deg": camera.fov_deg,
        "ortho_extent_width_cm": camera.ortho_extent_width_cm,
        "ortho_extent_height_cm": camera.ortho_extent_height_cm,
        "viewport_width": camera.viewport_width,
        "viewport_height": camera.viewport_height,
    }
    return _sha256_hex(payload)


def camera_revision(camera: CameraContext) -> str:
    """Stable deterministic camera revision id (cam_<sha256>)."""
    return f"cam_{camera_hash(camera)}"


def _canonicalize_visibility_entry(item: Any) -> dict[str, Any]:
    """Canonicalize one effective-visibility item deterministically.

    The stable path must be occurrence-qualified (or otherwise collision-proof);
    the native entity token is retained internally so duplicate component names
    in different occurrences can never collide. Public payloads strip native
    tokens via sanitize_public_payload before exposure.
    """
    if not isinstance(item, Mapping):
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Visibility state items must be mappings",
            details={"parsed_type": type(item).__name__},
        )
    path = item.get("full_path_name") or item.get("full_path") or item.get("name")
    if path is None:
        path = item.get("ref")
    if path is None or not isinstance(path, str) or not path.strip():
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Visibility item lacks a stable path (full_path_name/name/ref); failing closed for exact effective visibility hashing",
        )
    local = item.get("is_visible")
    effective = item.get("effective_visibility")
    if local is None and effective is None:
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Visibility item lacks is_visible/effective_visibility; failing closed for exact effective visibility hashing",
        )
    entry: dict[str, Any] = {
        "path": str(path),
        "kind": str(item.get("kind") or "entity"),
        "is_visible": bool(local if local is not None else effective),
        "effective_visibility": bool(effective if effective is not None else local),
    }
    if item.get("ref") is not None and isinstance(item["ref"], str):
        entry["ref"] = item["ref"]
    native_token = item.get("native_token")
    if native_token is not None and isinstance(native_token, str) and native_token.strip():
        entry["native_token"] = native_token
    return entry


def canonicalize_visibility_payload(raw: Any) -> dict[str, Any]:
    """Canonicalize effective-visibility state deterministically.

    Accepts a list of visibility items or a mapping holding an authoritative
    global state ('global': {'object_visibility': {...}}) plus an
    'effective_visibility'/'visibility'/'entries' list. Each item must carry a
    stable occurrence-qualified path (full_path_name/name/ref) and visibility
    fields. Entries are sorted by (path, kind, ref, native_token) so identical
    state hashes identically regardless of collection order. Global object
    visibility flags are hashed into the revision, so a global display-settings
    change invalidates the effective-visibility revision.
    """
    if raw is None:
        raw = {}
    entries_raw: Any = None
    global_flags: dict[str, Any] = {}
    if isinstance(raw, Mapping):
        raw_global = raw.get("global")
        if isinstance(raw_global, Mapping):
            ov = raw_global.get("object_visibility")
            if isinstance(ov, Mapping):
                for k, v in ov.items():
                    if not isinstance(k, str):
                        continue
                    if isinstance(v, bool):
                        global_flags[k] = v
                    elif isinstance(v, (int, float)) and not isinstance(v, bool):
                        global_flags[k] = bool(v)
                    elif isinstance(v, str):
                        global_flags[k] = v
            else:
                raise FusionCadError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Visibility global.object_visibility must be a mapping of display flags",
                    details={"parsed_type": type(ov).__name__},
                )
        for key in ("effective_visibility", "visibility", "entries"):
            if key in raw and raw[key] is not None:
                entries_raw = raw[key]
                break
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        entries_raw = raw

    if entries_raw is None:
        entries_raw = []
    if not isinstance(entries_raw, Sequence) or isinstance(entries_raw, (str, bytes)):
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Visibility state must be a sequence of visibility items",
            details={"parsed_type": type(entries_raw).__name__},
        )

    entries = [_canonicalize_visibility_entry(item) for item in entries_raw]
    entries.sort(key=lambda e: (e["path"], e["kind"], str(e.get("ref", "")), str(e.get("native_token", ""))))
    state: dict[str, Any] = {"entries": entries, "count": len(entries)}
    if global_flags:
        state["global"] = {"object_visibility": dict(sorted(global_flags.items()))}
    return state


def visibility_revision(state: Mapping[str, Any]) -> str:
    """Stable deterministic effective-visibility revision id (vis_<sha256>)."""
    if not isinstance(state, Mapping):
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Visibility state must be a canonicalized mapping",
            details={"parsed_type": type(state).__name__},
        )
    return f"vis_{_sha256_hex(state)}"


def _canonicalize_section_entry(raw: Any) -> dict[str, Any]:
    """Canonicalize one SectionAnalysis item deterministically."""
    if not isinstance(raw, Mapping):
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Section items must be mappings",
            details={"parsed_type": type(raw).__name__},
        )
    ident = raw.get("id") or raw.get("name") or raw.get("entityToken")
    if ident is None or not isinstance(ident, str) or not ident.strip():
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Section item lacks stable identity (id/name/entityToken); failing closed for exact section hashing",
        )
    is_vis = raw.get("is_visible")
    if is_vis is None:
        is_vis = raw.get("effective_visibility")
    if is_vis is None:
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Section item lacks is_visible/effective_visibility; failing closed for exact section hashing",
        )
    entry: dict[str, Any] = {
        "id": str(ident),
        "name": str(raw.get("name") or ""),
        "is_visible": bool(is_vis),
    }
    if raw.get("transform") is None:
        entry["transform"] = None
    elif (
        isinstance(raw.get("transform"), (list, tuple))
        and len(raw["transform"]) == 16
    ):
        entry["transform"] = [_round3(v) for v in raw["transform"]]
    else:
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Section item transform must be a 16-element 4x4 array or null; failing closed for exact section hashing",
        )
    return entry


def canonicalize_section_payload(raw: Any) -> dict[str, Any]:
    """Canonicalize explicit section state deterministically.

    Captures the collection/global visibility plus each visible/registered
    SectionAnalysis's stable identity/name, effective isVisible, and transform,
    so moving a section plane changes the section revision.
    """
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Section state must be a mapping",
            details={"parsed_type": type(raw).__name__},
        )
    sec_type = raw.get("type")
    if sec_type is not None and not isinstance(sec_type, str):
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Section type must be a string or null",
            details={"parsed_type": type(sec_type).__name__},
        )
    sections_raw = raw.get("sections")
    sections: list[dict[str, Any]] = []
    if sections_raw is not None:
        if not isinstance(sections_raw, Sequence) or isinstance(sections_raw, (str, bytes)):
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                "Section state 'sections' must be a sequence of section items",
                details={"parsed_type": type(sections_raw).__name__},
            )
        sections = [_canonicalize_section_entry(item) for item in sections_raw]
    sections.sort(key=lambda s: (s["id"], s["name"]))
    # `active` is derived from the authoritative per-section effective
    # visibility whenever sections are present. A raw "active" marker alone
    # (legacy disabled/default shape) only applies when no sections exist.
    if sections:
        active = any(s["is_visible"] for s in sections)
    else:
        active = bool(raw.get("active", False))
    if not active:
        global_visible = bool(raw.get("global_visible", False))
    else:
        global_visible = bool(raw.get("global_visible", True))
    return {
        "active": active,
        "type": sec_type,
        "global_visible": global_visible,
        "sections": sections,
        "count": len(sections),
    }


def section_revision(state: Mapping[str, Any]) -> str:
    """Stable deterministic section revision id (sec_<sha256>)."""
    if not isinstance(state, Mapping):
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Section state must be a canonicalized mapping",
            details={"parsed_type": type(state).__name__},
        )
    return f"sec_{_sha256_hex(state)}"


# ---------------------------------------------------------------------------
# ViewRefRecord and CurrentViewState
# ---------------------------------------------------------------------------


class ViewRefRecord(BaseModel):
    """Immutable screenshot view context binding image to model/camera/visibility/viewport/section."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    view_ref: str = Field(..., pattern=VIEW_REF_PATTERN)
    document_ref: str = Field(..., pattern=DOCUMENT_REF_PATTERN)
    model_revision: str = Field(..., pattern=MODEL_REVISION_PATTERN)
    camera_revision: str = Field(..., pattern=CAMERA_REVISION_PATTERN)
    camera_hash: str = Field(..., min_length=16)
    visibility_revision: str = Field(..., pattern=VISIBILITY_REVISION_PATTERN)
    visibility_hash: str = Field(..., min_length=16)
    section_revision: str = Field(..., pattern=SECTION_REVISION_PATTERN)
    section_hash: str = Field(..., min_length=16)
    viewport_width: int = Field(..., gt=0)
    viewport_height: int = Field(..., gt=0)
    image: str = Field(..., min_length=1)
    camera: CameraContext
    visibility_state: ImmutableMapping = Field(default_factory=ImmutableMapping)
    section_state: ImmutableMapping = Field(default_factory=ImmutableMapping)

    def to_summary(self) -> ViewRefSummary:
        """Expose the public immutable ViewRef metadata shape (compatible with ViewRefSummary)."""
        return ViewRefSummary(
            view_ref=self.view_ref,
            model_revision=self.model_revision,
            camera_revision=self.camera_revision,
            visibility_revision=self.visibility_revision,
            width=self.viewport_width,
            height=self.viewport_height,
            image=self.image,
        )


class CurrentViewState(BaseModel):
    """Latest observed view state for a node/document (camera, visibility, section)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(..., min_length=1, max_length=64)
    document_ref: str = Field(..., pattern=DOCUMENT_REF_PATTERN)
    camera: CameraContext
    camera_revision: str = Field(..., pattern=CAMERA_REVISION_PATTERN)
    camera_hash: str = Field(..., min_length=16)
    visibility_revision: str = Field(..., pattern=VISIBILITY_REVISION_PATTERN)
    visibility_hash: str = Field(..., min_length=16)
    section_revision: str = Field(..., pattern=SECTION_REVISION_PATTERN)
    section_hash: str = Field(..., min_length=16)
    section_state: ImmutableMapping = Field(default_factory=ImmutableMapping)


class ViewRefStore:
    """Bounded immutable store of screenshot ViewRefs plus per-node current view state.

    assert_fresh independently verifies document identity, model revision,
    camera revision, effective visibility revision, viewport dimensions, and
    section revision. A changed view is never reinterpreted under an old
    screenshot: any bound dimension mismatch returns VIEW_STALE, and a current
    document differing from the bound document returns WRONG_DOCUMENT.
    """

    def __init__(self) -> None:
        self._refs: dict[str, ViewRefRecord] = {}
        self._current: dict[str, CurrentViewState] = {}

    # -- current view state -----------------------------------------------

    def current(self, node_id: str) -> CurrentViewState | None:
        return self._current.get(node_id)

    def observe_camera(
        self,
        node_id: str,
        document_ref: str,
        camera: CameraContext,
        visibility_state: Mapping[str, Any],
        section_state: Mapping[str, Any],
    ) -> CurrentViewState:
        """Record the current canonical camera/visibility/section state for a node.

        Every camera mutation or screenshot updates this current state; old
        ViewRefs bound to a previous context then fail assert_fresh.
        """
        cam_hash = camera_hash(camera)
        vis_hash = _sha256_hex(visibility_state)
        sec_hash = _sha256_hex(section_state)
        state = CurrentViewState(
            node_id=node_id,
            document_ref=document_ref,
            camera=camera,
            camera_revision=camera_revision(camera),
            camera_hash=cam_hash,
            visibility_revision=visibility_revision(dict(visibility_state)),
            visibility_hash=vis_hash,
            section_revision=section_revision(dict(section_state)),
            section_hash=sec_hash,
            section_state=ImmutableMapping(dict(section_state)),
        )
        self._current[node_id] = state
        return state

    # -- binding -----------------------------------------------------------

    def bind(
        self,
        *,
        view_ref: str,
        document_ref: str,
        model_revision: str,
        camera: CameraContext,
        visibility_state: Mapping[str, Any],
        section_state: Mapping[str, Any],
        image: str,
        width: int | None = None,
        height: int | None = None,
    ) -> ViewRefRecord:
        """Bind an immutable ViewRef. A view_ref can never be bound twice."""
        if not isinstance(view_ref, str) or not re.match(VIEW_REF_PATTERN, view_ref):
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                "view_ref must match the view_* opaque reference pattern",
                details={"view_ref": view_ref},
            )
        if view_ref in self._refs:
            raise FusionCadError(
                ErrorCode.PRECONDITION_FAILED,
                "view_ref is already bound; ViewRef is immutable and cannot be overwritten",
                details={"view_ref": view_ref},
            )
        if not isinstance(camera, CameraContext):
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                "Camera context must be a canonical CameraContext",
                details={"parsed_type": type(camera).__name__},
            )
        width = camera.viewport_width if width is None else _as_positive_int(width, "width")
        height = camera.viewport_height if height is None else _as_positive_int(height, "height")
        vis_state = dict(visibility_state)
        sec_state = dict(section_state)
        cam_hash = camera_hash(camera)
        vis_hash = _sha256_hex(vis_state)
        sec_hash = _sha256_hex(sec_state)
        record = ViewRefRecord(
            view_ref=view_ref,
            document_ref=document_ref,
            model_revision=model_revision,
            camera_revision=camera_revision(camera),
            camera_hash=cam_hash,
            visibility_revision=visibility_revision(vis_state),
            visibility_hash=vis_hash,
            section_revision=section_revision(sec_state),
            section_hash=sec_hash,
            viewport_width=width,
            viewport_height=height,
            image=image,
            camera=camera,
            visibility_state=ImmutableMapping(vis_state),
            section_state=ImmutableMapping(sec_state),
        )
        self._refs[view_ref] = record
        return record

    def get(self, view_ref: str) -> ViewRefRecord | None:
        return self._refs.get(view_ref)

    def set_image(self, view_ref: str, image: str) -> ViewRefRecord:
        """Promote a bound ViewRef's image binding to the proven external image URI.

        Each record remains immutable; the store atomically replaces the internal
        placeholder with a new immutable record carrying the real emitted image
        ResourceLink URI. The fabricated resource://views/... placeholder can
        never escape to any public surface.
        """
        record = self._refs.get(view_ref)
        if record is None:
            raise FusionCadError(
                ErrorCode.REF_STALE,
                "View reference is not bound; cannot bind an image URI",
                details={"view_ref": view_ref},
            )
        if not isinstance(image, str) or not image.strip():
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                "image URI must be a non-empty string",
                details={"view_ref": view_ref},
            )
        promoted = record.model_copy(update={"image": image})
        self._refs[view_ref] = promoted
        return promoted

    # -- freshness ----------------------------------------------------------

    def assert_fresh(
        self,
        view_ref: str,
        current_context: Any | None = None,
        **kwargs: Any,
    ) -> ViewRefRecord:
        """Assert the immutable view still matches the current view context.

        Each of document identity, model revision, camera revision, effective
        visibility revision, viewport dimensions, and section revision is
        verified independently; any mismatch (or any missing required current
        datum) fails closed. A different current document returns WRONG_DOCUMENT.
        Never reinterprets an old screenshot under a changed view.
        """
        record = self._refs.get(view_ref)
        if record is None:
            raise FusionCadError(
                ErrorCode.VIEW_STALE,
                "View reference is unknown or no longer bound; the screenshot context cannot be verified",
                details={"view_ref": view_ref},
            )

        ctx: dict[str, Any] = {}
        if current_context is not None:
            if isinstance(current_context, Mapping):
                ctx.update(dict(current_context))
            elif isinstance(current_context, BaseModel):
                for key in (
                    "document_ref",
                    "model_revision",
                    "camera_revision",
                    "visibility_revision",
                    "section_revision",
                    "viewport_width",
                    "viewport_height",
                    "camera",
                    "visibility",
                    "section",
                ):
                    value = getattr(current_context, key, None)
                    if value is not None:
                        ctx[key] = value
            else:
                raise FusionCadError(
                    ErrorCode.INVALID_ARGUMENT,
                    "current_context must be a mapping or view state model",
                    details={"parsed_type": type(current_context).__name__},
                )
        for key, value in kwargs.items():
            if value is not None:
                ctx[key] = value

        current_document_ref = ctx.get("document_ref")
        if current_document_ref is None:
            raise FusionCadError(
                ErrorCode.VIEW_STALE,
                "Screenshot context cannot verify document identity (missing current document_ref)",
                details={"view_ref": view_ref},
            )
        if str(current_document_ref) != record.document_ref:
            raise FusionCadError(
                ErrorCode.WRONG_DOCUMENT,
                "Screenshot view belongs to a different document than the current active/current document",
                details={
                    "view_ref": view_ref,
                    "expected_document": record.document_ref,
                    "current_document": str(current_document_ref),
                },
            )

        current_model_revision = ctx.get("model_revision")
        if current_model_revision is None:
            raise FusionCadError(
                ErrorCode.VIEW_STALE,
                "Screenshot context cannot verify model revision (missing current model revision)",
                details={"view_ref": view_ref},
            )
        if str(current_model_revision) != record.model_revision:
            raise FusionCadError(
                ErrorCode.VIEW_STALE,
                "Screenshot view is stale: model revision changed",
                details={
                    "view_ref": view_ref,
                    "expected_revision": record.model_revision,
                    "current_revision": str(current_model_revision),
                },
            )

        current_camera_revision = self._resolve_camera_revision(ctx)
        if current_camera_revision is None:
            raise FusionCadError(
                ErrorCode.VIEW_STALE,
                "Screenshot context cannot verify camera state (missing current camera context)",
                details={"view_ref": view_ref},
            )
        if current_camera_revision != record.camera_revision:
            raise FusionCadError(
                ErrorCode.VIEW_STALE,
                "Screenshot view is stale: camera state changed",
                details={"view_ref": view_ref},
            )

        current_visibility_revision = self._resolve_visibility_revision(ctx)
        if current_visibility_revision is None:
            raise FusionCadError(
                ErrorCode.VIEW_STALE,
                "Screenshot context cannot verify effective visibility (missing current visibility state)",
                details={"view_ref": view_ref},
            )
        if current_visibility_revision != record.visibility_revision:
            raise FusionCadError(
                ErrorCode.VIEW_STALE,
                "Screenshot view is stale: effective visibility changed",
                details={"view_ref": view_ref},
            )

        current_width = ctx.get("viewport_width")
        current_height = ctx.get("viewport_height")
        if current_width is None or current_height is None:
            raise FusionCadError(
                ErrorCode.VIEW_STALE,
                "Screenshot context cannot verify viewport dimensions (missing viewport width/height)",
                details={"view_ref": view_ref},
            )
        # The freshness dimension check compares the LIVE viewport captured with
        # the camera (record.camera.viewport_width/height). The record's own
        # viewport_width/height are the screenshot OUTPUT resolution reported in
        # public metadata and may legitimately differ from the live viewport.
        if int(current_width) != record.camera.viewport_width:
            raise FusionCadError(
                ErrorCode.VIEW_STALE,
                "Screenshot view is stale: viewport width changed",
                details={"view_ref": view_ref},
            )
        if int(current_height) != record.camera.viewport_height:
            raise FusionCadError(
                ErrorCode.VIEW_STALE,
                "Screenshot view is stale: viewport height changed",
                details={"view_ref": view_ref},
            )

        current_section_revision = self._resolve_section_revision(ctx)
        if current_section_revision is None:
            raise FusionCadError(
                ErrorCode.VIEW_STALE,
                "Screenshot context cannot verify section state (missing current section state)",
                details={"view_ref": view_ref},
            )
        if current_section_revision != record.section_revision:
            raise FusionCadError(
                ErrorCode.VIEW_STALE,
                "Screenshot view is stale: section state changed",
                details={"view_ref": view_ref},
            )

        return record

    @staticmethod
    def _resolve_camera_revision(ctx: Mapping[str, Any]) -> str | None:
        explicit = ctx.get("camera_revision")
        if explicit is not None:
            return str(explicit)
        raw_camera = ctx.get("camera")
        if raw_camera is None:
            return None
        if isinstance(raw_camera, CameraContext):
            return camera_revision(raw_camera)
        if isinstance(raw_camera, dict):
            if "camera_revision" in raw_camera:
                return str(raw_camera["camera_revision"])
            try:
                return camera_revision(normalize_camera_context(raw_camera))
            except FusionCadError:
                return None
        return None

    @staticmethod
    def _resolve_visibility_revision(ctx: Mapping[str, Any]) -> str | None:
        explicit = ctx.get("visibility_revision")
        if explicit is not None:
            return str(explicit)
        raw_visibility = ctx.get("visibility")
        if raw_visibility is None:
            return None
        try:
            return visibility_revision(
                canonicalize_visibility_payload(raw_visibility)
            )
        except (FusionCadError, ValueError, TypeError):
            return None

    @staticmethod
    def _resolve_section_revision(ctx: Mapping[str, Any]) -> str | None:
        explicit = ctx.get("section_revision")
        if explicit is not None:
            return str(explicit)
        raw_section = ctx.get("section")
        if raw_section is None:
            return None
        try:
            return section_revision(canonicalize_section_payload(raw_section))
        except (FusionCadError, ValueError, TypeError):
            return None