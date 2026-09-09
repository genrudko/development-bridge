from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.fusion_cad.models import (
    DOCUMENT_REF_PATTERN,
    ENTITY_REF_PATTERN,
    MODEL_REVISION_PATTERN,
    SNAPSHOT_ID_PATTERN,
    BoundingBox,
    CoordinateFrame,
    ImmutableMapping,
    Point3,
)
from app.fusion_cad.refs import EntityRefRegistry

DependencyType = Literal["exact", "inferred", "unknown"]

from app.fusion_cad.errors import sanitize_public_payload

VOLATILE_HASH_KEYS = frozenset({"snapshot_id", "snapshotid"})
IDENTIFIER_REF_KEYS = frozenset(
    {
        "ref",
        "target",
        "target_ref",
        "targetref",
        "owner_ref",
        "ownerref",
        "owner_id",
        "ownerid",
        "entity_ref",
        "entityref",
        "reporter",
        "parent",
        "children",
        "outputs",
        "occurrence",
        "component",
    }
)


def _canonicalize_structural_value(
    val: Any, ref_map: Mapping[str, str], is_identifier: bool = False
) -> Any:
    """Recursively canonicalize semantic model payload for structural hashing.

    Removes/replaces volatile lifecycle identities (snapshot_id and opaque lifecycle refs
    as identifiers) while retaining mutation-sensitive values and without collapsing real
    semantic differences.
    """
    if val is None or isinstance(val, (bool, int)):
        return val
    if isinstance(val, float):
        rounded = round(val, 6)
        return 0.0 if rounded == 0.0 else rounded
    if isinstance(val, str):
        if is_identifier:
            if val in ref_map:
                return ref_map[val]
            if val.startswith("ent_") and re.match(ENTITY_REF_PATTERN, val):
                return ""
        return val
    if isinstance(val, Mapping):
        clean_map: dict[str, Any] = {}
        unknown_ref_entries: list[Any] = []
        for k, v in val.items():
            k_str = str(k)
            # 1. Volatile snapshot_id keys are removed entirely
            if k_str in VOLATILE_HASH_KEYS or k_str.lower() in VOLATILE_HASH_KEYS:
                continue

            # 2. Key is an entity ref in a ref-keyed mapping
            if k_str in ref_map:
                target_key = ref_map[k_str]
                canon_val = _canonicalize_structural_value(
                    v, ref_map, is_identifier=False
                )
                if target_key in clean_map:
                    col_idx = 1
                    while f"{target_key}#collision:{col_idx}" in clean_map:
                        col_idx += 1
                    clean_map[f"{target_key}#collision:{col_idx}"] = canon_val
                else:
                    clean_map[target_key] = canon_val
            elif k_str.startswith("ent_") and re.match(ENTITY_REF_PATTERN, k_str):
                unknown_ref_entries.append(
                    _canonicalize_structural_value(v, ref_map, is_identifier=False)
                )
            else:
                # 3. Field key: check if field is an identifier ref field
                is_field_id = (
                    k_str in IDENTIFIER_REF_KEYS or k_str.lower() in IDENTIFIER_REF_KEYS
                )
                clean_map[k_str] = _canonicalize_structural_value(
                    v, ref_map, is_identifier=is_field_id
                )

        if unknown_ref_entries:
            try:
                sorted_entries = sorted(
                    unknown_ref_entries,
                    key=lambda item: (
                        json.dumps(
                            item,
                            sort_keys=True,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        if isinstance(item, (dict, list, tuple))
                        else str(item)
                    ),
                )
            except (TypeError, ValueError):
                sorted_entries = unknown_ref_entries

            for idx, item in enumerate(sorted_entries):
                clean_map[f"ent_ref:{idx}"] = item

        return {k: clean_map[k] for k in sorted(clean_map.keys())}

    if isinstance(val, (set, frozenset)):
        canonical_items = [
            _canonicalize_structural_value(x, ref_map, is_identifier=is_identifier)
            for x in val
        ]
        try:
            return sorted(
                canonical_items,
                key=lambda item: (
                    json.dumps(
                        item,
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    if isinstance(item, (dict, list, tuple))
                    else str(item)
                ),
            )
        except (TypeError, ValueError):
            return canonical_items
    if isinstance(val, (list, tuple)):
        items = [
            _canonicalize_structural_value(x, ref_map, is_identifier=is_identifier)
            for x in val
        ]
        return tuple(items) if isinstance(val, tuple) else items
    return str(val)


def _safe_ent_ref(ref_candidate: Any, fallback_prefix: str = "ent") -> str:
    """Ensure a string conforms to ENTITY_REF_PATTERN, prefixing or sanitizing if needed."""
    if not ref_candidate:
        return f"{fallback_prefix}_{uuid.uuid4().hex[:10]}"
    s = str(ref_candidate)
    if re.match(ENTITY_REF_PATTERN, s):
        return s
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", s)
    if not sanitized.startswith("ent_"):
        return f"ent_{fallback_prefix}_{sanitized}"
    return sanitized


def _safe_doc_ref(doc_candidate: Any) -> str:
    """Ensure a string conforms to DOCUMENT_REF_PATTERN, prefixing or sanitizing if needed."""
    if not doc_candidate:
        return f"doc_{uuid.uuid4().hex[:10]}"
    s = str(doc_candidate)
    if re.match(DOCUMENT_REF_PATTERN, s):
        return s
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", s)
    if not sanitized.startswith("doc_"):
        return f"doc_{sanitized}"
    return sanitized


class SnapshotCounts(BaseModel):
    """Counts of entities and topological elements in the model snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    components: int = 0
    occurrences: int = 0
    bodies: int = 0
    sketches: int = 0
    features: int = 0
    parameters: int = 0
    faces: int = 0
    edges: int = 0
    vertices: int = 0


class ComponentSummary(BaseModel):
    """Summary of a CAD component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str = Field(..., pattern=ENTITY_REF_PATTERN)
    name: str = Field(..., min_length=1)
    kind: str = "component"
    component_path: tuple[str, ...] = Field(default_factory=tuple)
    id: str | None = None


class OccurrenceSummary(BaseModel):
    """Summary of a component occurrence in the assembly hierarchy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str = Field(..., pattern=ENTITY_REF_PATTERN)
    name: str = Field(..., min_length=1)
    kind: str = "occurrence"
    full_path_name: str = Field(..., min_length=1)
    component_path: tuple[str, ...] = Field(default_factory=tuple)
    is_visible: bool = True
    effective_visibility: bool = True
    transform: tuple[float, ...] | tuple[tuple[float, ...], ...] | None = None


class BodySummary(BaseModel):
    """Summary of a B-Rep or solid body."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str = Field(..., pattern=ENTITY_REF_PATTERN)
    name: str = Field(..., min_length=1)
    kind: str = "body"
    component_name: str | None = None
    component_path: tuple[str, ...] = Field(default_factory=tuple)
    is_solid: bool = True
    volume: float | None = None
    area: float | None = None
    bounding_box: BoundingBox | None = None
    faces_count: int = 0
    edges_count: int = 0
    is_visible: bool = True
    effective_visibility: bool = True


class SketchSummary(BaseModel):
    """Summary of a 2D/3D sketch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str = Field(..., pattern=ENTITY_REF_PATTERN)
    name: str = Field(..., min_length=1)
    kind: str = "sketch"
    component_name: str | None = None
    component_path: tuple[str, ...] = Field(default_factory=tuple)
    profiles_count: int = 0
    constraints_count: int = 0
    dimensions_count: int = 0
    fully_constrained: bool | None = None


class FeatureDependency(BaseModel):
    """Feature input dependency with strict fidelity: never upgrade inferred to exact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str = Field(..., pattern=ENTITY_REF_PATTERN)
    kind: str | None = None
    dependency_type: DependencyType = "unknown"

    @model_validator(mode="after")
    def validate_dependency_type(self) -> FeatureDependency:
        # Invariant: Never upgrade inferred to exact
        if self.dependency_type not in ("exact", "inferred", "unknown"):
            raise ValueError(f"Invalid dependency_type: '{self.dependency_type}'")
        return self


class FeatureRecord(BaseModel):
    """Record of a feature in the design timeline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str = Field(..., pattern=ENTITY_REF_PATTERN)
    timeline_index: int = Field(..., ge=0)
    name: str = Field(..., min_length=1)
    feature_type: str = Field(..., min_length=1)
    kind: str = "feature"
    is_suppressed: bool = False
    health_status: str = "ok"
    diagnostic_message: str | None = None
    component_path: tuple[str, ...] = Field(default_factory=tuple)
    dependencies: tuple[FeatureDependency, ...] = Field(default_factory=tuple)
    inputs: tuple[FeatureDependency, ...] = Field(default_factory=tuple)
    outputs: tuple[str, ...] = Field(default_factory=tuple)
    parent: str | None = None
    children: tuple[str, ...] = Field(default_factory=tuple)


class ParameterSummary(BaseModel):
    """Summary of a model or user parameter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str | None = Field(default=None, pattern=ENTITY_REF_PATTERN)
    name: str = Field(..., min_length=1)
    kind: str = "parameter"
    value: float
    expression: str | None = None
    unit: str | None = "mm"
    is_user: bool = False
    component_path: tuple[str, ...] = Field(default_factory=tuple)


class SketchReadResult(BaseModel):
    """Detailed result of reading a sketch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str = Field(..., pattern=ENTITY_REF_PATTERN)
    name: str = Field(..., min_length=1)
    plane: ImmutableMapping | None = None
    geometry: ImmutableMapping = Field(default_factory=ImmutableMapping)
    dimensions: tuple[ImmutableMapping, ...] = Field(default_factory=tuple)
    constraints: tuple[ImmutableMapping, ...] = Field(default_factory=tuple)
    profiles: tuple[ImmutableMapping, ...] = Field(default_factory=tuple)
    fully_constrained: bool | None = None
    linked_projection_state: tuple[ImmutableMapping, ...] = Field(default_factory=tuple)
    texts: tuple[ImmutableMapping, ...] = Field(default_factory=tuple)
    health: ImmutableMapping = Field(default_factory=ImmutableMapping)
    dof: None = None  # Do not invent unsupported DOF counts!


class ModelSnapshot(BaseModel):
    """Authoritative semantic model snapshot with structural hashing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: str = Field(..., pattern=SNAPSHOT_ID_PATTERN)
    document_ref: str = Field(..., pattern=DOCUMENT_REF_PATTERN)
    model_revision: str = Field(..., pattern=MODEL_REVISION_PATTERN)
    structural_hash: str = Field(..., min_length=1)
    fingerprint: str | None = None
    counts: SnapshotCounts
    components: tuple[ComponentSummary, ...] = Field(default_factory=tuple)
    occurrences: tuple[OccurrenceSummary, ...] = Field(default_factory=tuple)
    bodies: tuple[BodySummary, ...] = Field(default_factory=tuple)
    sketches: tuple[SketchSummary, ...] = Field(default_factory=tuple)
    features: tuple[FeatureRecord, ...] = Field(default_factory=tuple)
    parameters: tuple[ParameterSummary, ...] = Field(default_factory=tuple)
    visibility: ImmutableMapping = Field(default_factory=ImmutableMapping)
    appearance: ImmutableMapping = Field(default_factory=ImmutableMapping)
    health: ImmutableMapping = Field(default_factory=ImmutableMapping)
    logical_objects: tuple[ImmutableMapping, ...] = Field(default_factory=tuple)
    bounding_box: BoundingBox | None = None
    faces: tuple[ImmutableMapping, ...] | None = None
    edges: tuple[ImmutableMapping, ...] | None = None
    units: str = "mm"
    detail: Literal["compact", "full"] = "compact"


def _populate_semantic_ref_map(
    items: Sequence[Any],
    key_func: Any,
    ref_map: dict[str, str],
    prefix: str,
    omit_keys: Sequence[str] = ("ref", "id", "faces", "edges"),
) -> None:
    groups: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for item in items:
        ref = getattr(item, "ref", None) or (
            item.get("ref") if isinstance(item, Mapping) else None
        )
        if not ref:
            continue
        sem_key = str(key_func(item))
        data = (
            item.model_dump(mode="python")
            if isinstance(item, BaseModel)
            else dict(item)
        )
        for ok in omit_keys:
            data.pop(ok, None)
        groups.setdefault(sem_key, []).append((str(ref), data))

    for sem_key, group in groups.items():
        if len(group) == 1:
            ref_map[group[0][0]] = f"{prefix}:{sem_key}"
        else:
            sorted_dups = sorted(
                group,
                key=lambda x: json.dumps(
                    x[1],
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=str,
                ),
            )
            for idx, (ref, _) in enumerate(sorted_dups):
                ref_map[ref] = f"{prefix}:{sem_key}:{idx}"


def compute_structural_hash(snapshot_dict: Mapping[str, Any]) -> str:
    """Compute deterministic SHA-256 structural hash of a semantic snapshot."""
    # Build canonical payload omitting volatile identifiers (snapshot_id, UUID refs, runtime IDs)
    canonical_body: dict[str, Any] = {}

    # 1. Document & revision
    canonical_body["document_ref"] = snapshot_dict.get("document_ref")
    canonical_body["model_revision"] = snapshot_dict.get("model_revision")
    canonical_body["units"] = snapshot_dict.get("units", "mm")

    # 2. Counts
    counts = snapshot_dict.get("counts")
    if isinstance(counts, BaseModel):
        counts = counts.model_dump(mode="python")

    comps = snapshot_dict.get("components", ())
    occs = snapshot_dict.get("occurrences", ())
    bodies = snapshot_dict.get("bodies", ())
    sketches = snapshot_dict.get("sketches", ())
    features = snapshot_dict.get("features", ())
    params = snapshot_dict.get("parameters", ())

    # Build semantic identifier map for volatile UUID-backed refs
    ref_map: dict[str, str] = {}
    _populate_semantic_ref_map(
        comps,
        lambda c: (
            getattr(c, "name", None)
            or (c.get("name") if isinstance(c, Mapping) else "")
        ),
        ref_map,
        "comp",
        omit_keys=("ref", "id"),
    )
    _populate_semantic_ref_map(
        occs,
        lambda o: (
            getattr(o, "full_path_name", None)
            or (o.get("full_path_name") if isinstance(o, Mapping) else "")
        ),
        ref_map,
        "occ",
        omit_keys=("ref", "id"),
    )
    _populate_semantic_ref_map(
        bodies,
        lambda b: (
            f"{getattr(b, 'component_name', None) or (b.get('component_name') if isinstance(b, Mapping) else '')}:{getattr(b, 'name', None) or (b.get('name') if isinstance(b, Mapping) else '')}"
        ),
        ref_map,
        "body",
        omit_keys=("ref", "id", "faces", "edges"),
    )
    _populate_semantic_ref_map(
        sketches,
        lambda s: (
            f"{getattr(s, 'component_name', None) or (s.get('component_name') if isinstance(s, Mapping) else '')}:{getattr(s, 'name', None) or (s.get('name') if isinstance(s, Mapping) else '')}"
        ),
        ref_map,
        "sketch",
        omit_keys=("ref", "id"),
    )
    _populate_semantic_ref_map(
        features,
        lambda f: (
            f"{getattr(f, 'timeline_index', None) or (f.get('timeline_index') if isinstance(f, Mapping) else 0)}:{getattr(f, 'name', None) or (f.get('name') if isinstance(f, Mapping) else '')}"
        ),
        ref_map,
        "feat",
        omit_keys=("ref", "id"),
    )
    _populate_semantic_ref_map(
        params,
        lambda p: (
            getattr(p, "name", None)
            or (p.get("name") if isinstance(p, Mapping) else "")
        ),
        ref_map,
        "param",
        omit_keys=("ref", "id"),
    )

    faces = snapshot_dict.get("faces") or ()
    if isinstance(faces, (list, tuple)):
        for idx, face in enumerate(faces):
            f_ref = getattr(face, "ref", None) or (
                face.get("ref") if isinstance(face, Mapping) else None
            )
            f_id = getattr(face, "id", None) or (
                face.get("id") if isinstance(face, Mapping) else None
            )
            if f_ref:
                ref_map[str(f_ref)] = f"face:{f_id or idx}"

    edges = snapshot_dict.get("edges") or ()
    if isinstance(edges, (list, tuple)):
        for idx, edge in enumerate(edges):
            e_ref = getattr(edge, "ref", None) or (
                edge.get("ref") if isinstance(edge, Mapping) else None
            )
            e_id = getattr(edge, "id", None) or (
                edge.get("id") if isinstance(edge, Mapping) else None
            )
            if e_ref:
                ref_map[str(e_ref)] = f"edge:{e_id or idx}"

    canonical_body["counts"] = _canonicalize_structural_value(counts, ref_map)

    # 3. Components (sorted by name)
    comp_list = []
    for c in comps:
        cd = c.model_dump(mode="python") if isinstance(c, BaseModel) else dict(c)
        cd.pop("ref", None)
        cd.pop("id", None)
        comp_list.append(cd)
    comp_list.sort(
        key=lambda x: (
            x.get("name", ""),
            json.dumps(
                x,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            ),
        )
    )
    canonical_body["components"] = _canonicalize_structural_value(comp_list, ref_map)

    # 4. Occurrences (sorted by full_path_name)
    occ_list = []
    for o in occs:
        od = o.model_dump(mode="python") if isinstance(o, BaseModel) else dict(o)
        od.pop("ref", None)
        od.pop("id", None)
        occ_list.append(od)
    occ_list.sort(
        key=lambda x: (
            x.get("full_path_name", ""),
            json.dumps(
                x,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            ),
        )
    )
    canonical_body["occurrences"] = _canonicalize_structural_value(occ_list, ref_map)

    # 5. Bodies (sorted by component_name, name)
    body_list = []
    for b in bodies:
        bd = b.model_dump(mode="python") if isinstance(b, BaseModel) else dict(b)
        bd.pop("ref", None)
        bd.pop("id", None)
        bd.pop("faces", None)
        bd.pop("edges", None)
        body_list.append(bd)
    body_list.sort(
        key=lambda x: (
            x.get("component_name") or "",
            x.get("name", ""),
            json.dumps(
                x,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            ),
        )
    )
    canonical_body["bodies"] = _canonicalize_structural_value(body_list, ref_map)

    # 6. Sketches (sorted by component_name, name)
    sk_list = []
    for s in sketches:
        sd = s.model_dump(mode="python") if isinstance(s, BaseModel) else dict(s)
        sd.pop("ref", None)
        sd.pop("id", None)
        sk_list.append(sd)
    sk_list.sort(
        key=lambda x: (
            x.get("component_name") or "",
            x.get("name", ""),
            json.dumps(
                x,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            ),
        )
    )
    canonical_body["sketches"] = _canonicalize_structural_value(sk_list, ref_map)

    # 7. Features (sorted by timeline_index)
    feat_list = []
    for f in features:
        fd = f.model_dump(mode="python") if isinstance(f, BaseModel) else dict(f)
        fd.pop("ref", None)
        fd.pop("id", None)
        # Normalize dependencies / inputs using semantic ref map
        for dep_key in ("inputs", "dependencies"):
            if dep_key in fd and isinstance(fd[dep_key], (list, tuple)):
                norm_deps = []
                for dep in fd[dep_key]:
                    dep_d = (
                        dep.model_dump(mode="python")
                        if isinstance(dep, BaseModel)
                        else dict(dep)
                    )
                    d_ref = dep_d.get("ref", "")
                    dep_d["target"] = ref_map.get(
                        d_ref, d_ref if not str(d_ref).startswith("ent_") else ""
                    )
                    dep_d.pop("ref", None)
                    norm_deps.append(dep_d)
                fd[dep_key] = norm_deps
        # Normalize outputs using semantic ref map
        if "outputs" in fd and isinstance(fd["outputs"], (list, tuple)):
            fd["outputs"] = [
                ref_map.get(o, o if not str(o).startswith("ent_") else "")
                for o in fd["outputs"]
            ]
        # Normalize parent / children
        if fd.get("parent"):
            p_val = fd["parent"]
            fd["parent"] = ref_map.get(
                p_val, p_val if not str(p_val).startswith("ent_") else ""
            )
        if fd.get("children"):
            fd["children"] = [
                ref_map.get(ch, ch if not str(ch).startswith("ent_") else "")
                for ch in fd["children"]
            ]
        feat_list.append(fd)
    feat_list.sort(
        key=lambda x: (
            int(x.get("timeline_index", 0)),
            x.get("name", ""),
            json.dumps(
                x,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            ),
        )
    )
    canonical_body["features"] = _canonicalize_structural_value(feat_list, ref_map)

    # 8. Parameters (sorted by is_user, name)
    param_list = []
    for p in params:
        pd = p.model_dump(mode="python") if isinstance(p, BaseModel) else dict(p)
        pd.pop("ref", None)
        pd.pop("id", None)
        param_list.append(pd)
    param_list.sort(
        key=lambda x: (
            not x.get("is_user", False),
            x.get("name", ""),
            json.dumps(
                x,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            ),
        )
    )
    canonical_body["parameters"] = _canonicalize_structural_value(param_list, ref_map)

    # 9. Summaries
    for key in ("visibility", "appearance", "health", "logical_objects"):
        if key in snapshot_dict:
            val = snapshot_dict[key]
            if isinstance(val, BaseModel):
                val = val.model_dump(mode="python")
            canonical_body[key] = _canonicalize_structural_value(val, ref_map)

    serialized = json.dumps(
        canonical_body, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def normalize_feature(
    raw: Mapping[str, Any],
    *,
    ref_registry: EntityRefRegistry | None = None,
    document_ref: str = "doc_main",
) -> FeatureRecord:
    """Normalize a feature record while strictly preserving inferred/unknown dependency types."""
    idx = int(raw.get("index", raw.get("timeline_index", 0)))
    name = str(raw.get("name", f"Feature_{idx}"))
    feat_type = str(raw.get("feature_type", raw.get("type", "Feature")))
    tok = str(raw.get("entityToken") or "")
    raw_id = str(raw.get("id") or "")
    raw_ref = str(raw.get("ref") or "")

    explicit_ref = raw_ref if re.match(ENTITY_REF_PATTERN, raw_ref) else None

    if ref_registry is not None:
        issued = ref_registry.issue(
            document_ref=document_ref,
            kind="feature",
            name=name,
            native_token=tok or (raw_id if raw_id and raw_id != explicit_ref else None),
            opaque_ref=explicit_ref,
        )
        final_ref = issued.ref
    else:
        final_ref = _safe_ent_ref(explicit_ref or raw_id or f"ent_feat_{idx}", "feat")

    deps_raw = raw.get("inputs") or raw.get("dependencies") or []
    norm_deps: list[FeatureDependency] = []
    for d in deps_raw:
        if isinstance(d, Mapping):
            d_ref = str(d.get("ref") or d.get("id") or "")
            d_ref_safe = _safe_ent_ref(d_ref, "dep")
            raw_type = str(d.get("dependency_type", "unknown"))
            # Invariant: Never upgrade inferred to exact
            if raw_type not in ("exact", "inferred", "unknown"):
                raw_type = "unknown"
            norm_deps.append(
                FeatureDependency(
                    ref=d_ref_safe,
                    kind=d.get("kind"),
                    dependency_type=raw_type,  # type: ignore[arg-type]
                )
            )
        elif isinstance(d, FeatureDependency):
            norm_deps.append(d)
        elif isinstance(d, str):
            norm_deps.append(
                FeatureDependency(
                    ref=_safe_ent_ref(d, "dep"),
                    dependency_type="unknown",
                )
            )

    outputs_raw = raw.get("outputs") or []
    norm_outputs = tuple(_safe_ent_ref(o, "out") for o in outputs_raw)

    feat_comp_path = (
        tuple(str(x) for x in raw.get("component_path", ()))
        if raw.get("component_path")
        else ((str(raw.get("component_name")),) if raw.get("component_name") else ())
    )
    parent_val = str(raw["parent"]) if raw.get("parent") is not None else None
    children_raw = raw.get("children") or ()
    children_val = (
        tuple(str(ch) for ch in children_raw)
        if isinstance(children_raw, (list, tuple))
        else ()
    )

    return FeatureRecord(
        ref=final_ref,
        timeline_index=idx,
        name=name,
        feature_type=feat_type,
        is_suppressed=bool(raw.get("is_suppressed", False)),
        health_status=str(raw.get("health_status", "ok")),
        diagnostic_message=raw.get("diagnostic_message"),
        component_path=feat_comp_path,
        dependencies=tuple(norm_deps),
        inputs=tuple(norm_deps),
        outputs=norm_outputs,
        parent=parent_val,
        children=children_val,
    )


def normalize_sketch_read(
    raw: Mapping[str, Any],
    *,
    ref_registry: EntityRefRegistry | None = None,
    document_ref: str = "doc_main",
    include_profiles: bool = True,
    include_constraints: bool = True,
) -> SketchReadResult:
    """Normalize a sketch read result without inventing unsupported DOF counts."""
    name = str(raw.get("name", "Sketch"))
    ref_str = str(raw.get("ref") or raw.get("id") or "ent_sketch_0")
    if ref_registry is not None:
        issued = ref_registry.issue(
            document_ref=document_ref,
            kind="sketch",
            name=name,
            native_token=str(raw.get("entityToken") or raw.get("id") or ""),
            opaque_ref=ref_str if re.match(ENTITY_REF_PATTERN, ref_str) else None,
        )
        final_ref = issued.ref
    else:
        final_ref = _safe_ent_ref(ref_str, "sk")

    # Fully constrained: preserve True/False if exposed; None if unsupported
    fc_val = raw.get("fully_constrained")
    fc_bool = bool(fc_val) if isinstance(fc_val, bool) else None

    # Profiles
    raw_profiles = raw.get("profiles", []) if include_profiles else []
    profiles_list = []
    for p in raw_profiles:
        if isinstance(p, Mapping):
            p_dict = dict(sanitize_public_payload(p))
            if "ref" in p_dict:
                p_dict["ref"] = _safe_ent_ref(p_dict["ref"], "prof")
            profiles_list.append(ImmutableMapping(p_dict))

    # Constraints
    raw_constraints = raw.get("constraints", []) if include_constraints else []
    constraints_list = [
        ImmutableMapping(dict(sanitize_public_payload(c)))
        for c in raw_constraints
        if isinstance(c, Mapping)
    ]

    # Dimensions
    raw_dimensions = raw.get("dimensions", [])
    dimensions_list = [
        ImmutableMapping(dict(sanitize_public_payload(d)))
        for d in raw_dimensions
        if isinstance(d, Mapping)
    ]

    # Geometry
    geom = raw.get("geometry", {})
    geom_dict = (
        ImmutableMapping(dict(sanitize_public_payload(geom)))
        if isinstance(geom, Mapping)
        else ImmutableMapping({})
    )

    # Plane
    plane_raw = raw.get("plane")
    plane_imm = (
        ImmutableMapping(dict(sanitize_public_payload(plane_raw)))
        if isinstance(plane_raw, Mapping)
        else None
    )

    return SketchReadResult(
        ref=final_ref,
        name=name,
        plane=plane_imm,
        geometry=geom_dict,
        dimensions=tuple(dimensions_list),
        constraints=tuple(constraints_list),
        profiles=tuple(profiles_list),
        fully_constrained=fc_bool,
        linked_projection_state=tuple(
            ImmutableMapping(dict(sanitize_public_payload(x)))
            for x in raw.get("linked_projection_state", [])
            if isinstance(x, Mapping)
        ),
        texts=tuple(
            ImmutableMapping(dict(sanitize_public_payload(x)))
            for x in raw.get("texts", [])
            if isinstance(x, Mapping)
        ),
        health=ImmutableMapping(dict(sanitize_public_payload(raw.get("health", {}))))
        if isinstance(raw.get("health"), Mapping)
        else ImmutableMapping({}),
        dof=None,  # strictly None; do not invent numeric DOF
    )


def normalize_snapshot(
    raw: Mapping[str, Any],
    *,
    detail: Literal["compact", "full"] = "compact",
    ref_registry: EntityRefRegistry | None = None,
    snapshot_id: str | None = None,
) -> ModelSnapshot:
    """Canonical normalization of a raw Fusion model state into a semantic ModelSnapshot."""
    # 1. Document identity
    doc_info = raw.get("document") if isinstance(raw.get("document"), Mapping) else {}
    doc_ref_raw = (
        doc_info.get("document_ref") or raw.get("document_ref") or "doc_active"
    )
    doc_ref = _safe_doc_ref(doc_ref_raw)
    rev_raw = raw.get("model_revision") or "rev_1"
    rev = rev_raw if re.match(MODEL_REVISION_PATTERN, rev_raw) else f"rev_{rev_raw}"
    snap_id = snapshot_id or f"snap_{uuid.uuid4().hex[:12]}"

    # 2. Components
    comps_raw = raw.get("components") or []
    norm_comps: list[ComponentSummary] = []
    for c in comps_raw:
        if isinstance(c, Mapping):
            c_name = str(c.get("name", ""))
            c_tok = str(c.get("entityToken") or "")
            raw_id = str(c.get("id") or "")
            # Invariant: native token must never be exposed via ComponentSummary.id
            native_tok = c_tok or (
                raw_id
                if raw_id and (len(raw_id) > 16 or raw_id.startswith("AQAA"))
                else None
            )
            safe_id = None
            if (
                raw_id
                and raw_id != c_tok
                and not raw_id.startswith("AQAA")
                and len(raw_id) <= 16
            ):
                safe_id = raw_id

            if ref_registry is not None:
                iss = ref_registry.issue(
                    document_ref=doc_ref,
                    kind="component",
                    name=c_name,
                    native_token=native_tok,
                )
                c_ref = iss.ref
            else:
                c_ref = _safe_ent_ref(c.get("ref") or safe_id or c_name, "comp")

            c_path = (
                tuple(str(x) for x in c.get("component_path", ()))
                if c.get("component_path")
                else ()
            )
            norm_comps.append(
                ComponentSummary(
                    ref=c_ref,
                    name=c_name,
                    component_path=c_path,
                    id=safe_id,
                )
            )
    norm_comps.sort(key=lambda x: (x.name, x.ref))

    # 3. Occurrences
    occs_raw = raw.get("occurrences") or []
    norm_occs: list[OccurrenceSummary] = []
    for o in occs_raw:
        if isinstance(o, Mapping):
            o_name = str(o.get("name", ""))
            o_path = str(o.get("full_path_name") or o_name)
            if ref_registry is not None:
                iss = ref_registry.issue(
                    document_ref=doc_ref,
                    kind="occurrence",
                    name=o_name,
                    native_token=str(o.get("entityToken") or o_path),
                )
                o_ref = iss.ref
            else:
                o_ref = _safe_ent_ref(o.get("ref") or o_path, "occ")

            t_val = o.get("transform")
            t_tuple = (
                tuple(float(x) for x in t_val)
                if isinstance(t_val, (list, tuple))
                else None
            )
            is_vis = bool(o.get("is_visible", True))
            eff_vis = bool(o.get("effective_visibility", is_vis))
            o_comp_path = (
                tuple(str(x) for x in o.get("component_path", ()))
                if o.get("component_path")
                else ()
            )
            norm_occs.append(
                OccurrenceSummary(
                    ref=o_ref,
                    name=o_name,
                    full_path_name=o_path,
                    component_path=o_comp_path,
                    is_visible=is_vis,
                    effective_visibility=eff_vis,
                    transform=t_tuple,
                )
            )
    norm_occs.sort(key=lambda x: x.full_path_name)

    # 4. Bodies
    bodies_raw = raw.get("bodies") or []
    norm_bodies: list[BodySummary] = []
    total_faces = 0
    total_edges = 0
    total_verts = 0

    for b in bodies_raw:
        if isinstance(b, Mapping):
            b_name = str(b.get("name", "Body"))
            b_comp = b.get("component_name")
            b_comp_path = (
                tuple(str(x) for x in b.get("component_path", ()))
                if b.get("component_path")
                else ((str(b_comp),) if b_comp else ())
            )
            b_native = b.get("entityToken") or b.get("native_token") or b.get("id")
            if ref_registry is not None:
                iss = ref_registry.issue(
                    document_ref=doc_ref,
                    kind="body",
                    name=b_name,
                    component_path=b_comp_path,
                    native_token=(
                        str(b_native).strip()
                        if b_native is not None and str(b_native).strip()
                        else None
                    ),
                )
                b_ref = iss.ref
            else:
                b_ref = _safe_ent_ref(b.get("ref") or b_name, "body")

            bb_raw = b.get("bounding_box")
            bb_model = None
            if isinstance(bb_raw, Mapping):
                min_pt = bb_raw.get("min", [0.0, 0.0, 0.0])
                max_pt = bb_raw.get("max", [0.0, 0.0, 0.0])
                frame_dict = bb_raw.get("frame") or {"space": "world"}
                bb_model = BoundingBox(
                    min_point=Point3(
                        x=float(min_pt[0]),
                        y=float(min_pt[1]),
                        z=float(min_pt[2]),
                        frame=CoordinateFrame(**frame_dict),
                    ),
                    max_point=Point3(
                        x=float(max_pt[0]),
                        y=float(max_pt[1]),
                        z=float(max_pt[2]),
                        frame=CoordinateFrame(**frame_dict),
                    ),
                    frame=CoordinateFrame(**frame_dict),
                )

            # Face / edge counts on body
            fc = int(b.get("faces_count") or len(b.get("faces", [])) or 0)
            ec = int(b.get("edges_count") or len(b.get("edges", [])) or 0)
            vc = int(b.get("vertices_count") or len(b.get("vertices", [])) or 0)
            total_faces += fc
            total_edges += ec
            total_verts += vc

            norm_bodies.append(
                BodySummary(
                    ref=b_ref,
                    name=b_name,
                    component_name=str(b_comp) if b_comp else None,
                    component_path=b_comp_path,
                    is_solid=bool(b.get("is_solid", True)),
                    volume=float(b["volume"]) if b.get("volume") is not None else None,
                    area=float(b["area"]) if b.get("area") is not None else None,
                    bounding_box=bb_model,
                    faces_count=fc,
                    edges_count=ec,
                    is_visible=bool(b.get("is_visible", True)),
                    effective_visibility=bool(b.get("effective_visibility", True)),
                )
            )
    norm_bodies.sort(key=lambda x: (x.component_name or "", x.name, x.ref))

    # 5. Sketches
    sketches_raw = raw.get("sketches") or []
    norm_sketches: list[SketchSummary] = []
    for s in sketches_raw:
        if isinstance(s, Mapping):
            s_name = str(s.get("name", "Sketch"))
            s_comp = s.get("component_name")
            s_comp_path = (
                tuple(str(x) for x in s.get("component_path", ()))
                if s.get("component_path")
                else ((str(s_comp),) if s_comp else ())
            )
            s_native = s.get("entityToken") or s.get("native_token") or s.get("id")
            if ref_registry is not None:
                iss = ref_registry.issue(
                    document_ref=doc_ref,
                    kind="sketch",
                    name=s_name,
                    native_token=(
                        str(s_native).strip()
                        if s_native is not None and str(s_native).strip()
                        else None
                    ),
                )
                s_ref = iss.ref
            else:
                s_ref = _safe_ent_ref(s.get("ref") or s_name, "sketch")

            fc_val = s.get("fully_constrained")
            fc_bool = bool(fc_val) if isinstance(fc_val, bool) else None
            norm_sketches.append(
                SketchSummary(
                    ref=s_ref,
                    name=s_name,
                    component_name=str(s_comp) if s_comp else None,
                    component_path=s_comp_path,
                    profiles_count=int(
                        s.get("profiles_count") or len(s.get("profiles", [])) or 0
                    ),
                    constraints_count=int(
                        s.get("constraints_count") or len(s.get("constraints", [])) or 0
                    ),
                    dimensions_count=int(
                        s.get("dimensions_count") or len(s.get("dimensions", [])) or 0
                    ),
                    fully_constrained=fc_bool,
                )
            )
    norm_sketches.sort(key=lambda x: (x.component_name or "", x.name, x.ref))

    # 6. Features / timeline
    timeline_raw = raw.get("timeline") or raw.get("features") or []
    norm_features: list[FeatureRecord] = []
    for f in timeline_raw:
        if isinstance(f, Mapping):
            norm_features.append(
                normalize_feature(f, ref_registry=ref_registry, document_ref=doc_ref)
            )
    norm_features.sort(key=lambda x: x.timeline_index)

    # 7. Parameters
    norm_params: list[ParameterSummary] = []
    params_raw = raw.get("parameters") or {}
    if isinstance(params_raw, Mapping):
        # Could be {"model_parameters": [...], "user_parameters": [...]} or flat
        for p_cat, is_u in (("model_parameters", False), ("user_parameters", True)):
            for p in params_raw.get(p_cat, []):
                if isinstance(p, Mapping):
                    p_name = str(p.get("name", ""))
                    p_val = float(p.get("value", 0.0))
                    p_expr = (
                        str(p.get("expression", ""))
                        if p.get("expression") is not None
                        else None
                    )
                    p_unit = str(p.get("unit", "mm"))
                    p_comp_path = (
                        tuple(str(x) for x in p.get("component_path", ()))
                        if p.get("component_path")
                        else (
                            (str(p.get("component_name")),)
                            if p.get("component_name")
                            else ()
                        )
                    )
                    norm_params.append(
                        ParameterSummary(
                            name=p_name,
                            value=p_val,
                            expression=p_expr,
                            unit=p_unit,
                            is_user=is_u,
                            component_path=p_comp_path,
                        )
                    )
    elif isinstance(params_raw, (list, tuple)):
        for p in params_raw:
            if isinstance(p, Mapping):
                p_name = str(p.get("name", ""))
                p_val = float(p.get("value", 0.0))
                p_expr = (
                    str(p.get("expression", ""))
                    if p.get("expression") is not None
                    else None
                )
                p_unit = str(p.get("unit", "mm"))
                is_u = bool(p.get("is_user", False))
                p_comp_path = (
                    tuple(str(x) for x in p.get("component_path", ()))
                    if p.get("component_path")
                    else (
                        (str(p.get("component_name")),)
                        if p.get("component_name")
                        else ()
                    )
                )
                norm_params.append(
                    ParameterSummary(
                        name=p_name,
                        value=p_val,
                        expression=p_expr,
                        unit=p_unit,
                        is_user=is_u,
                        component_path=p_comp_path,
                    )
                )
    norm_params.sort(key=lambda x: (not x.is_user, x.name))

    # 8. Counts
    counts_raw = raw.get("counts") if isinstance(raw.get("counts"), Mapping) else {}
    face_count = int(
        counts_raw.get("faces") or len(raw.get("faces", [])) or total_faces
    )
    edge_count = int(
        counts_raw.get("edges") or len(raw.get("edges", [])) or total_edges
    )
    vert_count = int(
        counts_raw.get("vertices") or len(raw.get("vertices", [])) or total_verts
    )

    counts_model = SnapshotCounts(
        components=len(norm_comps),
        occurrences=len(norm_occs),
        bodies=len(norm_bodies),
        sketches=len(norm_sketches),
        features=len(norm_features),
        parameters=len(norm_params),
        faces=face_count,
        edges=edge_count,
        vertices=vert_count,
    )

    # 9. Detail mode: compact vs full
    faces_tuple = None
    edges_tuple = None
    if detail == "full":
        if "faces" in raw and isinstance(raw["faces"], (list, tuple)):
            faces_tuple = tuple(
                ImmutableMapping(dict(sanitize_public_payload(f)))
                for f in raw["faces"]
                if isinstance(f, Mapping)
            )
        if "edges" in raw and isinstance(raw["edges"], (list, tuple)):
            edges_tuple = tuple(
                ImmutableMapping(dict(sanitize_public_payload(e)))
                for e in raw["edges"]
                if isinstance(e, Mapping)
            )

    # 10. Summaries (visibility, appearance, health, logical objects)
    vis_data = (
        ImmutableMapping(dict(sanitize_public_payload(raw.get("visibility", {}))))
        if isinstance(raw.get("visibility"), Mapping)
        else ImmutableMapping({})
    )
    app_data = (
        ImmutableMapping(dict(sanitize_public_payload(raw.get("appearance", {}))))
        if isinstance(raw.get("appearance"), Mapping)
        else ImmutableMapping({})
    )
    health_data = (
        ImmutableMapping(dict(sanitize_public_payload(raw.get("health", {}))))
        if isinstance(raw.get("health"), Mapping)
        else ImmutableMapping({})
    )
    logical_objs = tuple(
        ImmutableMapping(dict(sanitize_public_payload(lo)))
        for lo in raw.get("logical_objects", [])
        if isinstance(lo, Mapping)
    )

    # 11. Compute structural hash
    partial_dict = {
        "document_ref": doc_ref,
        "model_revision": rev,
        "counts": counts_model,
        "components": norm_comps,
        "occurrences": norm_occs,
        "bodies": norm_bodies,
        "sketches": norm_sketches,
        "features": norm_features,
        "parameters": norm_params,
        "visibility": vis_data,
        "appearance": app_data,
        "health": health_data,
        "logical_objects": logical_objs,
        "units": "mm",
    }
    struct_hash = compute_structural_hash(partial_dict)

    fp_raw = raw.get("fingerprint")
    fingerprint_val = str(fp_raw) if fp_raw is not None else None

    return ModelSnapshot(
        snapshot_id=snap_id,
        document_ref=doc_ref,
        model_revision=rev,
        structural_hash=struct_hash,
        fingerprint=fingerprint_val,
        counts=counts_model,
        components=tuple(norm_comps),
        occurrences=tuple(norm_occs),
        bodies=tuple(norm_bodies),
        sketches=tuple(norm_sketches),
        features=tuple(norm_features),
        parameters=tuple(norm_params),
        visibility=vis_data,
        appearance=app_data,
        health=health_data,
        logical_objects=logical_objs,
        faces=faces_tuple,
        edges=edges_tuple,
        units="mm",
        detail=detail,
    )


class SnapshotStore:
    """Bounded in-memory store for model snapshots per document with LRU eviction."""

    def __init__(
        self, *, max_documents: int = 16, max_snapshots_per_doc: int = 32
    ) -> None:
        self._max_documents = max_documents
        self._max_snapshots_per_doc = max_snapshots_per_doc
        self._snapshots: OrderedDict[str, OrderedDict[str, ModelSnapshot]] = (
            OrderedDict()
        )
        self._id_to_doc: dict[str, str] = {}

    def put(self, snapshot: ModelSnapshot) -> str:
        doc_ref = snapshot.document_ref
        snap_id = snapshot.snapshot_id

        if doc_ref in self._snapshots:
            self._snapshots.move_to_end(doc_ref)
        else:
            if len(self._snapshots) >= self._max_documents:
                _oldest_doc, oldest_map = self._snapshots.popitem(last=False)
                for sid in oldest_map:
                    self._id_to_doc.pop(sid, None)
            self._snapshots[doc_ref] = OrderedDict()

        doc_map = self._snapshots[doc_ref]
        if snap_id in doc_map:
            doc_map.move_to_end(snap_id)
        else:
            if len(doc_map) >= self._max_snapshots_per_doc:
                evicted_id, _ = doc_map.popitem(last=False)
                self._id_to_doc.pop(evicted_id, None)

        doc_map[snap_id] = snapshot
        self._id_to_doc[snap_id] = doc_ref
        return snap_id

    def get(
        self, snapshot_id: str, document_ref: str | None = None
    ) -> ModelSnapshot | None:
        doc_ref = document_ref or self._id_to_doc.get(snapshot_id)
        if not doc_ref or doc_ref not in self._snapshots:
            return None
        return self._snapshots[doc_ref].get(snapshot_id)

    def get_latest(self, document_ref: str) -> ModelSnapshot | None:
        doc_map = self._snapshots.get(document_ref)
        if not doc_map:
            return None
        return next(reversed(doc_map.values()))

    def list_for_document(self, document_ref: str) -> tuple[ModelSnapshot, ...]:
        doc_map = self._snapshots.get(document_ref)
        if not doc_map:
            return ()
        return tuple(doc_map.values())

    def clear(self, document_ref: str | None = None) -> None:
        if document_ref is not None:
            doc_map = self._snapshots.pop(document_ref, None)
            if doc_map:
                for sid in doc_map:
                    self._id_to_doc.pop(sid, None)
        else:
            self._snapshots.clear()
            self._id_to_doc.clear()

    def has(self, snapshot_id: str) -> bool:
        return snapshot_id in self._id_to_doc
