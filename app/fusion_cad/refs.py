from __future__ import annotations

import math
import uuid
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.models import (
    DOCUMENT_REF_PATTERN,
    ENTITY_REF_PATTERN,
    BoundingBox,
    CoordinateFrame,
    EntityRef,
    ImmutableMapping,
    Plane,
    Point3,
    Ray,
    StabilityClass,
    Transform,
    Vector3,
)

ResolutionOutcome = Literal["exact", "split", "stale", "wrong_document", "ambiguous"]


class InternalEntityRecord(BaseModel):
    """Internal CAD entity record storing native token and resolver hints."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str = Field(..., pattern=ENTITY_REF_PATTERN)
    native_token: str | None = None
    kind: str = Field(..., min_length=1)
    document_ref: str = Field(..., pattern=DOCUMENT_REF_PATTERN)
    stability: StabilityClass = "persistent"
    native_type: str | None = None
    name: str | None = None
    component_path: tuple[str, ...] = Field(default_factory=tuple)
    geometry_signature: ImmutableMapping | None = None

    def to_public_ref(self) -> EntityRef:
        """Expose only public opaque EntityRef without internal native token or geometry signature."""
        return EntityRef(
            ref=self.ref,
            kind=self.kind,
            document_ref=self.document_ref,
            stability=self.stability,
            native_type=self.native_type,
            name=self.name,
            component_path=self.component_path,
        )


class ResolutionResult(BaseModel):
    """Authoritative result of resolving an EntityRef."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str
    outcome: ResolutionOutcome
    candidates: tuple[Any, ...] = Field(default_factory=tuple)
    record: InternalEntityRecord | None = None
    message: str | None = None


class EntityRefRegistry:
    """Document-bounded registry managing opaque EntityRef lifecycles and resolution."""

    def __init__(
        self,
        *,
        max_documents: int = 16,
        max_entries_per_doc: int = 10_000,
    ) -> None:
        self._max_documents = max_documents
        self._max_entries_per_doc = max_entries_per_doc
        self._doc_refs: OrderedDict[str, OrderedDict[str, InternalEntityRecord]] = (
            OrderedDict()
        )
        self._token_to_ref: dict[tuple[str, str], str] = {}

    def has_document(self, document_ref: str) -> bool:
        return document_ref in self._doc_refs

    def get_internal_record(
        self,
        ref: str,
        document_ref: str | None = None,
    ) -> InternalEntityRecord | None:
        if document_ref is not None:
            doc_map = self._doc_refs.get(document_ref)
            if doc_map is not None:
                return doc_map.get(ref)
            return None
        for doc_map in self._doc_refs.values():
            if ref in doc_map:
                return doc_map[ref]
        return None

    def issue(
        self,
        *,
        document_ref: str,
        kind: str,
        native_token: str | None = None,
        stability: StabilityClass = "persistent",
        native_type: str | None = None,
        name: str | None = None,
        component_path: Sequence[str] = (),
        geometry_signature: Mapping[str, Any] | None = None,
        opaque_ref: str | None = None,
    ) -> EntityRef:
        """Issue an opaque EntityRef, never exposing the native token as public identity."""
        # Ensure document mapping exists and touch LRU order
        if document_ref in self._doc_refs:
            self._doc_refs.move_to_end(document_ref)
        else:
            if len(self._doc_refs) >= self._max_documents:
                oldest_doc, oldest_map = self._doc_refs.popitem(last=False)
                for rec in oldest_map.values():
                    if rec.native_token is not None:
                        self._token_to_ref.pop((oldest_doc, rec.native_token), None)
            self._doc_refs[document_ref] = OrderedDict()

        doc_map = self._doc_refs[document_ref]

        # Idempotency / deduplication: reuse existing opaque ref for same token in document
        if native_token is not None:
            token_key = (document_ref, native_token)
            if token_key in self._token_to_ref:
                existing_ref = self._token_to_ref[token_key]
                if existing_ref in doc_map:
                    return doc_map[existing_ref].to_public_ref()

        # Generate opaque ref matching ENTITY_REF_PATTERN
        if opaque_ref is not None:
            ref_str = opaque_ref
        else:
            ref_str = f"ent_{uuid.uuid4().hex[:16]}"

        # Invariant: public ref is NEVER the native token
        if native_token is not None and ref_str == native_token:
            ref_str = f"ent_{uuid.uuid4().hex[:16]}"

        # Check per-document bounded entry capacity
        if len(doc_map) >= self._max_entries_per_doc:
            _oldest_ref, oldest_record = doc_map.popitem(last=False)
            if oldest_record.native_token is not None:
                self._token_to_ref.pop((document_ref, oldest_record.native_token), None)

        record = InternalEntityRecord(
            ref=ref_str,
            native_token=native_token,
            kind=kind,
            document_ref=document_ref,
            stability=stability,
            native_type=native_type,
            name=name,
            component_path=tuple(component_path),
            geometry_signature=ImmutableMapping(geometry_signature)
            if geometry_signature
            else None,
        )

        doc_map[ref_str] = record
        if native_token is not None:
            self._token_to_ref[(document_ref, native_token)] = ref_str

        return record.to_public_ref()

    def resolve(
        self,
        ref: str | EntityRef,
        active_document_ref: str,
        *,
        native_resolver: Callable[
            [InternalEntityRecord], tuple[ResolutionOutcome, Sequence[Any]]
        ]
        | None = None,
    ) -> ResolutionResult:
        """Resolve a public EntityRef against the active document.

        Wrong document check fails before attempting native lookup.
        Topology split returns all candidates.
        Ambiguous resolution never silently picks the first candidate.
        """
        ref_str = ref.ref if isinstance(ref, EntityRef) else str(ref)

        # 1. Check if EntityRef explicitly declares another document
        if isinstance(ref, EntityRef) and ref.document_ref != active_document_ref:
            return ResolutionResult(
                ref=ref_str,
                outcome="wrong_document",
                candidates=(),
                message=f"EntityRef belongs to document '{ref.document_ref}', active document is '{active_document_ref}'",
            )

        # 2. Check if ref is registered in a different document in registry
        for doc_id, doc_map in self._doc_refs.items():
            if ref_str in doc_map and doc_id != active_document_ref:
                return ResolutionResult(
                    ref=ref_str,
                    outcome="wrong_document",
                    candidates=(),
                    record=doc_map[ref_str],
                    message=f"Reference belongs to document '{doc_id}', active document is '{active_document_ref}'",
                )

        # 3. Check active document map
        active_map = self._doc_refs.get(active_document_ref)
        if active_map is None or ref_str not in active_map:
            return ResolutionResult(
                ref=ref_str,
                outcome="stale",
                candidates=(),
                message=f"Reference '{ref_str}' not found in active document '{active_document_ref}'",
            )

        record = active_map[ref_str]

        # 4. Native resolver lookup
        if native_resolver is not None:
            outcome, candidates = native_resolver(record)
            return ResolutionResult(
                ref=ref_str,
                outcome=outcome,
                candidates=tuple(candidates),
                record=record,
            )

        return ResolutionResult(
            ref=ref_str,
            outcome="exact",
            candidates=(record,),
            record=record,
        )

    def resolve_one(
        self,
        ref: str | EntityRef,
        active_document_ref: str,
        *,
        native_resolver: Callable[
            [InternalEntityRecord], tuple[ResolutionOutcome, Sequence[Any]]
        ]
        | None = None,
    ) -> Any:
        """Resolve single entity strictly; fails closed on wrong_document, stale, split, or ambiguous."""
        res = self.resolve(ref, active_document_ref, native_resolver=native_resolver)

        if res.outcome == "exact":
            if not res.candidates:
                raise FusionCadError(
                    ErrorCode.REF_STALE,
                    f"EntityRef '{res.ref}' resolved to exact outcome but returned no candidate",
                    details={
                        "ref": res.ref,
                        "active_document_ref": active_document_ref,
                    },
                )
            return res.candidates[0]

        if res.outcome == "wrong_document":
            raise FusionCadError(
                ErrorCode.WRONG_DOCUMENT,
                f"EntityRef '{res.ref}' belongs to another document (active: '{active_document_ref}')",
                details={
                    "ref": res.ref,
                    "active_document_ref": active_document_ref,
                    "outcome": "wrong_document",
                },
            )

        if res.outcome == "stale":
            raise FusionCadError(
                ErrorCode.REF_STALE,
                f"EntityRef '{res.ref}' is stale and cannot be resolved in active document '{active_document_ref}'",
                details={
                    "ref": res.ref,
                    "active_document_ref": active_document_ref,
                    "outcome": "stale",
                },
            )

        if res.outcome == "split":
            raise FusionCadError(
                ErrorCode.REF_SPLIT,
                f"EntityRef '{res.ref}' resolved to multiple split candidates ({len(res.candidates)})",
                details={
                    "ref": res.ref,
                    "active_document_ref": active_document_ref,
                    "outcome": "split",
                    "candidate_count": len(res.candidates),
                    "candidates": [getattr(c, "ref", str(c)) for c in res.candidates],
                },
            )

        if res.outcome == "ambiguous":
            raise FusionCadError(
                ErrorCode.REF_AMBIGUOUS,
                f"EntityRef '{res.ref}' contextual resolution is ambiguous with {len(res.candidates)} candidates",
                details={
                    "ref": res.ref,
                    "active_document_ref": active_document_ref,
                    "outcome": "ambiguous",
                    "candidate_count": len(res.candidates),
                    "candidates": [getattr(c, "ref", str(c)) for c in res.candidates],
                },
            )

        raise FusionCadError(
            ErrorCode.REF_STALE,
            f"EntityRef '{res.ref}' resolution failed with outcome: {res.outcome}",
            details={
                "ref": res.ref,
                "active_document_ref": active_document_ref,
                "outcome": res.outcome,
            },
        )


# ==============================================================================
# CoordinateFrame Conversions
# ==============================================================================

Matrix4x4 = tuple[tuple[float, ...], ...]

_IDENTITY_4X4: Matrix4x4 = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)


def _check_occurrence_frame_safety(
    source_frame: CoordinateFrame,
    target_frame: CoordinateFrame,
    transform_matrix: Matrix4x4 | None,
) -> None:
    """Do not claim occurrence transform support from mere API presence.

    Occurrence transform requires explicit verified transform matrix;
    without it, conversion must fail closed as degraded/unavailable.
    """
    if (
        source_frame.space == "occurrence" or target_frame.space == "occurrence"
    ) and transform_matrix is None:
        raise FusionCadError(
            ErrorCode.CAPABILITY_DEGRADED,
            "Occurrence coordinate frame conversion requires verified occurrence transform capability; "
            "API presence alone does not guarantee contract support without runtime verification",
            details={
                "source_frame": source_frame.model_dump(),
                "target_frame": target_frame.model_dump(),
            },
        )


def _apply_affine_point(pt: Point3, m: Matrix4x4) -> tuple[float, float, float]:
    x, y, z = pt.x, pt.y, pt.z
    new_x = m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3]
    new_y = m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3]
    new_z = m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3]
    return round(new_x, 8), round(new_y, 8), round(new_z, 8)


def _apply_affine_vector(vec: Vector3, m: Matrix4x4) -> tuple[float, float, float]:
    x, y, z = vec.x, vec.y, vec.z
    new_x = m[0][0] * x + m[0][1] * y + m[0][2] * z
    new_y = m[1][0] * x + m[1][1] * y + m[1][2] * z
    new_z = m[2][0] * x + m[2][1] * y + m[2][2] * z
    return round(new_x, 8), round(new_y, 8), round(new_z, 8)


def convert_point(
    point: Point3,
    target_frame: CoordinateFrame,
    *,
    transform_matrix: Matrix4x4 | None = None,
) -> Point3:
    """Convert Point3 to target CoordinateFrame carrying explicit target frame."""
    if point.frame == target_frame:
        return point

    _check_occurrence_frame_safety(point.frame, target_frame, transform_matrix)
    m = transform_matrix or _IDENTITY_4X4
    nx, ny, nz = _apply_affine_point(point, m)
    return Point3(x=nx, y=ny, z=nz, frame=target_frame)


def convert_vector(
    vector: Vector3,
    target_frame: CoordinateFrame,
    *,
    transform_matrix: Matrix4x4 | None = None,
) -> Vector3:
    """Convert Vector3 to target CoordinateFrame carrying explicit target frame."""
    if vector.frame == target_frame:
        return vector

    _check_occurrence_frame_safety(vector.frame, target_frame, transform_matrix)
    m = transform_matrix or _IDENTITY_4X4
    nx, ny, nz = _apply_affine_vector(vector, m)
    return Vector3(x=nx, y=ny, z=nz, frame=target_frame)


def convert_bounding_box(
    bbox: BoundingBox,
    target_frame: CoordinateFrame,
    *,
    transform_matrix: Matrix4x4 | None = None,
) -> BoundingBox:
    """Convert BoundingBox to target CoordinateFrame, transforming all 8 corners."""
    if bbox.frame == target_frame:
        return bbox

    _check_occurrence_frame_safety(bbox.frame, target_frame, transform_matrix)
    m = transform_matrix or _IDENTITY_4X4

    xs = (bbox.min_point.x, bbox.max_point.x)
    ys = (bbox.min_point.y, bbox.max_point.y)
    zs = (bbox.min_point.z, bbox.max_point.z)

    transformed_corners = []
    for x in xs:
        for y in ys:
            for z in zs:
                pt = Point3(x=x, y=y, z=z, frame=bbox.frame)
                transformed_corners.append(_apply_affine_point(pt, m))

    min_x = min(c[0] for c in transformed_corners)
    max_x = max(c[0] for c in transformed_corners)
    min_y = min(c[1] for c in transformed_corners)
    max_y = max(c[1] for c in transformed_corners)
    min_z = min(c[2] for c in transformed_corners)
    max_z = max(c[2] for c in transformed_corners)

    min_pt = Point3(x=min_x, y=min_y, z=min_z, frame=target_frame)
    max_pt = Point3(x=max_x, y=max_y, z=max_z, frame=target_frame)
    return BoundingBox(min_point=min_pt, max_point=max_pt, frame=target_frame)


def convert_plane(
    plane: Plane,
    target_frame: CoordinateFrame,
    *,
    transform_matrix: Matrix4x4 | None = None,
) -> Plane:
    """Convert Plane to target CoordinateFrame with transformed origin and normal."""
    if plane.frame == target_frame:
        return plane

    _check_occurrence_frame_safety(plane.frame, target_frame, transform_matrix)
    new_origin = convert_point(
        plane.origin, target_frame, transform_matrix=transform_matrix
    )
    new_normal = convert_vector(
        plane.normal, target_frame, transform_matrix=transform_matrix
    )

    # Normalize normal vector
    length = math.sqrt(new_normal.x**2 + new_normal.y**2 + new_normal.z**2)
    if length > 0:
        new_normal = Vector3(
            x=round(new_normal.x / length, 8),
            y=round(new_normal.y / length, 8),
            z=round(new_normal.z / length, 8),
            frame=target_frame,
        )

    return Plane(origin=new_origin, normal=new_normal, frame=target_frame)


def convert_ray(
    ray: Ray,
    target_frame: CoordinateFrame,
    *,
    transform_matrix: Matrix4x4 | None = None,
) -> Ray:
    """Convert Ray to target CoordinateFrame with transformed origin and direction."""
    if ray.frame == target_frame:
        return ray

    _check_occurrence_frame_safety(ray.frame, target_frame, transform_matrix)
    new_origin = convert_point(
        ray.origin, target_frame, transform_matrix=transform_matrix
    )
    new_direction = convert_vector(
        ray.direction, target_frame, transform_matrix=transform_matrix
    )

    length = math.sqrt(new_direction.x**2 + new_direction.y**2 + new_direction.z**2)
    if length > 0:
        new_direction = Vector3(
            x=round(new_direction.x / length, 8),
            y=round(new_direction.y / length, 8),
            z=round(new_direction.z / length, 8),
            frame=target_frame,
        )

    return Ray(origin=new_origin, direction=new_direction, frame=target_frame)


def convert_transform(
    transform: Transform,
    target_frame: CoordinateFrame,
    *,
    transform_matrix: Matrix4x4 | None = None,
) -> Transform:
    """Convert Transform matrix to target CoordinateFrame carrying explicit target frame."""
    if transform.frame == target_frame:
        return transform

    _check_occurrence_frame_safety(transform.frame, target_frame, transform_matrix)
    # Target frame is explicitly stamped on the resulting Transform
    return Transform(matrix=transform.matrix, frame=target_frame)
