from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError


def _canonicalize_value(val: Any) -> Any:
    """Recursively canonicalize values for deterministic JSON serialization."""
    if val is None or isinstance(val, (bool, int, str)):
        return val
    if isinstance(val, float):
        rounded = round(val, 6)
        return 0.0 if rounded == 0.0 else rounded
    if isinstance(val, Mapping):
        return {k: _canonicalize_value(val[k]) for k in sorted(val.keys())}
    if isinstance(val, (list, tuple, set, frozenset)):
        canonical_items = [_canonicalize_value(x) for x in val]
        try:
            return sorted(
                canonical_items,
                key=lambda item: (
                    json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                    if isinstance(item, (dict, list, tuple))
                    else str(item)
                ),
            )
        except (TypeError, ValueError):
            return canonical_items
    return str(val)


def canonicalize_fingerprint_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Sort and canonicalize mutation-sensitive semantic model data before hashing."""
    if not isinstance(payload, Mapping):
        raise FusionCadError(
            ErrorCode.INVALID_ARGUMENT,
            f"Expected mapping for model fingerprint payload, got {type(payload).__name__}",
        )

    canonical: dict[str, Any] = {}

    # 1. Document identity / modified marker
    if "document" in payload and isinstance(payload["document"], Mapping):
        doc = payload["document"]
        canonical["document"] = {
            "document_ref": str(doc.get("document_ref") or doc.get("id") or ""),
            "name": str(doc.get("name") or "") if doc.get("name") is not None else None,
            "is_modified": bool(doc.get("is_modified", False)),
            "saved_version": doc.get("saved_version"),
        }
    elif "document_ref" in payload or "is_modified" in payload:
        canonical["document"] = {
            "document_ref": str(payload.get("document_ref", "")),
            "name": str(payload.get("name", "")) if payload.get("name") is not None else None,
            "is_modified": bool(payload.get("is_modified", False)),
            "saved_version": payload.get("saved_version"),
        }

    # 2. Timeline feature identity / health / suppression
    if "timeline" in payload and isinstance(payload["timeline"], (list, tuple, Sequence)):
        timeline_items: list[dict[str, Any]] = []
        for item in payload["timeline"]:
            if isinstance(item, Mapping):
                timeline_items.append({
                    "index": int(item.get("index", 0)),
                    "id": str(item.get("id") or item.get("entityToken") or item.get("index", "")),
                    "name": str(item.get("name", "")),
                    "is_suppressed": bool(item.get("is_suppressed", False)),
                    "is_valid": bool(item.get("is_valid", True)),
                    "is_rolled_back": bool(item.get("is_rolled_back", False)),
                    "health_status": str(item.get("health_status")) if item.get("health_status") is not None else None,
                })
        timeline_items.sort(key=lambda x: (x["index"], x["id"], x["name"]))
        canonical["timeline"] = timeline_items

    # 3. Components / occurrences / transforms
    if "components" in payload and isinstance(payload["components"], (list, tuple, Sequence)):
        components_items: list[dict[str, Any]] = []
        for c in payload["components"]:
            if isinstance(c, Mapping):
                components_items.append({
                    "name": str(c.get("name", "")),
                    "id": str(c.get("id", "")) if c.get("id") is not None else None,
                })
        components_items.sort(key=lambda x: (x["name"], x.get("id") or ""))
        canonical["components"] = components_items

    if "occurrences" in payload and isinstance(payload["occurrences"], (list, tuple, Sequence)):
        occ_items: list[dict[str, Any]] = []
        for occ in payload["occurrences"]:
            if isinstance(occ, Mapping):
                transform = occ.get("transform")
                canonical_transform = _canonicalize_value(transform) if transform is not None else None
                occ_items.append({
                    "name": str(occ.get("name", "")),
                    "full_path_name": str(occ.get("full_path_name") or occ.get("name", "")),
                    "is_visible": bool(occ.get("is_visible", True)),
                    "transform": canonical_transform,
                })
        occ_items.sort(key=lambda x: x["full_path_name"])
        canonical["occurrences"] = occ_items

    # 4. Bodies and geometry summary
    if "bodies" in payload and isinstance(payload["bodies"], (list, tuple, Sequence)):
        body_items: list[dict[str, Any]] = []
        for b in payload["bodies"]:
            if isinstance(b, Mapping):
                bbox = b.get("bounding_box")
                body_items.append({
                    "name": str(b.get("name", "")),
                    "component": str(b.get("component")) if b.get("component") is not None else None,
                    "is_solid": bool(b.get("is_solid", True)),
                    "is_visible": bool(b.get("is_visible", True)),
                    "volume": _canonicalize_value(float(b.get("volume", 0.0))),
                    "area": _canonicalize_value(float(b.get("area", 0.0))),
                    "faces_count": int(b.get("faces_count", 0)),
                    "edges_count": int(b.get("edges_count", 0)),
                    "bounding_box": _canonicalize_value(bbox) if bbox is not None else None,
                })
        body_items.sort(key=lambda x: (x.get("component") or "", x["name"]))
        canonical["bodies"] = body_items

    # 5. Sketches and constraints
    if "sketches" in payload and isinstance(payload["sketches"], (list, tuple, Sequence)):
        sketch_items: list[dict[str, Any]] = []
        for s in payload["sketches"]:
            if isinstance(s, Mapping):
                constraints = s.get("constraints")
                sketch_items.append({
                    "name": str(s.get("name", "")),
                    "component": str(s.get("component")) if s.get("component") is not None else None,
                    "is_visible": bool(s.get("is_visible", True)),
                    "profiles_count": int(s.get("profiles_count", 0)),
                    "curves_count": int(s.get("curves_count", 0)),
                    "constraints_count": int(s.get("constraints_count", 0)),
                    "constraints": _canonicalize_value(constraints) if constraints is not None else None,
                })
        sketch_items.sort(key=lambda x: (x.get("component") or "", x["name"]))
        canonical["sketches"] = sketch_items

    # 6. Parameter expressions and values
    if "parameters" in payload and isinstance(payload["parameters"], (list, tuple, Sequence)):
        param_items: list[dict[str, Any]] = []
        for p in payload["parameters"]:
            if isinstance(p, Mapping):
                val = p.get("value", 0.0)
                param_items.append({
                    "name": str(p.get("name", "")),
                    "expression": str(p.get("expression", "")),
                    "value": _canonicalize_value(val),
                    "unit": str(p.get("unit", "")),
                    "is_favorite": bool(p.get("is_favorite", False)),
                })
        param_items.sort(key=lambda x: x["name"])
        canonical["parameters"] = param_items

    # 7. Bridge attributes
    if "attributes" in payload:
        raw_attrs = payload["attributes"]
        attr_items: list[dict[str, Any]] = []
        if isinstance(raw_attrs, Mapping):
            for k, v in raw_attrs.items():
                attr_items.append({
                    "group": "bridge.cad/v1",
                    "name": str(k),
                    "value": str(v),
                })
        elif isinstance(raw_attrs, (list, tuple, Sequence)):
            for a in raw_attrs:
                if isinstance(a, Mapping):
                    attr_items.append({
                        "group": str(a.get("group", "bridge.cad/v1")),
                        "name": str(a.get("name", "")),
                        "value": str(a.get("value", "")),
                    })
        attr_items.sort(key=lambda x: (x["group"], x["name"]))
        canonical["attributes"] = attr_items

    # 8. Effective visibility inputs
    if "visibility" in payload:
        canonical["visibility"] = _canonicalize_value(payload["visibility"])

    known_keys = {
        "document",
        "timeline",
        "components",
        "occurrences",
        "bodies",
        "sketches",
        "parameters",
        "attributes",
        "visibility",
    }
    for k in sorted(payload.keys()):
        if k not in known_keys and not k.startswith("_"):
            canonical[k] = _canonicalize_value(payload[k])

    return canonical


def compute_model_fingerprint(payload: Mapping[str, Any] | str) -> str:
    """Compute a deterministic SHA-256 model fingerprint over canonicalized data."""
    if isinstance(payload, str):
        return payload

    canonical = canonicalize_fingerprint_payload(payload)
    serialized = json.dumps(
        canonical,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RevisionRecord:
    """Immutable record of an observed document revision and its model fingerprint."""

    document_ref: str
    sequence: int
    revision: str
    fingerprint: str
    created_at: float = field(default_factory=time.time)

    @property
    def model_revision(self) -> str:
        return self.revision


class RevisionTracker:
    """Tracks document model revisions and external/Bridge mutations."""

    def __init__(self) -> None:
        self._documents: dict[str, RevisionRecord] = {}
        self._history: dict[str, list[RevisionRecord]] = {}
        self._active_document_ref: str | None = None

    @property
    def active_document_ref(self) -> str | None:
        return self._active_document_ref

    def observe(
        self,
        document_ref: str,
        fingerprint: str | Mapping[str, Any],
    ) -> RevisionRecord:
        """Observe a document fingerprint; advance sequence only on fingerprint change."""
        if not document_ref or not isinstance(document_ref, str):
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                f"document_ref must be a non-empty string, got {document_ref!r}",
            )

        effective_fp = (
            compute_model_fingerprint(fingerprint)
            if isinstance(fingerprint, Mapping)
            else str(fingerprint)
        )
        self._active_document_ref = document_ref

        if document_ref in self._documents:
            current_rec = self._documents[document_ref]
            if current_rec.fingerprint == effective_fp:
                return current_rec
            new_seq = current_rec.sequence + 1
            new_rec = RevisionRecord(
                document_ref=document_ref,
                sequence=new_seq,
                revision=f"rev_{new_seq}",
                fingerprint=effective_fp,
            )
            self._documents[document_ref] = new_rec
            self._history[document_ref].append(new_rec)
            return new_rec

        new_rec = RevisionRecord(
            document_ref=document_ref,
            sequence=1,
            revision="rev_1",
            fingerprint=effective_fp,
        )
        self._documents[document_ref] = new_rec
        self._history[document_ref] = [new_rec]
        return new_rec

    def current(self, document_ref: str | None = None) -> RevisionRecord | None:
        """Return the current revision record for document_ref, or active document."""
        if document_ref is not None:
            return self._documents.get(document_ref)
        if self._active_document_ref is not None:
            return self._documents.get(self._active_document_ref)
        return None

    def assert_expected(
        self,
        document_ref: str,
        expected_revision: str | None,
        *,
        require_revision: bool = True,
    ) -> RevisionRecord:
        """Assert that expected_revision matches the current tracked revision."""
        if not document_ref or not isinstance(document_ref, str):
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                f"document_ref must be a non-empty string, got {document_ref!r}",
            )

        if expected_revision is None:
            if require_revision:
                raise FusionCadError(
                    ErrorCode.REVISION_CONFLICT,
                    f"expected_revision is required for freshness check on document '{document_ref}'",
                    details={"document_ref": document_ref, "expected_revision": None},
                )
            rec = self._documents.get(document_ref)
            if rec is None:
                raise FusionCadError(
                    ErrorCode.NO_ACTIVE_DESIGN,
                    f"No observed revision for document '{document_ref}'",
                    details={"document_ref": document_ref},
                )
            return rec

        rec = self._documents.get(document_ref)
        if rec is None:
            raise FusionCadError(
                ErrorCode.REVISION_CONFLICT,
                f"No observed revision for document '{document_ref}' (expected '{expected_revision}')",
                details={
                    "document_ref": document_ref,
                    "expected_revision": expected_revision,
                    "current_revision": None,
                },
            )

        if rec.revision != expected_revision:
            raise FusionCadError(
                ErrorCode.REVISION_CONFLICT,
                f"Revision conflict for document '{document_ref}': expected '{expected_revision}', but current revision is '{rec.revision}'",
                details={
                    "document_ref": document_ref,
                    "expected_revision": expected_revision,
                    "current_revision": rec.revision,
                    "current_sequence": rec.sequence,
                },
            )

        return rec

    def get_fingerprint(self, document_ref: str, revision: str | None = None) -> str | None:
        """Retrieve fingerprint for a document at a specific revision or current."""
        if document_ref not in self._documents:
            return None
        if revision is None:
            return self._documents[document_ref].fingerprint
        for rec in reversed(self._history.get(document_ref, [])):
            if rec.revision == revision:
                return rec.fingerprint
        return None

    def close_document(self, document_ref: str) -> None:
        """Mark document closed and clear active document reference."""
        if self._active_document_ref == document_ref:
            self._active_document_ref = None

    def switch_document(self, document_ref: str) -> RevisionRecord | None:
        """Switch active document and return its current record if known."""
        self._active_document_ref = document_ref
        return self._documents.get(document_ref)

    def reset(self, document_ref: str | None = None) -> None:
        """Reset tracking state for a specific document or all documents."""
        if document_ref is not None:
            self._documents.pop(document_ref, None)
            self._history.pop(document_ref, None)
            if self._active_document_ref == document_ref:
                self._active_document_ref = None
        else:
            self._documents.clear()
            self._history.clear()
            self._active_document_ref = None
