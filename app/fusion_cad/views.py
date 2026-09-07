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

    camera = CameraContext(
        eye=_as_point_tuple(raw.get("eye"), "eye"),
        target=_as_point_tuple(raw.get("target"), "target"),
        up=_as_point_tuple(raw.get("up"), "up"),
        projection=projection,
        fov_deg=fov_deg,
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
        "viewport_width": camera.viewport_width,
        "viewport_height": camera.viewport_height,
    }
    return _sha256_hex(payload)


def camera_revision(camera: CameraContext) -> str:
    """Stable deterministic camera revision id (cam_<sha256>)."""
    return f"cam_{camera_hash(camera)}"


def canonicalize_visibility_payload(raw: Any) -> dict[str, Any]:
    """Canonicalize effective-visibility state deterministically.

    Accepts a list of visibility items or a mapping holding an
    'effective_visibility'/'visibility'/'entries' list. Each item must carry a
    stable path (full_path_name/name/ref) and visibility fields. Entries are
    sorted by (path, kind) so identical state hashes identically regardless of
    collection order. Items without a stable path fail closed.
    """
    if raw is None:
        raw = []
    if isinstance(raw, Mapping):
        for key in ("effective_visibility", "visibility", "entries"):
            if key in raw and raw[key] is not None:
                raw = raw[key]
                break
        else:
            raw = []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Visibility state must be a sequence of visibility items",
            details={"parsed_type": type(raw).__name__},
        )

    entries: list[dict[str, Any]] = []
    for item in raw:
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
        entries.append(entry)

    entries.sort(key=lambda e: (e["path"], e["kind"], str(e.get("ref", ""))))
    return {"entries": entries, "count": len(entries)}


def visibility_revision(state: Mapping[str, Any]) -> str:
    """Stable deterministic effective-visibility revision id (vis_<sha256>)."""
    if not isinstance(state, Mapping):
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Visibility state must be a canonicalized mapping",
            details={"parsed_type": type(state).__name__},
        )
    return f"vis_{_sha256_hex(state)}"


def canonicalize_section_payload(raw: Any) -> dict[str, Any]:
    """Canonicalize explicit section state.

    P0 supports only explicit disabled/default section state; an active section
    state cannot be hashed exactly with P0 introspection and fails closed.
    """
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Section state must be a mapping",
            details={"parsed_type": type(raw).__name__},
        )
    active = bool(raw.get("active", False))
    if active:
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "P0 section state must be explicit disabled/default; active section state is not supported and cannot be hashed exactly",
            details={"active": True},
        )
    sec_type = raw.get("type")
    if sec_type is not None and not isinstance(sec_type, str):
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            "Section type must be a string or null",
            details={"parsed_type": type(sec_type).__name__},
        )
    return {"active": False, "type": sec_type}


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

    assert_fresh independently verifies model revision, camera revision,
    effective visibility revision, viewport dimensions, and section revision.
    A changed view is never reinterpreted under an old screenshot: any bound
    dimension mismatch returns VIEW_STALE.
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

    # -- freshness ----------------------------------------------------------

    def assert_fresh(
        self,
        view_ref: str,
        current_context: Any | None = None,
        **kwargs: Any,
    ) -> ViewRefRecord:
        """Assert the immutable view still matches the current view context.

        Each of model revision, camera revision, effective visibility revision,
        viewport dimensions, and section revision is verified independently; any
        mismatch (or any missing required current datum) raises VIEW_STALE.
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
        if int(current_width) != record.viewport_width:
            raise FusionCadError(
                ErrorCode.VIEW_STALE,
                "Screenshot view is stale: viewport width changed",
                details={"view_ref": view_ref},
            )
        if int(current_height) != record.viewport_height:
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