"""Development Bridge guarded mutation envelope for pinned Shimmer.

This file is copied into ``fusion_mcp_addin.ops.bridge_cad`` by install.py.
It deliberately delegates to Shimmer's existing operation registry instead of
reimplementing CAD algorithms.  The helpers are dependency-light so their
transaction/guard behavior can be tested without Autodesk Fusion installed.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping

API_VERSION = "bridge.shimmer/v1"
TRANSACTION_NAME = "bridge_cad_shimmer"

DEFAULT_ALLOWED_OPS = frozenset(
    {
        "sketch.create",
        "sketch.rectangle",
        "sketch.circle",
        "sketch.line",
        "sketch.constrain",
        "sketch.dimension",
        "feature.extrude",
        "feature.hole",
        "feature.fillet",
        "feature.chamfer",
    }
)


def _items(collection):
    if collection is None:
        return []
    count = getattr(collection, "count", None)
    item = getattr(collection, "item", None)
    if isinstance(count, int) and callable(item):
        return [item(i) for i in range(count)]
    try:
        return list(collection)
    except Exception:
        return []


def _text(value):
    if value is None:
        return None
    try:
        return str(value)
    except Exception:
        return None


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _token(value):
    for name in ("entityToken", "id"):
        try:
            token = getattr(value, name, None)
        except Exception:
            token = None
        if token is not None:
            token = _text(token)
            if token:
                return token
    return None


def _matrix_values(value):
    if value is None:
        return None
    try:
        raw = value.asArray() if callable(getattr(value, "asArray", None)) else value
        values = list(raw)
    except Exception:
        return None
    result = []
    for item in values:
        number = _finite(item)
        if number is None:
            return None
        result.append(number)
    return result


def _attribute_rows(owner, owner_kind, owner_id):
    try:
        attrs = getattr(owner, "attributes", None)
    except Exception:
        attrs = None
    rows = []
    for attr in _items(attrs):
        try:
            group = _text(getattr(attr, "groupName", None) or getattr(attr, "group", None))
            name = _text(getattr(attr, "name", None))
            value = _text(getattr(attr, "value", None))
        except Exception:
            continue
        if group == "bridge.cad/v1" and name is not None:
            rows.append(
                {
                    "owner_kind": owner_kind,
                    "owner_id": owner_id,
                    "group": group,
                    "name": name,
                    "value": value,
                }
            )
    return rows


def _active_document_ref(ctx):
    """Mirror P0's copy-safe document-ref normalization for provider binding."""
    doc = getattr(getattr(ctx, "app", None), "activeDocument", None)
    if doc is None:
        raise ValueError("active document required")
    try:
        data_file = getattr(doc, "dataFile", None)
    except Exception:
        data_file = None
    if data_file is not None:
        try:
            value = getattr(data_file, "id", None)
        except Exception:
            value = None
        if value is None or not str(value).strip():
            raise ValueError("saved/cloud document lacks DataFile.id")
        raw = str(value).strip()
    else:
        try:
            value = getattr(doc, "dataId", None)
        except Exception:
            value = None
        if value is not None and str(value).strip():
            raw = str(value).strip()
        else:
            try:
                creation = getattr(doc, "creationId", None)
                saved_version = getattr(doc, "savedVersion", None)
            except Exception:
                creation, saved_version = None, None
            if saved_version is not None:
                raise ValueError("saved document lacks copy-safe identity")
            if creation is None or not str(creation).strip():
                raise ValueError("document lacks stable runtime identity")
            raw = "unsaved_" + str(creation).strip()
    clean = re.sub(r"[^A-Za-z0-9._-]", "_", raw)
    return clean if clean.startswith("doc_") else "doc_" + clean


def _document_identity(ctx, design, components):
    doc = getattr(getattr(ctx, "app", None), "activeDocument", None)
    data_file = getattr(doc, "dataFile", None) if doc is not None else None
    data_id = _text(getattr(data_file, "id", None)) if data_file is not None else None
    component_tokens = sorted(t for t in (_token(c) for c in components) if t)
    return {
        "document_ref": _active_document_ref(ctx),
        "data_file_id": data_id,
        "document_name": _text(getattr(doc, "name", None)) if doc is not None else None,
        "root_component_token": _token(getattr(design, "rootComponent", None)),
        "component_tokens": component_tokens,
    }


def _provider_guard_payload(ctx):
    design = ctx.design()
    components = _items(getattr(design, "allComponents", None))
    component_rows = []
    attribute_rows = []
    for component in components:
        token = _token(component)
        name = _text(getattr(component, "name", None))
        revision = _text(getattr(component, "revisionId", None))
        component_rows.append({"token": token, "name": name, "revision_id": revision})
        attribute_rows.extend(_attribute_rows(component, "component", token or name or ""))
        for body in _items(getattr(component, "bRepBodies", None)):
            body_id = _token(body) or _text(getattr(body, "name", None)) or ""
            attribute_rows.extend(_attribute_rows(body, "body", body_id))
        for sketch in _items(getattr(component, "sketches", None)):
            sketch_id = _token(sketch) or _text(getattr(sketch, "name", None)) or ""
            attribute_rows.extend(_attribute_rows(sketch, "sketch", sketch_id))
    component_rows.sort(key=lambda row: (row["token"] or "", row["name"] or ""))

    root = getattr(design, "rootComponent", None)
    occurrence_rows = []
    for occurrence in _items(getattr(root, "allOccurrences", None)):
        try:
            transform = getattr(occurrence, "transform2", None)
        except Exception:
            transform = None
        if transform is None:
            try:
                transform = getattr(occurrence, "transform", None)
            except Exception:
                transform = None
        occurrence_rows.append(
            {
                "token": _token(occurrence),
                "path": _text(
                    getattr(occurrence, "fullPathName", None)
                    or getattr(occurrence, "name", None)
                ),
                "grounded": bool(getattr(occurrence, "isGrounded", False)),
                "visible": bool(getattr(occurrence, "isLightBulbOn", True)),
                "transform": _matrix_values(transform),
            }
        )
    occurrence_rows.sort(key=lambda row: (row["token"] or "", row["path"] or ""))

    parameter_rows = []
    for parameter in _items(getattr(design, "allParameters", None)):
        parameter_rows.append(
            {
                "name": _text(getattr(parameter, "name", None)),
                "expression": _text(getattr(parameter, "expression", None)),
                "value": _finite(getattr(parameter, "value", None)),
                "unit": _text(getattr(parameter, "unit", None)),
            }
        )
    parameter_rows.sort(key=lambda row: row["name"] or "")

    attribute_rows.extend(_attribute_rows(design, "design", "design"))
    timeline = getattr(design, "timeline", None)
    for index, timeline_item in enumerate(_items(timeline)):
        entity = getattr(timeline_item, "entity", None)
        owner = entity if entity is not None else timeline_item
        owner_id = _token(owner) or f"timeline:{index}"
        attribute_rows.extend(_attribute_rows(owner, "timeline", owner_id))
    attribute_rows.sort(
        key=lambda row: (
            row["owner_kind"], row["owner_id"], row["group"], row["name"], row["value"] or ""
        )
    )

    return {
        "document": _document_identity(ctx, design, components),
        "components": component_rows,
        "occurrences": occurrence_rows,
        "parameters": parameter_rows,
        "attributes": attribute_rows,
    }


def _entity_inventory(ctx):
    """Return a private token-keyed inventory for created/changed evidence."""
    design = ctx.design()
    rows = {}

    def add(kind, entity, signature=None):
        token = _token(entity)
        if not token:
            return
        rows[token] = {"kind": kind, "token": token, "signature": signature}

    for component in _items(getattr(design, "allComponents", None)):
        add("component", component, _text(getattr(component, "revisionId", None)))
        for body in _items(getattr(component, "bRepBodies", None)):
            add("body", body, _text(getattr(body, "revisionId", None)))
        for sketch in _items(getattr(component, "sketches", None)):
            add("sketch", sketch, _text(getattr(sketch, "revisionId", None)))

    root = getattr(design, "rootComponent", None)
    for occurrence in _items(getattr(root, "allOccurrences", None)):
        try:
            transform = getattr(occurrence, "transform2", None)
        except Exception:
            transform = None
        if transform is None:
            try:
                transform = getattr(occurrence, "transform", None)
            except Exception:
                transform = None
        signature = {
            "grounded": bool(getattr(occurrence, "isGrounded", False)),
            "visible": bool(getattr(occurrence, "isLightBulbOn", True)),
            "transform": _matrix_values(transform),
        }
        add("occurrence", occurrence, signature)

    timeline = getattr(design, "timeline", None)
    for item in _items(timeline):
        entity = getattr(item, "entity", None)
        if entity is None:
            continue
        # Timeline can expose sketches and other already-classified entities as
        # timeline items. Preserve their canonical entity kind; only classify a
        # token as a feature when it was not identified by a stronger collection.
        token = _token(entity)
        if token and token in rows:
            continue
        add("feature", entity, _text(getattr(entity, "revisionId", None)))
    return rows


def _entity_diff(before, after):
    def public(row):
        return {"kind": row["kind"], "token": row["token"]}

    created = [public(after[token]) for token in sorted(set(after) - set(before))]
    deleted = [public(before[token]) for token in sorted(set(before) - set(after))]
    changed = [
        public(after[token])
        for token in sorted(set(before) & set(after))
        if before[token].get("kind") != after[token].get("kind")
        or before[token].get("signature") != after[token].get("signature")
    ]
    return {"created": created, "changed": changed, "deleted": deleted}


def compute_provider_guard(ctx):
    payload = _provider_guard_payload(ctx)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return {
        "api_version": API_VERSION,
        "algorithm": "sha256",
        "document_ref": payload["document"]["document_ref"],
        "guard": hashlib.sha256(encoded).hexdigest(),
    }


def guard_for_document(ctx, params):
    if not isinstance(params, Mapping):
        return _error("INVALID_ARGUMENT")
    requested = params.get("document_ref")
    if not isinstance(requested, str) or not requested:
        return _error("INVALID_ARGUMENT")
    try:
        evidence = compute_provider_guard(ctx)
    except Exception:
        return _error("FUSION_API_ERROR")
    if evidence.get("document_ref") != requested:
        return _error("WRONG_DOCUMENT")
    return evidence


def _error(code, *, applied=False):
    return {
        "api_version": API_VERSION,
        "ok": False,
        "error": {"code": code, "applied": applied},
    }


class _PrivateResolutionError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _native_candidates(resolved):
    if resolved is None:
        return []
    if isinstance(resolved, (list, tuple)):
        return list(resolved)
    try:
        count_value = getattr(resolved, "count")
    except AttributeError:
        try:
            length = len(resolved)
        except (TypeError, AttributeError):
            return [resolved]
        except Exception:
            raise _PrivateResolutionError("REF_STALE") from None
        try:
            return [resolved[index] for index in range(length)]
        except Exception:
            raise _PrivateResolutionError("REF_STALE") from None
    except Exception:
        raise _PrivateResolutionError("REF_STALE") from None
    try:
        return [resolved.item(index) for index in range(int(count_value))]
    except Exception:
        raise _PrivateResolutionError("REF_STALE") from None


def _native_kind(entity):
    object_type = str(getattr(entity, "objectType", None) or type(entity).__name__)
    if "BRepBody" in object_type:
        return "body"
    if "BRepFace" in object_type:
        return "face"
    if "BRepEdge" in object_type:
        return "edge"
    if "SketchPoint" in object_type:
        return "sketch_point"
    if any(
        name in object_type
        for name in (
            "SketchCurve", "SketchLine", "SketchArc", "SketchCircle",
            "SketchEllipse", "SketchEllipticalArc", "SketchConicCurve",
            "SketchFittedSpline", "SketchControlPointSpline", "SketchFixedSpline",
        )
    ):
        return "sketch_curve"
    if object_type.endswith("Sketch") or object_type == "Sketch":
        return "sketch"
    if "Occurrence" in object_type:
        return "occurrence"
    if "Component" in object_type:
        return "component"
    return "other"


def _resolve_entity_marker(ctx, marker, expected_kind=None):
    if not isinstance(marker, Mapping):
        raise _PrivateResolutionError("INVALID_ARGUMENT")
    token = marker.get("token")
    declared_kind = marker.get("kind")
    if not isinstance(token, str) or not token or not isinstance(declared_kind, str):
        raise _PrivateResolutionError("INVALID_ARGUMENT")
    if expected_kind is not None and declared_kind != expected_kind:
        raise _PrivateResolutionError("TYPE_MISMATCH")
    try:
        resolver = getattr(ctx.design(), "findEntityByToken", None)
    except Exception:
        raise _PrivateResolutionError("REF_STALE") from None
    if not callable(resolver):
        raise _PrivateResolutionError("REF_STALE")
    try:
        matches = _native_candidates(resolver(token))
    except _PrivateResolutionError:
        raise
    except Exception:
        raise _PrivateResolutionError("REF_STALE") from None
    if len(matches) > 1:
        raise _PrivateResolutionError("REF_SPLIT")
    if not matches or matches[0] is None:
        raise _PrivateResolutionError("REF_STALE")
    entity = matches[0]
    if _native_kind(entity) != declared_kind:
        raise _PrivateResolutionError("TYPE_MISMATCH")
    return entity


def _index_in(collection, entity):
    for index, candidate in enumerate(_items(collection)):
        try:
            if candidate is entity or candidate == entity:
                return index
        except Exception:
            if candidate is entity:
                return index
    raise _PrivateResolutionError("REF_STALE")


def _body_index(ctx, body):
    return _index_in(getattr(ctx.target(), "bRepBodies", None), body)


def _sketch_index(ctx, sketch):
    return _index_in(getattr(ctx.target(), "sketches", None), sketch)


def _face_location(ctx, face):
    body = getattr(face, "body", None)
    if body is not None:
        try:
            return _body_index(ctx, body), _index_in(getattr(body, "faces", None), face)
        except _PrivateResolutionError:
            pass
    for body_index, candidate_body in enumerate(_items(getattr(ctx.target(), "bRepBodies", None))):
        try:
            face_index = _index_in(getattr(candidate_body, "faces", None), face)
            return body_index, face_index
        except _PrivateResolutionError:
            continue
    raise _PrivateResolutionError("REF_STALE")


def _edge_index_for_body(body, edge):
    return _index_in(getattr(body, "edges", None), edge)


def _sketch_entity_location(ctx, entity, kind):
    for sketch_index, sketch in enumerate(_items(getattr(ctx.target(), "sketches", None))):
        collection = (
            getattr(sketch, "sketchCurves", None)
            if kind == "sketch_curve"
            else getattr(sketch, "sketchPoints", None)
        )
        try:
            return sketch_index, _index_in(collection, entity)
        except _PrivateResolutionError:
            continue
    raise _PrivateResolutionError("REF_STALE")


def _is_entity_marker(value):
    return (
        isinstance(value, Mapping)
        and isinstance(value.get("token"), str)
        and isinstance(value.get("kind"), str)
    )


def _is_action_marker(value):
    return isinstance(value, Mapping) and isinstance(value.get("__bridge_action_ref__"), Mapping)


def _action_reference_ids(value):
    found = []
    if _is_action_marker(value):
        ref = value["__bridge_action_ref__"]
        action_id = ref.get("action_id")
        element = ref.get("element", "curve")
        index = ref.get("index", 0)
        if (
            not isinstance(action_id, str)
            or not action_id
            or element not in {"curve", "start", "end", "center"}
            or isinstance(index, bool)
            or not isinstance(index, int)
            or index < 0
        ):
            raise _PrivateResolutionError("INVALID_ARGUMENT")
        found.append(action_id)
    elif isinstance(value, Mapping):
        for item in value.values():
            found.extend(_action_reference_ids(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_action_reference_ids(item))
    return found


def _validate_operations(raw_operations, registry, allowed_ops):
    if not isinstance(raw_operations, list) or not raw_operations:
        return None
    prepared = []
    seen_ids = set()
    geometry_ids = set()
    for raw in raw_operations:
        if not isinstance(raw, Mapping):
            return None
        op_name = raw.get("op")
        params = raw.get("params", {})
        action_id = raw.get("action_id")
        if not isinstance(op_name, str) or op_name not in allowed_ops:
            return None
        if op_name not in registry or not callable(registry[op_name]):
            return None
        if not isinstance(params, Mapping):
            return None
        if action_id is not None:
            if not isinstance(action_id, str) or not action_id or action_id in seen_ids:
                return None
        try:
            refs = _action_reference_ids(params)
        except _PrivateResolutionError:
            return None
        if any(ref_id not in geometry_ids for ref_id in refs):
            return None
        if action_id is not None:
            seen_ids.add(action_id)
            if op_name in {"sketch.line", "sketch.rectangle", "sketch.circle"}:
                geometry_ids.add(action_id)
        prepared.append((op_name, action_id, dict(params)))
    return prepared


def _constraint_operand_kinds(kind):
    if kind == "coincident":
        return "sketch_point", "sketch_point"
    if kind == "midpoint":
        return "sketch_point", "sketch_curve"
    return "sketch_curve", "sketch_curve"


def _prepare_existing_sketch_operand(ctx, sketch_index, value, expected_kind):
    if _is_action_marker(value):
        return value
    if not _is_entity_marker(value):
        return value
    entity = _resolve_entity_marker(ctx, value, expected_kind)
    actual_sketch_index, entity_index = _sketch_entity_location(ctx, entity, expected_kind)
    if actual_sketch_index != sketch_index:
        raise _PrivateResolutionError("TYPE_MISMATCH")
    return entity_index


def _prepare_operation_params(ctx, op_name, params):
    prepared = dict(params)
    if op_name == "sketch.create":
        plane = prepared.get("plane")
        if _is_entity_marker(plane):
            face = _resolve_entity_marker(ctx, plane, "face")
            body_index, face_index = _face_location(ctx, face)
            prepared["plane"] = {"body": body_index, "face": face_index}
        return prepared

    if op_name in {
        "sketch.rectangle", "sketch.circle", "sketch.line",
        "sketch.constrain", "sketch.dimension",
    }:
        sketch_value = prepared.get("sketch")
        if _is_entity_marker(sketch_value):
            sketch = _resolve_entity_marker(ctx, sketch_value, "sketch")
            prepared["sketch"] = _sketch_index(ctx, sketch)
        sketch_index = prepared.get("sketch")
        if op_name in {"sketch.constrain", "sketch.dimension"}:
            if not isinstance(sketch_index, int):
                raise _PrivateResolutionError("INVALID_ARGUMENT")
            expected_one = "sketch_curve"
            expected_two = "sketch_curve"
            if op_name == "sketch.constrain":
                expected_one, expected_two = _constraint_operand_kinds(prepared.get("type"))
            for key, expected_kind in (("entity_one", expected_one), ("entity_two", expected_two)):
                if key in prepared and prepared[key] is not None:
                    prepared[key] = _prepare_existing_sketch_operand(
                        ctx, sketch_index, prepared[key], expected_kind
                    )
        return prepared

    if op_name == "feature.extrude":
        sketch_value = prepared.get("sketch")
        if _is_entity_marker(sketch_value):
            sketch = _resolve_entity_marker(ctx, sketch_value, "sketch")
            prepared["sketch"] = _sketch_index(ctx, sketch)
        return prepared

    if op_name == "feature.hole":
        plane = prepared.get("plane")
        if _is_entity_marker(plane):
            face = _resolve_entity_marker(ctx, plane, "face")
            body_index, face_index = _face_location(ctx, face)
            prepared["plane"] = {"body": body_index, "face": face_index}
        return prepared

    if op_name in {"feature.fillet", "feature.chamfer"}:
        body_value = prepared.get("body")
        if not _is_entity_marker(body_value):
            return prepared
        body = _resolve_entity_marker(ctx, body_value, "body")
        prepared["body"] = _body_index(ctx, body)
        edges = prepared.get("edges")
        if isinstance(edges, list):
            resolved_edges = []
            for edge_value in edges:
                edge = _resolve_entity_marker(ctx, edge_value, "edge")
                try:
                    resolved_edges.append(_edge_index_for_body(body, edge))
                except _PrivateResolutionError:
                    raise _PrivateResolutionError("TYPE_MISMATCH") from None
            prepared["edges"] = resolved_edges
        return prepared

    return prepared


def _resolve_action_marker(ctx, marker, action_state, sketch_index, expected_kind):
    ref = marker["__bridge_action_ref__"]
    action_id = ref.get("action_id")
    element = ref.get("element", "curve")
    local_index = ref.get("index", 0)
    state = action_state.get(action_id)
    if state is None or state.get("sketch") != sketch_index:
        raise _PrivateResolutionError("INVALID_ARGUMENT")
    curves = state.get("curves") or []
    if local_index >= len(curves):
        raise _PrivateResolutionError("INVALID_ARGUMENT")
    curve_index = curves[local_index]
    if element == "curve":
        if expected_kind != "sketch_curve":
            raise _PrivateResolutionError("TYPE_MISMATCH")
        return curve_index
    if expected_kind != "sketch_point":
        raise _PrivateResolutionError("TYPE_MISMATCH")
    sketch = ctx.get_sketch(sketch_index)
    curve = sketch.sketchCurves.item(curve_index)
    attr = {"start": "startSketchPoint", "end": "endSketchPoint", "center": "centerSketchPoint"}.get(element)
    point = getattr(curve, attr, None) if attr else None
    if point is None:
        raise _PrivateResolutionError("INVALID_ARGUMENT")
    return _index_in(getattr(sketch, "sketchPoints", None), point)


def _resolve_runtime_action_refs(ctx, op_name, params, action_state):
    if op_name not in {"sketch.constrain", "sketch.dimension"}:
        return params
    prepared = dict(params)
    sketch_index = prepared.get("sketch")
    if not isinstance(sketch_index, int):
        raise _PrivateResolutionError("INVALID_ARGUMENT")
    expected_one = "sketch_curve"
    expected_two = "sketch_curve"
    if op_name == "sketch.constrain":
        expected_one, expected_two = _constraint_operand_kinds(prepared.get("type"))
    for key, expected_kind in (("entity_one", expected_one), ("entity_two", expected_two)):
        value = prepared.get(key)
        if _is_action_marker(value):
            prepared[key] = _resolve_action_marker(
                ctx, value, action_state, sketch_index, expected_kind
            )
    return prepared


def _capture_geometry_action(ctx, op_name, params):
    if op_name not in {"sketch.line", "sketch.rectangle", "sketch.circle"}:
        return None
    sketch_ref = params.get("sketch")
    if not isinstance(sketch_ref, int):
        raise _PrivateResolutionError("INVALID_ARGUMENT")
    sketch = ctx.get_sketch(sketch_ref)
    return {
        "sketch": sketch_ref,
        "curve_count": len(_items(getattr(sketch, "sketchCurves", None))),
    }


def _record_geometry_action(ctx, capture):
    sketch_index = capture["sketch"]
    sketch = ctx.get_sketch(sketch_index)
    after_count = len(_items(getattr(sketch, "sketchCurves", None)))
    before_count = capture["curve_count"]
    if after_count <= before_count:
        raise _PrivateResolutionError("FUSION_API_ERROR")
    return {
        "sketch": sketch_index,
        "curves": list(range(before_count, after_count)),
    }


def _abort_and_prove(ctx, guard_before):
    try:
        aborted = str(ctx.app.executeTextCommand("PTransaction.Abort")).strip() == "1"
    except Exception:
        return False, None
    if not aborted:
        return False, None
    try:
        guard_after = compute_provider_guard(ctx)["guard"]
    except Exception:
        return False, None
    return guard_after == guard_before, guard_after


def execute_guarded(ctx, params, registry, allowed_ops=None):
    """Execute an allow-listed Shimmer plan under one Fusion PTransaction."""
    if not isinstance(params, Mapping):
        return _error("INVALID_ARGUMENT")
    requested_document_ref = params.get("document_ref")
    expected_guard = params.get("expected_guard")
    mode = params.get("mode")
    if (
        not isinstance(requested_document_ref, str)
        or not requested_document_ref
        or not isinstance(expected_guard, str)
        or len(expected_guard) != 64
        or any(ch not in "0123456789abcdefABCDEF" for ch in expected_guard)
        or mode not in {"commit", "preview"}
    ):
        return _error("INVALID_ARGUMENT")

    allowed = frozenset(allowed_ops) if allowed_ops is not None else DEFAULT_ALLOWED_OPS
    operations = _validate_operations(params.get("operations"), registry, allowed)
    if operations is None:
        return _error("INVALID_ARGUMENT")

    try:
        guard_evidence = compute_provider_guard(ctx)
    except Exception:
        return _error("FUSION_API_ERROR")
    if guard_evidence.get("document_ref") != requested_document_ref:
        return _error("WRONG_DOCUMENT")
    guard_before = guard_evidence["guard"]
    if guard_before != expected_guard:
        return _error("REVISION_CONFLICT")

    try:
        operations = [
            (op_name, action_id, _prepare_operation_params(ctx, op_name, operation_params))
            for op_name, action_id, operation_params in operations
        ]
    except _PrivateResolutionError as exc:
        return _error(exc.code)
    except Exception:
        return _error("FUSION_API_ERROR")

    try:
        entities_before = _entity_inventory(ctx)
    except Exception:
        return _error("FUSION_API_ERROR")

    try:
        started = str(
            ctx.app.executeTextCommand(f'PTransaction.Start "{TRANSACTION_NAME}"')
        ).strip()
    except Exception:
        return _error("OPERATION_UNCERTAIN", applied=None)
    if started != "1":
        return _error("FUSION_API_ERROR")

    effects = []
    action_state = {}
    try:
        for op_name, action_id, operation_params in operations:
            runtime_params = _resolve_runtime_action_refs(
                ctx, op_name, operation_params, action_state
            )
            capture = (
                _capture_geometry_action(ctx, op_name, runtime_params)
                if action_id is not None
                else None
            )
            effect = registry[op_name](ctx, runtime_params)
            if action_id is not None and capture is not None:
                action_state[action_id] = _record_geometry_action(ctx, capture)
            effects.append({"op": op_name, "result": effect})
    except _PrivateResolutionError as exc:
        restored, guard_after = _abort_and_prove(ctx, guard_before)
        if restored:
            result = _error(exc.code)
            result["guard_after"] = guard_after
            return result
        return _error("OPERATION_UNCERTAIN", applied=None)
    except Exception:
        restored, guard_after = _abort_and_prove(ctx, guard_before)
        if restored:
            result = _error("FUSION_API_ERROR")
            result["guard_after"] = guard_after
            return result
        return _error("OPERATION_UNCERTAIN", applied=None)

    try:
        entities_after_apply = _entity_inventory(ctx)
        entity_evidence = _entity_diff(entities_before, entities_after_apply)
    except Exception:
        restored, _guard_after = _abort_and_prove(ctx, guard_before)
        if restored:
            return _error("FUSION_API_ERROR")
        return _error("OPERATION_UNCERTAIN", applied=None)

    if mode == "preview":
        try:
            preview_guard = compute_provider_guard(ctx)["guard"]
        except Exception:
            preview_guard = None
        restored, guard_after = _abort_and_prove(ctx, guard_before)
        if not restored:
            return _error("OPERATION_UNCERTAIN", applied=None)
        return {
            "api_version": API_VERSION,
            "ok": True,
            "mode": "preview",
            "document_ref": requested_document_ref,
            "guard_before": guard_before,
            "preview_guard": preview_guard,
            "guard_after": guard_after,
            "effects": effects,
            "entities": entity_evidence,
        }

    # Once commit has been attempted its outcome is never auto-replayed or
    # auto-aborted: a transport/runtime exception here is semantically uncertain.
    try:
        committed = str(ctx.app.executeTextCommand("PTransaction.Commit")).strip()
    except Exception:
        return _error("OPERATION_UNCERTAIN", applied=None)
    if committed != "1":
        return _error("OPERATION_UNCERTAIN", applied=None)
    try:
        guard_after = compute_provider_guard(ctx)["guard"]
    except Exception:
        return _error("OPERATION_UNCERTAIN", applied=True)
    return {
        "api_version": API_VERSION,
        "ok": True,
        "mode": "commit",
        "document_ref": requested_document_ref,
        "guard_before": guard_before,
        "guard_after": guard_after,
        "effects": effects,
        "entities": entity_evidence,
    }


# Auto-register only when this file lives inside the pinned Shimmer add-in.
try:  # pragma: no cover - exercised in live Shimmer, pure helpers are unit tested.
    from ._common import REGISTRY, op
except (ImportError, ModuleNotFoundError):  # standalone test/import outside Shimmer
    REGISTRY = None
    op = None

if op is not None:

    @op("bridge.cad_guard", summary="Return Development Bridge private CAD provider guard.", readonly=True)
    def bridge_cad_guard(ctx, params):
        return guard_for_document(ctx, params)

    @op("bridge.cad_apply", summary="Apply an allow-listed Development Bridge CAD plan under one Fusion transaction.")
    def bridge_cad_apply(ctx, params):
        return execute_guarded(ctx, params, REGISTRY)
