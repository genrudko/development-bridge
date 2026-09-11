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


def _document_identity(ctx, design, components):
    doc = getattr(getattr(ctx, "app", None), "activeDocument", None)
    data_file = getattr(doc, "dataFile", None) if doc is not None else None
    data_id = _text(getattr(data_file, "id", None)) if data_file is not None else None
    component_tokens = sorted(t for t in (_token(c) for c in components) if t)
    return {
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
        if entity is not None:
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
        "guard": hashlib.sha256(encoded).hexdigest(),
    }


def _error(code, *, applied=False):
    return {
        "api_version": API_VERSION,
        "ok": False,
        "error": {"code": code, "applied": applied},
    }


def _validate_operations(raw_operations, registry, allowed_ops):
    if not isinstance(raw_operations, list) or not raw_operations:
        return None
    prepared = []
    for raw in raw_operations:
        if not isinstance(raw, Mapping):
            return None
        op_name = raw.get("op")
        params = raw.get("params", {})
        if not isinstance(op_name, str) or op_name not in allowed_ops:
            return None
        if op_name not in registry or not callable(registry[op_name]):
            return None
        if not isinstance(params, Mapping):
            return None
        prepared.append((op_name, dict(params)))
    return prepared


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
    expected_guard = params.get("expected_guard")
    mode = params.get("mode")
    if (
        not isinstance(expected_guard, str)
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
        guard_before = compute_provider_guard(ctx)["guard"]
    except Exception:
        return _error("FUSION_API_ERROR")
    if guard_before != expected_guard:
        return _error("REVISION_CONFLICT")

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
    try:
        for op_name, operation_params in operations:
            effect = registry[op_name](ctx, operation_params)
            effects.append({"op": op_name, "result": effect})
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
        return compute_provider_guard(ctx)

    @op("bridge.cad_apply", summary="Apply an allow-listed Development Bridge CAD plan under one Fusion transaction.")
    def bridge_cad_apply(ctx, params):
        return execute_guarded(ctx, params, REGISTRY)
