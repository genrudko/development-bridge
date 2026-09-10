from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError, sanitize_public_payload
from app.fusion_cad.models import (
    ENTITY_REF_PATTERN,
    BoundingBox,
    CoordinateFrame,
    ImmutableMapping,
    Point3,
    Vector3,
)
from app.fusion_cad.refs import EntityRefRegistry

LENGTH_UNIT = "mm"
ANGLE_UNIT = "deg"
AREA_UNIT = "mm^2"
VOLUME_UNIT = "mm^3"

_UNIT_BY_QUANTITY: dict[str, str] = {
    "area": AREA_UNIT,
    "perimeter": LENGTH_UNIT,
    "volume": VOLUME_UNIT,
    "distance": LENGTH_UNIT,
    "minimum_distance": LENGTH_UNIT,
    "angle": ANGLE_UNIT,
    "thickness": LENGTH_UNIT,
}

# Exact expected public quantity for every scalar-measure operation. A requested
# operation must never accept a mismatched quantity (e.g. area reporting a
# volume). face_to_face_thickness exposes quantity 'thickness'.
_EXPECTED_QUANTITY: dict[str, str] = {
    "area": "area",
    "perimeter": "perimeter",
    "volume": "volume",
    "distance": "distance",
    "minimum_distance": "minimum_distance",
    "angle": "angle",
    "face_to_face_thickness": "thickness",
}

# Exact measured-deviation key contract per relation operation.
_RELATION_MEASURED_KEYS: dict[str, frozenset[str]] = {
    "parallel": frozenset({"angle_deg"}),
    "perpendicular": frozenset({"angle_deg"}),
    "coplanar": frozenset({"angle_deg", "distance_mm"}),
    "concentric": frozenset({"angle_deg", "offset_mm"}),
}

_RELATION_TOLERANCE_UNIT: dict[str, str] = {
    "parallel": ANGLE_UNIT,
    "perpendicular": ANGLE_UNIT,
    "coplanar": LENGTH_UNIT,
    "concentric": LENGTH_UNIT,
}


class MeasureResult(BaseModel):
    """Normalized scalar measure with exact quantity and unit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    quantity: str = Field(..., min_length=1)
    value: float
    unit: str = Field(..., min_length=1)


class BoundingBoxResult(BaseModel):
    """Normalized axis-aligned bounding box with explicit frame."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bounding_box: BoundingBox


class OrientedBoundingBox(BaseModel):
    """Normalized oriented bounding box (center, orthonormal axes, half-extents, frame)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    center: Point3
    axes: tuple[Vector3, Vector3, Vector3]
    extents: tuple[float, float, float]
    frame: CoordinateFrame


class CentroidResult(BaseModel):
    """Normalized centroid point with explicit frame."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    point: Point3


class DistanceResult(BaseModel):
    """Normalized distance measure between two explicit points with frames."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    quantity: str
    value: float
    unit: str
    from_point: Point3
    to_point: Point3


class AngleResult(BaseModel):
    """Normalized angle measure in degrees."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    quantity: str
    value: float
    unit: str


class ToleranceSpec(BaseModel):
    """Explicit relation tolerance value and unit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: float = Field(..., ge=0)
    unit: str = Field(..., min_length=1)


class RelationResult(BaseModel):
    """Normalized geometric relation result with matches, measured deviation, and explicit tolerance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    relation: str
    matches: bool
    measured: ImmutableMapping
    tolerance: ToleranceSpec
    tolerances: ImmutableMapping | None = None
    target_a: str
    target_b: str


class ThicknessResult(BaseModel):
    """Normalized face-to-face thickness only when two-face geometry is unambiguous."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    quantity: str
    value: float
    unit: str
    face_a: str
    face_b: str
    unambiguous: bool


class DescribeResult(BaseModel):
    """Normalized describe record with supported exact measures."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str
    kind: str = Field(..., min_length=1)
    name: str | None = None
    native_type: str | None = None
    frame: CoordinateFrame
    measures: ImmutableMapping = Field(default_factory=ImmutableMapping)


def _coerce_frame(raw: Any, default_space: str | None = None) -> CoordinateFrame:
    """Build an explicit CoordinateFrame from raw data, never guessing a frame.

    A raw frame must carry an explicit non-empty 'space'. When a default_space is
    provided (used only for dimensionless direction vectors inside an enclosing
    frame), a missing raw frame may inherit that space; otherwise a missing frame
    fails closed with UNSUPPORTED_GEOMETRY. 'world' is never silently synthesized.
    """
    if isinstance(raw, CoordinateFrame):
        return raw
    if isinstance(raw, Mapping):
        space = raw.get("space")
        if not isinstance(space, str) or not space.strip():
            raise FusionCadError(
                ErrorCode.UNSUPPORTED_GEOMETRY,
                "Inspection result carries an invalid or missing coordinate frame space",
            )
        try:
            return CoordinateFrame(space=space, ref=raw.get("ref"))
        except (ValueError, TypeError):
            raise FusionCadError(
                ErrorCode.UNSUPPORTED_GEOMETRY,
                "Inspection result contains an invalid coordinate frame",
            ) from None
    if default_space is not None:
        return CoordinateFrame(space=default_space, ref=None)
    raise FusionCadError(
        ErrorCode.UNSUPPORTED_GEOMETRY,
        "Inspection result is missing an explicit coordinate frame",
    )


def _coerce_point(raw: Any) -> Point3:
    """Build an explicit Point3 carrying an explicit frame; a missing/invalid
    frame fails closed (world is never synthesized)."""
    if isinstance(raw, Point3):
        return raw
    if not isinstance(raw, Mapping):
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            "Inspection result missing exact point geometry",
        )
    try:
        return Point3(
            x=float(raw["x"]),
            y=float(raw["y"]),
            z=float(raw["z"]),
            frame=_coerce_frame(raw.get("frame")),
        )
    except (KeyError, TypeError, ValueError):
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            "Inspection result missing exact point coordinates",
        ) from None


def _coerce_vector(raw: Any, frame: CoordinateFrame | None = None) -> Vector3:
    """Build an explicit Vector3 carrying an explicit frame.

    Direction vectors inherit their frame from the enclosing geometry; they must
    never define a frame-free vector, so an enclosing frame is required.
    """
    if isinstance(raw, Vector3):
        return raw
    if frame is None:
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            "Inspection result vector is missing an enclosing coordinate frame",
        )
    if isinstance(raw, (list, tuple)) and len(raw) == 3:
        try:
            return Vector3(
                x=float(raw[0]),
                y=float(raw[1]),
                z=float(raw[2]),
                frame=frame,
            )
        except (TypeError, ValueError):
            raise FusionCadError(
                ErrorCode.UNSUPPORTED_GEOMETRY,
                "Inspection result missing exact vector coordinates",
            ) from None
    if isinstance(raw, Mapping):
        try:
            return Vector3(
                x=float(raw["x"]),
                y=float(raw["y"]),
                z=float(raw["z"]),
                frame=_coerce_frame(raw.get("frame"), frame.space),
            )
        except (KeyError, TypeError, ValueError):
            raise FusionCadError(
                ErrorCode.UNSUPPORTED_GEOMETRY,
                "Inspection result missing exact vector coordinates",
            ) from None
    raise FusionCadError(
        ErrorCode.UNSUPPORTED_GEOMETRY,
        "Inspection result missing exact vector geometry",
    )


def _require_ref(value: Any, field: str) -> str:
    s = str(value or "")
    if not re.match(ENTITY_REF_PATTERN, s):
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            f"Inspection result missing valid entity ref for '{field}'",
        )
    return s


def normalize_measure(
    raw: Mapping[str, Any], *, operation: str
) -> MeasureResult:
    """Normalize an exact scalar measure, failing closed on missing/guessed values.

    The quantity must exactly match the operation's public contract and every
    numeric measurement must be finite.
    """
    value = raw.get("value")
    if value is None or not isinstance(value, (int, float)) or isinstance(value, bool):
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            f"Inspection '{operation}' result missing exact measured value",
        )
    value_float = float(value)
    if not math.isfinite(value_float):
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            f"Inspection '{operation}' result measured value must be finite",
        )
    quantity = raw.get("quantity")
    expected_quantity = _EXPECTED_QUANTITY.get(operation)
    if expected_quantity is not None:
        if not isinstance(quantity, str) or quantity != expected_quantity:
            raise FusionCadError(
                ErrorCode.UNSUPPORTED_GEOMETRY,
                f"Inspection '{operation}' result quantity '{quantity}' does not match expected '{expected_quantity}'",
            )
    else:
        quantity = str(quantity or operation or "")
        if not quantity:
            raise FusionCadError(
                ErrorCode.UNSUPPORTED_GEOMETRY,
                f"Inspection '{operation}' result missing exact quantity",
            )
    unit = raw.get("unit")
    if not isinstance(unit, str) or not unit.strip():
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            f"Inspection '{operation}' result missing exact unit",
        )
    expected_unit = _UNIT_BY_QUANTITY.get(quantity)
    if expected_unit is not None and unit != expected_unit:
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            f"Inspection '{operation}' result unit '{unit}' does not match expected '{expected_unit}'",
        )
    return MeasureResult(quantity=quantity, value=value_float, unit=unit)


def normalize_bounding_box(raw: Mapping[str, Any]) -> BoundingBoxResult:
    """Normalize an axis-aligned bounding box with an explicit frame (missing frame fails closed)."""
    bb_raw = raw.get("bounding_box") or raw.get("bbox")
    if not isinstance(bb_raw, Mapping):
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            "Inspection bounding_box result missing exact bounding box",
        )
    try:
        min_raw = bb_raw.get("min") or bb_raw.get("min_point")
        max_raw = bb_raw.get("max") or bb_raw.get("max_point")
        if (
            not isinstance(min_raw, (list, tuple))
            or len(min_raw) != 3
            or not isinstance(max_raw, (list, tuple))
            or len(max_raw) != 3
        ):
            raise TypeError("missing min/max")
        frame = _coerce_frame(bb_raw.get("frame"))
        bb = BoundingBox(
            min_point=Point3(
                x=float(min_raw[0]),
                y=float(min_raw[1]),
                z=float(min_raw[2]),
                frame=frame,
            ),
            max_point=Point3(
                x=float(max_raw[0]),
                y=float(max_raw[1]),
                z=float(max_raw[2]),
                frame=frame,
            ),
            frame=frame,
        )
    except FusionCadError:
        raise
    except (TypeError, ValueError):
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            "Inspection bounding_box result missing exact min/max points",
        ) from None
    return BoundingBoxResult(bounding_box=bb)


def normalize_oriented_bbox(raw: Mapping[str, Any]) -> OrientedBoundingBox:
    """Normalize an oriented bounding box with center, axes, extents, and an
    explicit frame (missing center/obb frames fail closed)."""
    obb_raw = raw.get("oriented_bbox") or raw.get("obb")
    if not isinstance(obb_raw, Mapping):
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            "Inspection oriented_bbox result missing exact oriented bounding box",
        )
    try:
        center_raw = obb_raw.get("center")
        if not isinstance(center_raw, Mapping):
            raise TypeError("missing center")
        center = _coerce_point(center_raw)
        axes_raw = obb_raw.get("axes")
        if not isinstance(axes_raw, (list, tuple)) or len(axes_raw) != 3:
            raise TypeError("missing axes")
        axes = tuple(_coerce_vector(a, center.frame) for a in axes_raw)
        extents_raw = obb_raw.get("extents")
        if not isinstance(extents_raw, (list, tuple)) or len(extents_raw) != 3:
            raise TypeError("missing extents")
        extents = tuple(float(e) for e in extents_raw)
        if not all(math.isfinite(e) for e in extents):
            raise TypeError("non-finite extents")
        frame = _coerce_frame(obb_raw.get("frame"))
    except FusionCadError:
        raise
    except (TypeError, ValueError):
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            "Inspection oriented_bbox result missing exact center/axes/extents",
        ) from None
    return OrientedBoundingBox(
        center=center, axes=axes, extents=extents, frame=frame
    )


def normalize_centroid(raw: Mapping[str, Any]) -> CentroidResult:
    """Normalize a centroid point with an explicit frame (missing frame fails closed)."""
    point_raw = raw.get("point") or raw.get("centroid")
    if not isinstance(point_raw, Mapping):
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            "Inspection centroid result missing exact point",
        )
    return CentroidResult(point=_coerce_point(point_raw))


def normalize_distance(
    raw: Mapping[str, Any], *, operation: str
) -> DistanceResult:
    """Normalize a distance measure with explicit from/to points and frames."""
    measure = normalize_measure(raw, operation=operation)
    from_raw = raw.get("from") or raw.get("from_point")
    to_raw = raw.get("to") or raw.get("to_point")
    if not isinstance(from_raw, Mapping) or not isinstance(to_raw, Mapping):
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            f"Inspection '{operation}' result missing exact from/to points",
        )
    return DistanceResult(
        quantity=measure.quantity,
        value=measure.value,
        unit=measure.unit,
        from_point=_coerce_point(from_raw),
        to_point=_coerce_point(to_raw),
    )


def normalize_angle(raw: Mapping[str, Any]) -> AngleResult:
    """Normalize an angle measure in degrees."""
    measure = normalize_measure(raw, operation="angle")
    return AngleResult(
        quantity=measure.quantity, value=measure.value, unit=measure.unit
    )


def normalize_relation(
    raw: Mapping[str, Any], *, operation: str
) -> RelationResult:
    """Normalize a relation result with matches, measured deviation, and explicit tolerance.

    The relation name must equal the requested operation, the measured-deviation
    keys and tolerance unit must match the operation's public contract, and every
    numeric measurement/tolerance must be finite.
    """
    relation = str(raw.get("relation") or operation or "")
    if not relation:
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            f"Inspection '{operation}' relation result missing exact relation name",
        )
    if relation != operation:
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            f"Inspection '{operation}' relation result relation '{relation}' does not match requested operation",
        )
    matches_raw = raw.get("matches")
    if not isinstance(matches_raw, bool):
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            f"Inspection '{operation}' relation result missing exact matches boolean",
        )
    measured_raw = raw.get("measured")
    if not isinstance(measured_raw, Mapping) or not measured_raw:
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            f"Inspection '{operation}' relation result missing measured deviation",
        )
    expected_keys = _RELATION_MEASURED_KEYS.get(operation)
    if expected_keys is not None and set(measured_raw.keys()) != expected_keys:
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            f"Inspection '{operation}' relation result measured keys must be {sorted(expected_keys)}",
        )
    for key, val in measured_raw.items():
        if (
            val is None
            or isinstance(val, bool)
            or not isinstance(val, (int, float))
            or not math.isfinite(float(val))
        ):
            raise FusionCadError(
                ErrorCode.UNSUPPORTED_GEOMETRY,
                f"Inspection '{operation}' relation result measured '{key}' must be a finite number",
            )
    tol_raw = raw.get("tolerance")
    if not isinstance(tol_raw, Mapping):
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            f"Inspection '{operation}' relation result missing explicit tolerance",
        )
    tol_value = tol_raw.get("value")
    tol_unit = tol_raw.get("unit")
    if (
        tol_value is None
        or not isinstance(tol_value, (int, float))
        or isinstance(tol_value, bool)
    ):
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            f"Inspection '{operation}' relation result missing explicit tolerance value",
        )
    if not isinstance(tol_unit, str) or not tol_unit.strip():
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            f"Inspection '{operation}' relation result missing explicit tolerance unit",
        )
    tol_float = float(tol_value)
    if not math.isfinite(tol_float):
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            f"Inspection '{operation}' relation result tolerance must be finite",
        )
    if tol_float < 0:
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            f"Inspection '{operation}' relation result has negative tolerance",
        )
    expected_tol_unit = _RELATION_TOLERANCE_UNIT.get(operation)
    if expected_tol_unit is not None and tol_unit != expected_tol_unit:
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            f"Inspection '{operation}' relation result tolerance unit '{tol_unit}' does not match expected '{expected_tol_unit}'",
        )
    tolerances: ImmutableMapping | None = None
    tolerances_raw = raw.get("tolerances")
    if tolerances_raw is not None:
        if not isinstance(tolerances_raw, Mapping) or not tolerances_raw:
            raise FusionCadError(
                ErrorCode.UNSUPPORTED_GEOMETRY,
                f"Inspection '{operation}' relation result tolerances must be a non-empty mapping",
            )
        tol_map: dict[str, Any] = {}
        for tol_key, tol_val in tolerances_raw.items():
            if (
                tol_val is None
                or not isinstance(tol_val, (int, float))
                or isinstance(tol_val, bool)
            ):
                raise FusionCadError(
                    ErrorCode.UNSUPPORTED_GEOMETRY,
                    f"Inspection '{operation}' relation result tolerance '{tol_key}' must be a non-negative number",
                )
            tol_val_float = float(tol_val)
            if not math.isfinite(tol_val_float):
                raise FusionCadError(
                    ErrorCode.UNSUPPORTED_GEOMETRY,
                    f"Inspection '{operation}' relation result tolerance '{tol_key}' must be finite",
                )
            if tol_val_float < 0:
                raise FusionCadError(
                    ErrorCode.UNSUPPORTED_GEOMETRY,
                    f"Inspection '{operation}' relation result tolerance '{tol_key}' is negative",
                )
            tol_map[str(tol_key)] = tol_val_float
        tolerances = ImmutableMapping(tol_map)
    return RelationResult(
        relation=relation,
        matches=matches_raw,
        measured=ImmutableMapping(dict(measured_raw)),
        tolerance=ToleranceSpec(value=tol_float, unit=str(tol_unit)),
        tolerances=tolerances,
        target_a=_require_ref(raw.get("target_a"), "target_a"),
        target_b=_require_ref(raw.get("target_b"), "target_b"),
    )


def normalize_thickness(raw: Mapping[str, Any]) -> ThicknessResult:
    """Normalize exact face-to-face thickness; never a whole-body min-wall heuristic."""
    if raw.get("unambiguous") is not True:
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            "Face-to-face thickness requires unambiguous two-face geometry; no whole-body min-wall heuristic",
        )
    measure = normalize_measure(raw, operation="face_to_face_thickness")
    return ThicknessResult(
        quantity=measure.quantity,
        value=measure.value,
        unit=measure.unit,
        face_a=_require_ref(raw.get("face_a"), "face_a"),
        face_b=_require_ref(raw.get("face_b"), "face_b"),
        unambiguous=True,
    )


def normalize_describe(raw: Mapping[str, Any]) -> DescribeResult:
    """Normalize a describe record with supported exact measures.

    Every measure must be an explicit structured mapping carrying
    quantity+unit/value (or an explicit bounding-box structure with an explicit
    frame). Bare numeric measures and missing quantity/unit/frame fail closed with
    UNSUPPORTED_GEOMETRY -- units/frames are never inferred.
    """
    target = raw.get("target")
    if not isinstance(target, Mapping):
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            "Inspection describe result missing exact target record",
        )
    ref = _require_ref(target.get("ref") or raw.get("ref"), "ref")
    kind = target.get("kind") or raw.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            "Inspection describe result missing exact entity kind",
        )
    frame = _coerce_frame(raw.get("frame"))
    measures_raw = raw.get("measures")
    measures: dict[str, Any] = {}
    if isinstance(measures_raw, Mapping):
        for key, val in measures_raw.items():
            key_str = str(key)
            if isinstance(val, Mapping) and (
                "min" in val or "min_point" in val
            ):
                bb = normalize_bounding_box({"bounding_box": val})
                measures[key_str] = bb.model_dump(mode="python")
            elif isinstance(val, Mapping):
                measures[key_str] = normalize_measure(
                    val, operation=key_str
                ).model_dump(mode="python")
            else:
                raise FusionCadError(
                    ErrorCode.UNSUPPORTED_GEOMETRY,
                    f"Inspection describe measure '{key_str}' must be an explicit structured mapping with quantity+unit/value or an explicit bounding box with an explicit frame; bare numeric measures are rejected",
                )
    return DescribeResult(
        ref=ref,
        kind=kind,
        name=target.get("name") if isinstance(target.get("name"), str) else None,
        native_type=(
            target.get("native_type")
            if isinstance(target.get("native_type"), str)
            else None
        ),
        frame=frame,
        measures=ImmutableMapping(measures),
    )


def normalize_inspect_result(
    raw: Mapping[str, Any],
    *,
    operation: str,
    ref_registry: EntityRefRegistry | None = None,
    document_ref: str = "doc_active",
) -> ImmutableMapping:
    """Dispatch normalization of a raw Fusion inspection result by operation.

    Unsupported target types surface as TYPE_MISMATCH or UNSUPPORTED_GEOMETRY;
    values are never guessed or heuristically derived.
    """
    if not isinstance(raw, Mapping):
        raise FusionCadError(
            ErrorCode.UNSUPPORTED_GEOMETRY,
            "Inspection result must be a mapping",
        )

    unsupported = raw.get("unsupported")
    if unsupported in ("TYPE_MISMATCH", "UNSUPPORTED_GEOMETRY"):
        raise FusionCadError(
            ErrorCode(str(unsupported)),
            f"Inspection '{operation}' target type is unsupported",
        )

    if operation == "describe":
        result: BaseModel = normalize_describe(raw)
    elif operation == "bounding_box":
        result = normalize_bounding_box(raw)
    elif operation == "oriented_bbox":
        obb_result = normalize_oriented_bbox(raw)
        dumped = obb_result.model_dump(mode="python", exclude_none=True)
        dumped["operation"] = operation
        return ImmutableMapping(
            sanitize_public_payload({"oriented_bbox": dumped})
        )
    elif operation == "centroid":
        result = normalize_centroid(raw)
    elif operation in ("area", "perimeter", "volume"):
        result = normalize_measure(raw, operation=operation)
    elif operation in ("distance", "minimum_distance"):
        result = normalize_distance(raw, operation=operation)
    elif operation == "angle":
        result = normalize_angle(raw)
    elif operation in ("parallel", "perpendicular", "coplanar", "concentric"):
        result = normalize_relation(raw, operation=operation)
    elif operation == "face_to_face_thickness":
        result = normalize_thickness(raw)
    else:
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            f"Unknown inspection operation '{operation}'",
        )

    dumped = result.model_dump(mode="python", exclude_none=True)
    dumped["operation"] = operation
    return ImmutableMapping(sanitize_public_payload(dumped))