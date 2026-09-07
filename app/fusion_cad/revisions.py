from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.api.errors import ErrorCode
from app.fusion_cad.canonicalization import canonicalize_value
from app.fusion_cad.errors import FusionCadError


def _canonicalize_value(val: Any) -> Any:
    """Recursively canonicalize values for deterministic JSON serialization."""
    return canonicalize_value(val)


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
        raw_ref = str(doc.get("document_ref") or doc.get("id") or "")
        if raw_ref.startswith("doc_"):
            doc_ref = "doc_" + raw_ref[4:]
        elif raw_ref:
            doc_ref = "doc_" + raw_ref
        else:
            doc_ref = ""
        canonical["document"] = {
            "document_ref": doc_ref,
            "name": str(doc.get("name") or "") if doc.get("name") is not None else None,
            "is_modified": bool(doc.get("is_modified", False)),
            "saved_version": doc.get("saved_version"),
        }
    elif "document_ref" in payload or "is_modified" in payload:
        raw_ref = str(payload.get("document_ref", ""))
        if raw_ref.startswith("doc_"):
            doc_ref = "doc_" + raw_ref[4:]
        elif raw_ref:
            doc_ref = "doc_" + raw_ref
        else:
            doc_ref = ""
        canonical["document"] = {
            "document_ref": doc_ref,
            "name": str(payload.get("name", ""))
            if payload.get("name") is not None
            else None,
            "is_modified": bool(payload.get("is_modified", False)),
            "saved_version": payload.get("saved_version"),
        }

    # 2. Timeline feature identity / health / suppression
    if "timeline" in payload and isinstance(
        payload["timeline"], (list, tuple, Sequence)
    ):
        timeline_items: list[dict[str, Any]] = []
        for item in payload["timeline"]:
            if isinstance(item, Mapping):
                timeline_items.append(
                    {
                        "index": int(item.get("index", 0)),
                        "id": str(
                            item.get("id")
                            or item.get("entityToken")
                            or item.get("index", "")
                        ),
                        "name": str(item.get("name", "")),
                        "is_suppressed": bool(item.get("is_suppressed", False)),
                        "is_valid": bool(item.get("is_valid", True)),
                        "is_rolled_back": bool(item.get("is_rolled_back", False)),
                        "health_status": str(item.get("health_status"))
                        if item.get("health_status") is not None
                        else None,
                    }
                )
        timeline_items.sort(key=lambda x: (x["index"], x["id"], x["name"]))
        canonical["timeline"] = timeline_items

    # 3. Components / occurrences / transforms
    if "components" in payload and isinstance(
        payload["components"], (list, tuple, Sequence)
    ):
        components_items: list[dict[str, Any]] = []
        for c in payload["components"]:
            if isinstance(c, Mapping):
                components_items.append(
                    {
                        "name": str(c.get("name", "")),
                        "id": str(c.get("id", "")) if c.get("id") is not None else None,
                    }
                )
        components_items.sort(key=lambda x: (x["name"], x.get("id") or ""))
        canonical["components"] = components_items

    if "occurrences" in payload and isinstance(
        payload["occurrences"], (list, tuple, Sequence)
    ):
        occ_items: list[dict[str, Any]] = []
        for occ in payload["occurrences"]:
            if isinstance(occ, Mapping):
                transform = occ.get("transform")
                canonical_transform = (
                    _canonicalize_value(transform) if transform is not None else None
                )
                is_vis = bool(occ.get("is_visible", True))
                occ_items.append(
                    {
                        "name": str(occ.get("name", "")),
                        "full_path_name": str(
                            occ.get("full_path_name") or occ.get("name", "")
                        ),
                        "is_visible": is_vis,
                        "effective_visibility": bool(
                            occ.get("effective_visibility", is_vis)
                        ),
                        "transform": canonical_transform,
                    }
                )
        occ_items.sort(key=lambda x: x["full_path_name"])
        canonical["occurrences"] = occ_items

    # 4. Bodies and geometry summary
    if "bodies" in payload and isinstance(payload["bodies"], (list, tuple, Sequence)):
        body_items: list[dict[str, Any]] = []
        for b in payload["bodies"]:
            if isinstance(b, Mapping):
                bbox = b.get("bounding_box")
                is_vis = bool(b.get("is_visible", True))
                com = b.get("center_of_mass")
                verts = b.get("vertices")
                f_list = b.get("faces")
                e_list = b.get("edges")
                f_centroids = b.get("face_centroids")
                geom_sig = b.get("geometric_signature")
                body_items.append(
                    {
                        "name": str(b.get("name", "")),
                        "component": str(b.get("component"))
                        if b.get("component") is not None
                        else None,
                        "is_solid": bool(b.get("is_solid", True)),
                        "is_visible": is_vis,
                        "effective_visibility": bool(
                            b.get("effective_visibility", is_vis)
                        ),
                        "volume": _canonicalize_value(float(b.get("volume", 0.0))),
                        "area": _canonicalize_value(float(b.get("area", 0.0))),
                        "faces_count": int(b.get("faces_count", 0)),
                        "edges_count": int(b.get("edges_count", 0)),
                        "bounding_box": _canonicalize_value(bbox)
                        if bbox is not None
                        else None,
                        "center_of_mass": _canonicalize_value(com)
                        if com is not None
                        else None,
                        "vertices": _canonicalize_value(verts)
                        if verts is not None
                        else None,
                        "faces": _canonicalize_value(f_list)
                        if f_list is not None
                        else None,
                        "edges": _canonicalize_value(e_list)
                        if e_list is not None
                        else None,
                        "face_centroids": _canonicalize_value(f_centroids)
                        if f_centroids is not None
                        else None,
                        "geometric_signature": _canonicalize_value(geom_sig)
                        if geom_sig is not None
                        else None,
                    }
                )
        body_items.sort(key=lambda x: (x.get("component") or "", x["name"]))
        canonical["bodies"] = body_items

    # 5. Sketches and constraints
    if "sketches" in payload and isinstance(
        payload["sketches"], (list, tuple, Sequence)
    ):
        sketch_items: list[dict[str, Any]] = []
        for s in payload["sketches"]:
            if isinstance(s, Mapping):
                constraints = s.get("constraints")
                dimensions = s.get("dimensions")
                is_vis = bool(s.get("is_visible", True))
                cons_count = int(
                    s.get(
                        "constraints_count",
                        len(constraints)
                        if isinstance(constraints, (list, tuple))
                        else 0,
                    )
                )
                dim_count = int(
                    s.get(
                        "dimensions_count",
                        len(dimensions) if isinstance(dimensions, (list, tuple)) else 0,
                    )
                )
                curves = s.get("curves")
                points = s.get("points")
                s_bbox = s.get("bounding_box")
                sketch_items.append(
                    {
                        "name": str(s.get("name", "")),
                        "component": str(s.get("component"))
                        if s.get("component") is not None
                        else None,
                        "is_visible": is_vis,
                        "effective_visibility": bool(
                            s.get("effective_visibility", is_vis)
                        ),
                        "profiles_count": int(s.get("profiles_count", 0)),
                        "curves_count": int(s.get("curves_count", 0)),
                        "constraints_count": cons_count,
                        "constraints": _canonicalize_value(constraints)
                        if constraints is not None
                        else None,
                        "dimensions_count": dim_count,
                        "dimensions": _canonicalize_value(dimensions)
                        if dimensions is not None
                        else None,
                        "curves": _canonicalize_value(curves)
                        if curves is not None
                        else None,
                        "points": _canonicalize_value(points)
                        if points is not None
                        else None,
                        "bounding_box": _canonicalize_value(s_bbox)
                        if s_bbox is not None
                        else None,
                    }
                )
        sketch_items.sort(key=lambda x: (x.get("component") or "", x["name"]))
        canonical["sketches"] = sketch_items

    # 6. Parameter expressions and values
    if "parameters" in payload and isinstance(
        payload["parameters"], (list, tuple, Sequence)
    ):
        param_items: list[dict[str, Any]] = []
        for p in payload["parameters"]:
            if isinstance(p, Mapping):
                val = p.get("value", 0.0)
                param_items.append(
                    {
                        "name": str(p.get("name", "")),
                        "expression": str(p.get("expression", "")),
                        "value": _canonicalize_value(val),
                        "unit": str(p.get("unit", "")),
                        "is_favorite": bool(p.get("is_favorite", False)),
                    }
                )
        param_items.sort(key=lambda x: x["name"])
        canonical["parameters"] = param_items

    # 7. Bridge attributes
    if "attributes" in payload:
        raw_attrs = payload["attributes"]
        attr_items: list[dict[str, Any]] = []
        doc_id_for_attr = canonical.get("document", {}).get("document_ref", "")
        if isinstance(raw_attrs, Mapping):
            if not doc_id_for_attr or not str(doc_id_for_attr).strip():
                raise FusionCadError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Cannot canonicalize document attributes without a stable document_ref",
                )
            for k, v in raw_attrs.items():
                attr_items.append(
                    {
                        "owner_type": "document",
                        "owner_id": doc_id_for_attr,
                        "group": "bridge.cad/v1",
                        "name": str(k),
                        "value": str(v),
                    }
                )
        elif isinstance(raw_attrs, (list, tuple, Sequence)):
            for a in raw_attrs:
                if isinstance(a, Mapping):
                    owner_t = str(a.get("owner_type", "document"))
                    owner_id = str(
                        a.get(
                            "owner_id", doc_id_for_attr if owner_t == "document" else ""
                        )
                    )
                    if not owner_id or not owner_id.strip():
                        raise FusionCadError(
                            ErrorCode.INVALID_ARGUMENT,
                            "Attribute lacks stable owner_id; empty IDs or mutable names are rejected",
                            details={"attribute": dict(a)},
                        )
                    attr_items.append(
                        {
                            "owner_type": owner_t,
                            "owner_id": owner_id,
                            "group": str(a.get("group", "bridge.cad/v1")),
                            "name": str(a.get("name", "")),
                            "value": str(a.get("value", "")),
                        }
                    )
        attr_items.sort(
            key=lambda x: (
                x["owner_type"],
                x["owner_id"],
                x["group"],
                x["name"],
                x.get("value", ""),
            )
        )
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
        self._transactions: dict[str, dict[str, str]] = {}

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
                    details={
                        "document_ref": document_ref,
                        "expected_revision": None,
                        "applied": False,
                    },
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
                    "applied": False,
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
                    "applied": False,
                },
            )

        return rec

    def get_fingerprint(
        self, document_ref: str, revision: str | None = None
    ) -> str | None:
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
            # Clear any transactions bound to this document
            to_remove = [
                tid
                for tid, tb in self._transactions.items()
                if tb["document_ref"] == document_ref
            ]
            for tid in to_remove:
                self._transactions.pop(tid, None)
        else:
            self._documents.clear()
            self._history.clear()
            self._active_document_ref = None
            self._transactions.clear()

    # ------------------------------------------------------------------
    # Transaction baseline persistence (Task 4 foundation)
    # ------------------------------------------------------------------

    def begin_transaction(
        self,
        transaction_id: str,
        document_ref: str | None = None,
        baseline_revision: str | None = None,
        baseline_fingerprint: str | None = None,
    ) -> dict[str, str]:
        """Record baseline revision and fingerprint at transaction begin.

        Returns a dict with baseline_revision and baseline_fingerprint.
        preview/commit must bind to these stored values, not caller-selected
        expected_revision, to prevent freshness bypass.
        """
        if not transaction_id or not isinstance(transaction_id, str):
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                f"transaction_id must be a non-empty string, got {transaction_id!r}",
            )

        doc_ref = document_ref or self._active_document_ref
        if not doc_ref:
            raise FusionCadError(
                ErrorCode.NO_ACTIVE_DESIGN,
                "No active document for transaction begin",
            )

        rec = self._documents.get(doc_ref)
        if baseline_fingerprint is not None:
            b_fp = baseline_fingerprint
        else:
            b_fp = rec.fingerprint if rec else None

        if baseline_revision is not None:
            b_rev = baseline_revision
        else:
            b_rev = rec.revision if rec else None

        if not b_fp or not isinstance(b_fp, str) or not b_fp.strip():
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                "Authoritative baseline_fingerprint is required and cannot be empty",
                details={"transaction_id": transaction_id, "document_ref": doc_ref},
            )

        if not b_rev or not isinstance(b_rev, str) or not b_rev.strip():
            raise FusionCadError(
                ErrorCode.NO_ACTIVE_DESIGN,
                f"No observed revision for document '{doc_ref}' at transaction begin; cannot establish authoritative baseline",
                details={"transaction_id": transaction_id, "document_ref": doc_ref},
            )

        baseline = {
            "transaction_id": transaction_id,
            "document_ref": doc_ref,
            "baseline_revision": b_rev,
            "baseline_fingerprint": b_fp,
        }
        self._transactions[transaction_id] = baseline
        return baseline

    def get_transaction_baseline(
        self,
        transaction_id: str,
    ) -> dict[str, str] | None:
        """Look up stored baseline for a transaction.

        Returns None if no baseline is stored (transaction not begun).
        """
        return self._transactions.get(transaction_id)

    def clear_transaction(self, transaction_id: str) -> None:
        """Remove stored transaction baseline (after commit, abort, or rollback)."""
        self._transactions.pop(transaction_id, None)

    def snapshot(self) -> dict[str, Any]:
        """Create a deep snapshot of current tracker and transaction authority."""
        return {
            "documents": dict(self._documents),
            "history": {doc: list(recs) for doc, recs in self._history.items()},
            "active_document_ref": self._active_document_ref,
            "transactions": {
                tx_id: dict(data) for tx_id, data in self._transactions.items()
            },
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore tracker and transaction authority from a snapshot."""
        self._documents = dict(snapshot["documents"])
        self._history = {doc: list(recs) for doc, recs in snapshot["history"].items()}
        self._active_document_ref = snapshot["active_document_ref"]
        self._transactions = {
            tx_id: dict(data) for tx_id, data in snapshot["transactions"].items()
        }