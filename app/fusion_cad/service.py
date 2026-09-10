from __future__ import annotations

import json
import math
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError

from app.api.errors import BridgeError, ErrorCode
from app.desktop_nodes.service import DesktopNodeService, has_binary_data
from app.fusion_cad.capabilities import (
    CapabilityMatrix,
    FusionRuntimeIdentity,
    get_required_capability,
)
from app.fusion_cad.errors import (
    FusionCadError,
    filter_trusted_diagnostics,
    format_safe_validation_message,
    get_safe_error_message,
    sanitize_public_payload,
    sanitize_validation_errors,
    trusted_detail,
)
from app.fusion_cad.inspect import normalize_inspect_result
from app.fusion_cad.metadata import (
    ProvenanceRecord,
    apply_geometry_provenance_plan,
    apply_metadata_mutation_plan,
    assert_reserved_metadata_group,
    parse_provenance_attribute,
)
from app.fusion_cad.models import (
    ENTITY_REF_PATTERN,
    CadResult,
    DocumentState,
    ImmutableMapping,
)
from app.fusion_cad.refs import EntityRefRegistry, InternalEntityRecord
from app.fusion_cad.requests import (
    FusionInspectRequest,
    FusionMetadataRequest,
    FusionReadRequest,
    FusionStyleRequest,
    FusionTransactionRequest,
    FusionValidateRequest,
    FusionViewRequest,
    _StrictCadBase,
)
from app.fusion_cad.revisions import RevisionRecord, RevisionTracker
from app.fusion_cad.scripts import FusionCadScriptBundle
from app.fusion_cad.selectors import SelectorEngine
from app.fusion_cad.snapshots import (
    SnapshotStore,
    normalize_feature,
    normalize_sketch_read,
    normalize_snapshot,
)
from app.fusion_cad.text import normalize_text_lineage
from app.fusion_cad.transactions import TransactionState, TransactionStore
from app.fusion_cad.validation import P0_VALIDATION_PROFILES, validate_model_evidence
from app.fusion_cad.views import (
    ViewRefStore,
    canonicalize_section_payload,
    canonicalize_visibility_payload,
    normalize_camera_context,
)

_GROUP_REQUEST_ADAPTERS: dict[str, TypeAdapter[Any]] = {
    "read": TypeAdapter(FusionReadRequest),
    "inspect": TypeAdapter(FusionInspectRequest),
    "view": TypeAdapter(FusionViewRequest),
    "metadata": TypeAdapter(FusionMetadataRequest),
    "style": TypeAdapter(FusionStyleRequest),
    "validate": TypeAdapter(FusionValidateRequest),
    "transaction": TypeAdapter(FusionTransactionRequest),
}

# Exhaustive per-(group, operation) classification mapping:
# (group, operation) -> (is_async, is_mutation)
_CAD_OPERATION_CLASSIFICATION: dict[tuple[str, str], tuple[bool, bool]] = {
    # 1. fusion_read
    ("read", "entity"): (False, False),
    ("read", "feature_tree"): (False, False),
    ("read", "sketch"): (False, False),
    ("read", "parameters"): (False, False),
    ("read", "visibility"): (False, False),
    ("read", "selection"): (False, False),
    ("read", "query"): (False, False),
    ("read", "capabilities"): (False, False),
    ("read", "echo"): (False, False),
    ("read", "model_snapshot"): (False, False),
    # 2. fusion_inspect (all 15 inspect operations are sync, non-mutating)
    ("inspect", "describe"): (False, False),
    ("inspect", "bounding_box"): (False, False),
    ("inspect", "oriented_bbox"): (False, False),
    ("inspect", "centroid"): (False, False),
    ("inspect", "area"): (False, False),
    ("inspect", "perimeter"): (False, False),
    ("inspect", "volume"): (False, False),
    ("inspect", "distance"): (False, False),
    ("inspect", "minimum_distance"): (False, False),
    ("inspect", "angle"): (False, False),
    ("inspect", "parallel"): (False, False),
    ("inspect", "perpendicular"): (False, False),
    ("inspect", "coplanar"): (False, False),
    ("inspect", "concentric"): (False, False),
    ("inspect", "face_to_face_thickness"): (False, False),
    # 3. fusion_view (camera mutations default async and non-replayable; screenshot is async)
    ("view", "camera_read"): (False, False),
    ("view", "pick"): (False, False),
    ("view", "camera_set"): (True, True),
    ("view", "fit"): (True, True),
    ("view", "zoom_entity"): (True, True),
    ("view", "orient_to_face"): (True, True),
    ("view", "standard_view"): (True, True),
    ("view", "screenshot"): (True, False),
    # 4. fusion_metadata & fusion_style mutations
    ("mutate", "get"): (False, False),
    ("mutate", "query"): (False, False),
    ("mutate", "provenance"): (False, False),
    ("mutate", "set"): (True, True),
    ("mutate", "remove"): (True, True),
    ("mutate", "tag"): (True, True),
    ("mutate", "untag"): (True, True),
    ("mutate", "set_role"): (True, True),
    ("mutate", "clear_role"): (True, True),
    # 5. fusion_style text and visibility
    ("mutate", "text_read"): (False, False),
    ("mutate", "text_create"): (True, True),
    ("mutate", "text_update"): (True, True),
    ("mutate", "text_delete"): (True, True),
    ("mutate", "text_extrude"): (True, True),
    ("mutate", "text_cut"): (True, True),
    ("mutate", "show"): (True, True),
    ("mutate", "hide"): (True, True),
    ("mutate", "show_only"): (True, True),
    ("mutate", "isolate"): (True, True),
    ("mutate", "restore"): (True, True),
    # 6. fusion_validate
    ("validate", "run"): (True, False),
    # 7. fusion_transaction
    ("transaction", "begin"): (True, True),
    ("transaction", "stage"): (True, True),
    ("transaction", "status"): (False, False),
    ("transaction", "abort"): (True, True),
    ("transaction", "preview"): (True, True),
    ("transaction", "commit"): (True, True),
    ("transaction", "rollback"): (True, True),
}


@dataclass(frozen=True, slots=True)
class _CachedNodeCapabilities:
    matrix: CapabilityMatrix
    session_generation: int


CAD_RESULT_INLINE_LIMIT_BYTES: int = 1_048_576

# Task 10: reserved-namespace metadata operations (fusion_metadata family)
_METADATA_READ_OPS = frozenset({"get", "query", "provenance"})
_METADATA_MUTATION_OPS = frozenset(
    {"set", "remove", "tag", "untag", "set_role", "clear_role"}
)
_METADATA_OPS = _METADATA_READ_OPS | _METADATA_MUTATION_OPS

_VIEW_FINALIZE_OPS = frozenset(
    {
        "camera_read",
        "camera_set",
        "fit",
        "zoom_entity",
        "orient_to_face",
        "standard_view",
        "screenshot",
    }
)


class FusionCadService:
    """Domain service for Fusion CAD workstation operations.

    Orchestrates domain requests above the outbound Windows DesktopNodeService.
    Reuses existing desktop-node sync/async execution and external-result
    handling without duplicating the operation journal or introducing global state.
    """

    def __init__(
        self,
        desktop_nodes: DesktopNodeService,
        script_bundle: FusionCadScriptBundle | None = None,
        revision_tracker: RevisionTracker | None = None,
        ref_registry: EntityRefRegistry | None = None,
        snapshot_store: SnapshotStore | None = None,
        view_store: ViewRefStore | None = None,
        transaction_store: TransactionStore | None = None,
        inline_limit_bytes: int = CAD_RESULT_INLINE_LIMIT_BYTES,
    ) -> None:
        self._desktop_nodes = desktop_nodes
        self._script_bundle = script_bundle or FusionCadScriptBundle()
        self._revision_tracker = revision_tracker or RevisionTracker()
        self._ref_registry = ref_registry or EntityRefRegistry()
        self._snapshot_store = snapshot_store or SnapshotStore()
        self._view_store = view_store or ViewRefStore()
        self._transaction_store = transaction_store or TransactionStore()
        self._selector_engine = SelectorEngine()
        self.inline_limit_bytes = inline_limit_bytes
        self._node_capabilities: dict[str, _CachedNodeCapabilities] = {}
        self._active_document_refs_by_node: dict[str, str] = {}
        self._visibility_restore_states: dict[str, dict[str, Any]] = {}

    @property
    def revision_tracker(self) -> RevisionTracker:
        return self._revision_tracker

    @property
    def ref_registry(self) -> EntityRefRegistry:
        return self._ref_registry

    @property
    def snapshot_store(self) -> SnapshotStore:
        return self._snapshot_store

    @property
    def view_store(self) -> ViewRefStore:
        return self._view_store

    @property
    def transaction_store(self) -> TransactionStore:
        return self._transaction_store

    @property
    def selector_engine(self) -> SelectorEngine:
        return self._selector_engine

    def build_current_view_context(
        self,
        node_id: str,
        document_ref: str | None = None,
    ) -> dict[str, Any] | None:
        """Build the current immutable-view freshness context for a node/document.

        Combines the latest observed camera/visibility/section state with the
        current observed model revision. Returns None when no view context has
        been observed for the node yet (Task 9 pick then fails closed).
        """
        state = self._view_store.current(node_id)
        if state is None:
            return None
        doc_ref = document_ref or state.document_ref
        rec = self._revision_tracker.current(doc_ref)
        model_revision = rec.revision if rec is not None else None
        return {
            "document_ref": doc_ref,
            "model_revision": model_revision,
            "camera_revision": state.camera_revision,
            "visibility_revision": state.visibility_revision,
            "section_revision": state.section_revision,
            "viewport_width": state.camera.viewport_width,
            "viewport_height": state.camera.viewport_height,
        }

    def assert_view_fresh(
        self,
        view_ref: str,
        node_id: str,
        document_ref: str | None = None,
    ) -> Any:
        """Assert a screenshot ViewRef is still fresh against current view context.

        Implements the immutable view invariant before any screenshot coordinate
        is ever reinterpreted. Exposed for Task 9 (screen-space pick) to consume;
        this task only wires the freshness path.
        """
        current = self.build_current_view_context(node_id, document_ref)
        if current is None:
            raise FusionCadError(
                ErrorCode.VIEW_STALE,
                "Current view context is unknown for node; capture a camera or screenshot operation first",
                details={"node_id": node_id, "view_ref": view_ref},
            )
        return self._view_store.assert_fresh(view_ref, current_context=current)

    def _is_oversized(self, payload: dict[str, Any]) -> bool:
        try:
            raw = json.dumps(payload, default=str)
            return len(raw.encode("utf-8")) > self.inline_limit_bytes
        except (TypeError, ValueError, OverflowError):
            return False

    @staticmethod
    def _finalization_context(
        payload: Mapping[str, Any], *, group: str, operation: str
    ) -> dict[str, Any]:
        """Return only semantic fields consumed after async terminal delivery."""
        keys = {"operation", "transaction_id", "document_ref"}
        if group == "transaction" and operation == "stage":
            keys.add("action")
        elif group == "mutate":
            keys.update(
                {
                    "logical_object_ref",
                    "text_ref",
                    "provenance",
                    "style_semantic_contract",
                    "target",
                    "visible",
                    "name",
                }
            )
        elif group == "read":
            keys.update(
                {
                    "detail",
                    "include_profiles",
                    "include_constraints",
                    "include_model_params",
                    "include_user_params",
                    "selector",
                    "limit",
                }
            )
        elif group == "view" and operation == "pick":
            keys.add("_pick_expected")
        elif group == "validate" and operation == "run":
            keys.update({"profiles", "checks"})
        return dict(
            sanitize_public_payload(
                {key: payload[key] for key in keys if key in payload}
            )
        )

    def _snapshot_selector_candidates(self, snapshot: Any) -> list[Any]:
        """Collect the current/latest Task5 semantic snapshot candidate records
        (components, occurrences, bodies, sketches, features, faces, edges)."""
        candidates: list[Any] = []
        for group in ("components", "occurrences", "bodies", "sketches", "features"):
            candidates.extend(getattr(snapshot, group, ()))
        for group in ("faces", "edges"):
            items = getattr(snapshot, group, None)
            if items:
                candidates.extend(items)
        return candidates

    def _resolve_inspect_selector(
        self, selector: Any, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Resolve an inspect EntitySelector target through the Task5 SelectorEngine
        with EXACT-ONE cardinality and inject the resulting opaque ref / native
        resolution hint. Fails closed with SELECTOR_EMPTY or SELECTOR_AMBIGUOUS
        when exact-one cannot be proven."""
        doc_ref = (
            payload.get("document_ref") or self._revision_tracker.active_document_ref
        )
        if not doc_ref:
            raise FusionCadError(
                ErrorCode.SELECTOR_EMPTY,
                "Inspection selector could not be resolved without a document context",
                details={"document_ref": doc_ref},
            )
        snap = self._snapshot_store.get_latest(doc_ref)
        if snap is None:
            raise FusionCadError(
                ErrorCode.SELECTOR_EMPTY,
                "Inspection selector matched nothing: no current semantic snapshot for the document",
                details={"document_ref": doc_ref},
            )
        candidates = self._snapshot_selector_candidates(snap)
        matched = self._selector_engine.resolve_one(selector, candidates)
        if isinstance(matched, Mapping):
            ref = matched.get("ref")
            kind = matched.get("kind")
            name = matched.get("name")
            comp_path = matched.get("component_path") or ()
        else:
            ref = getattr(matched, "ref", None)
            kind = getattr(matched, "kind", None)
            name = getattr(matched, "name", None)
            comp_path = getattr(matched, "component_path", None) or ()
        if not isinstance(ref, str) or not re.match(ENTITY_REF_PATTERN, ref):
            raise FusionCadError(
                ErrorCode.SELECTOR_EMPTY,
                "Inspection selector resolved a candidate without a usable opaque ref",
                details={"document_ref": doc_ref},
            )
        record = self._ref_registry.get_internal_record(ref, doc_ref)
        if record is None or not record.native_token:
            raise FusionCadError(
                ErrorCode.SELECTOR_EMPTY,
                "Inspection selector resolved a target with no native resolution hint; cannot prove exact resolution",
                details={"document_ref": doc_ref, "ref": ref},
            )
        hint: dict[str, Any] = {
            "ref": ref,
            "kind": kind or "entity",
            "name": name,
            "component_path": list(comp_path) if comp_path else None,
            "native_token": record.native_token,
        }
        if record.geometry_signature:
            hint["geometry_signature"] = dict(record.geometry_signature)
        return hint

    def _resolve_opaque_inspect_ref(
        self, raw: str, doc_ref: str | None
    ) -> InternalEntityRecord | None:
        """Resolve an opaque inspect target ref within the effective document context.

        Task5 document-bounded semantics are preserved:
          - a ref registered to a different document than the effective context
            fails closed with WRONG_DOCUMENT (a foreign native token is never
            injected);
          - an unknown / no-longer-resolvable ref in the effective context fails
            closed with REF_STALE;
          - a ref registered in the effective context returns its record for
            native-hint injection.

        When no effective document context exists (neither a request document_ref
        nor an active document), resolution falls back to the registry's
        any-document lookup solely for backward-compatible single-document
        requests; it never injects a token proven to belong to another document.
        """
        if doc_ref is not None:
            record = self._ref_registry.get_internal_record(raw, doc_ref)
            if record is not None:
                return record
            other = self._ref_registry.get_internal_record(raw)
            if other is not None and other.document_ref != doc_ref:
                raise FusionCadError(
                    ErrorCode.WRONG_DOCUMENT,
                    "Inspection target ref belongs to a different document than the effective document context; refusing to inject a foreign native entity token",
                    details={"ref": raw, "active_document_ref": doc_ref},
                )
            raise FusionCadError(
                ErrorCode.REF_STALE,
                "Inspection target ref is unknown or stale in the effective document context",
                details={"ref": raw, "active_document_ref": doc_ref},
            )
        return self._ref_registry.get_internal_record(raw)

    def _inject_inspect_target_hints(self, payload: dict[str, Any]) -> None:
        """Resolve inspection targets (opaque refs OR EntitySelectors) into native hints.

        Opaque EntityRef targets issued by this service are translated into
        {ref, kind, native_token, name, component_path, geometry_signature} hints
        so the static Fusion script can resolve them exactly via findEntityByToken.
        Resolution is bound to the EFFECTIVE document context (the request
        document_ref, else the active document) so a ref from another document can
        never inject its foreign native token. Cross-document opaque refs fail
        closed with WRONG_DOCUMENT and unknown/stale active-doc refs fail closed
        with REF_STALE.

        EntitySelector (dict) targets are resolved first through the Task5
        SelectorEngine with EXACT-ONE cardinality against the current semantic
        snapshot, then the resulting opaque ref / native hint is injected. The
        selector never falls through to the script's kind/name-only fallback.

        Unregistered opaque refs with no effective document context fall through
        to contextual resolution in the script.
        """
        doc_ref = (
            payload.get("document_ref") or self._revision_tracker.active_document_ref
        )
        for key in ("target", "target_a", "target_b", "face_a", "face_b"):
            raw = payload.get(key)
            if isinstance(raw, str) and re.match(ENTITY_REF_PATTERN, raw):
                record = self._resolve_opaque_inspect_ref(raw, doc_ref)
                if record is None:
                    continue
                payload[key] = {
                    "ref": record.ref,
                    "kind": record.kind,
                    "native_token": record.native_token,
                    "name": record.name,
                    "component_path": list(record.component_path),
                    "geometry_signature": (
                        dict(record.geometry_signature)
                        if record.geometry_signature
                        else None
                    ),
                }
            elif isinstance(raw, Mapping):
                payload[key] = self._resolve_inspect_selector(raw, payload)

    def _inject_metadata_target_hint(self, payload: dict[str, Any]) -> None:
        """Resolve a metadata target into an exact native hint, failing closed.

        Registered opaque refs become {ref, kind, native_token, ...} hints bound
        to the effective document context. Unknown/stale refs, refs registered
        to a different document than the effective context, and refs without a
        native resolution hint fail closed BEFORE dispatch: metadata is never
        silently applied to the document owner while echoing an entity ref.
        Only an absent/None target means explicit document scope.
        """
        raw = payload.get("target")
        if isinstance(raw, Mapping):
            payload["target"] = self._resolve_inspect_selector(raw, payload)
            return
        if isinstance(raw, str) and re.match(ENTITY_REF_PATTERN, raw):
            doc_ref = (
                payload.get("document_ref")
                or self._revision_tracker.active_document_ref
            )
            record = self._resolve_opaque_inspect_ref(raw, doc_ref)
            if record is None:
                raise FusionCadError(
                    ErrorCode.REF_STALE,
                    "Metadata target ref is unknown or stale in the effective document context; refusing to fall back to the document owner",
                    details={"ref": raw, "active_document_ref": doc_ref},
                )
            if not record.native_token:
                raise FusionCadError(
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                    "Metadata target ref has no native resolution hint; metadata cannot be applied to an exactly resolved entity, failing closed",
                    details={
                        "ref": record.ref,
                        "active_document_ref": record.document_ref,
                    },
                )
            hint: dict[str, Any] = {
                "ref": record.ref,
                "kind": record.kind,
                "name": record.name,
                "native_token": record.native_token,
                "component_path": list(record.component_path),
            }
            if record.geometry_signature:
                hint["geometry_signature"] = dict(record.geometry_signature)
            payload["target"] = hint

    def _prepare_metadata_payload(
        self,
        payload: dict[str, Any],
        op: str,
        *,
        operation_id: str | None = None,
    ) -> None:
        """Task 10 payload preparation for reserved-namespace metadata operations.

        Mutations get the one-command plan (explicit writes/removals plus the
        provenance write) executed by the same script execution as any geometry
        change; reads are normalized to the reserved namespace. Foreign groups
        and unknown/stale/cross-document entity targets fail closed before any
        dispatch. The provenance record carries the durable command operation id
        (shared with the desktop operation journal) and the truthful
        post-mutation created_revision resolved from the RevisionTracker.
        """
        if op == "set" and "name" not in payload:
            # fusion_style visibility set: not a metadata operation
            return
        if op in _METADATA_MUTATION_OPS:
            doc_ref = (
                payload.get("document_ref")
                or self._revision_tracker.active_document_ref
            )
            created_revision = (
                self._revision_tracker.next_revision(doc_ref) if doc_ref else None
            )
            apply_metadata_mutation_plan(
                payload, operation_id=operation_id, created_revision=created_revision
            )
        elif op in _METADATA_READ_OPS:
            payload["group"] = assert_reserved_metadata_group(payload.get("group"))
        else:
            return
        if "target" in payload:
            self._inject_metadata_target_hint(payload)

    def _finalize_metadata_execution(
        self,
        cad_result: CadResult,
        *,
        op: str,
        payload: dict[str, Any],
        target_doc: str | None,
    ) -> CadResult:
        """Normalize Task 10 metadata results without exposing native owner tokens."""
        data = dict(cad_result.data) if isinstance(cad_result.data, Mapping) else {}
        if op == "set" and "name" not in payload:
            # fusion_style visibility set: not a metadata operation
            return cad_result
        if op in _METADATA_MUTATION_OPS:
            if data.get("applied") is not True:
                raise FusionCadError(
                    ErrorCode.FUSION_API_ERROR,
                    "Metadata mutation completed without applied=True; failing closed",
                    details={"operation": op},
                )
            provenance = data.get("provenance")
            if not isinstance(provenance, Mapping):
                raise FusionCadError(
                    ErrorCode.FUSION_API_ERROR,
                    "Metadata mutation result lacks the transactional provenance record; failing closed",
                    details={"operation": op},
                )
            summary = f"Metadata {op} applied with provenance"
        else:
            if op == "provenance":
                records = data.get("records") or []
                first = records[0] if records else None
                value = first.get("value") if isinstance(first, Mapping) else None
                data["provenance"] = (
                    parse_provenance_attribute(value).model_dump(
                        mode="json", exclude_none=True
                    )
                    if value is not None
                    else None
                )
                data.pop("records", None)
            if op == "query":
                cleaned: list[Any] = []
                for idx, cand in enumerate(data.get("candidates") or []):
                    if not isinstance(cand, Mapping):
                        continue
                    d = dict(cand)
                    native_token = (
                        d.get("entityToken") or d.get("native_token") or d.get("token")
                    )
                    d.pop("entityToken", None)
                    d.pop("native_token", None)
                    d.pop("token", None)
                    if native_token and target_doc:
                        issued = self._ref_registry.issue(
                            document_ref=target_doc,
                            kind=str(d.get("kind") or "entity"),
                            name=d.get("name"),
                            native_token=str(native_token),
                        )
                        d["ref"] = issued.ref
                    else:
                        d["ref"] = d.get("ref") or f"ent_meta_{idx}"
                    cleaned.append(d)
                data["candidates"] = cleaned
                data["candidate_count"] = len(cleaned)
            summary = f"Metadata {op} read from persisted model attributes"
        return cad_result.model_copy(
            update={
                "data": ImmutableMapping(sanitize_public_payload(data)),
                "summary": summary,
            }
        )

    def _prepare_style_payload(
        self, payload: dict[str, Any], op: str, operation_id: str | None
    ) -> None:
        """Bind Task 11 requests to opaque refs and same-command provenance."""
        if "target" in payload:
            self._inject_metadata_target_hint(payload)
        if op == "restore":
            doc_ref = payload.get("document_ref") or self._revision_tracker.active_document_ref
            state = self._visibility_restore_states.get(str(doc_ref))
            if state is None:
                raise FusionCadError(
                    ErrorCode.REF_STALE,
                    "No service-owned visibility state is available for this document",
                )
            payload["visibility_state"] = state
        if not op.startswith("text_") or op == "text_read":
            return
        logical_ref = payload.get("text_ref")
        if op == "text_create":
            logical_ref = f"text_{uuid.uuid4().hex[:16]}"
            payload["logical_object_ref"] = logical_ref
        else:
            payload["logical_object_ref"] = logical_ref
        doc_ref = (
            payload.get("document_ref") or self._revision_tracker.active_document_ref
        )
        apply_geometry_provenance_plan(
            payload,
            operation=op,
            creator_operation=f"fusion_style:{op}",
            operation_id=operation_id,
            created_revision=(
                self._revision_tracker.next_revision(doc_ref) if doc_ref else None
            ),
        )
        payload["style_semantic_contract"] = "task11.v1"

    def _finalize_style_execution(
        self, cad_result: CadResult, *, op: str, payload: dict[str, Any]
    ) -> CadResult:
        """Validate semantic Task 11 evidence and strip adapter-private state."""
        data = dict(cad_result.data) if isinstance(cad_result.data, Mapping) else {}
        public: dict[str, Any] = {}
        if op.startswith("text_"):
            raw_lineage = data.get("lineage")
            if raw_lineage is None and op != "text_delete":
                raise FusionCadError(
                    ErrorCode.FUSION_API_ERROR,
                    "Logical text operation completed without verified lineage",
                    details={"operation": op},
                )
            if raw_lineage is not None:
                try:
                    lineage = normalize_text_lineage(raw_lineage)
                except (ValidationError, ValueError, TypeError) as exc:
                    raise FusionCadError(
                        ErrorCode.FUSION_API_ERROR,
                        "Logical text operation returned invalid lineage",
                        details={"operation": op},
                    ) from exc
                expected_ref = payload.get("logical_object_ref") or payload.get(
                    "text_ref"
                )
                if expected_ref and lineage["logical_ref"] != expected_ref:
                    raise FusionCadError(
                        ErrorCode.FUSION_API_ERROR,
                        "Logical text adapter returned lineage for a different TextRef",
                        details={"operation": op},
                    )
                if (
                    op in {"text_update", "text_read", "text_extrude", "text_cut"}
                    and lineage["is_current"] is not True
                ):
                    raise FusionCadError(
                        ErrorCode.FUSION_API_ERROR,
                        "Logical text operation did not return the current generation",
                        details={"operation": op},
                    )
                public["lineage"] = lineage
            if op == "text_update":
                replacement = data.get("replacement_evidence")
                valid_replacement = (
                    isinstance(replacement, Mapping)
                    and replacement.get("logical_ref") == payload.get("text_ref")
                    and isinstance(replacement.get("previous_generation"), int)
                    and isinstance(replacement.get("current_generation"), int)
                    and replacement.get("current_generation")
                    > replacement.get("previous_generation")
                    and replacement.get("previous_generation_is_current") is False
                    and replacement.get("current_generation_count") == 1
                    and replacement.get("replacement_or_rebind_verified") is True
                    and replacement.get("unrelated_legacy_preserved") is True
                )
                if not valid_replacement:
                    raise FusionCadError(
                        ErrorCode.FUSION_API_ERROR,
                        "Logical text update lacks verified single-current-generation replacement evidence",
                        details={"operation": op},
                    )
                public["replacement_evidence"] = {
                    key: replacement[key]
                    for key in (
                        "logical_ref",
                        "previous_generation",
                        "current_generation",
                        "previous_generation_is_current",
                        "current_generation_count",
                        "replacement_or_rebind_verified",
                        "unrelated_legacy_preserved",
                    )
                }
            if op != "text_read":
                expected_raw = payload.get("provenance")
                try:
                    expected = ProvenanceRecord.model_validate(expected_raw)
                    returned = ProvenanceRecord.model_validate(data.get("provenance"))
                    persisted = ProvenanceRecord.model_validate(
                        data.get("persisted_provenance")
                    )
                except (ValidationError, TypeError, ValueError) as exc:
                    raise FusionCadError(
                        ErrorCode.FUSION_API_ERROR,
                        "Logical text mutation lacks valid persisted same-command provenance",
                        details={"operation": op},
                    ) from exc
                if (
                    data.get("same_operation_provenance") is not True
                    or returned != expected
                    or persisted != expected
                ):
                    raise FusionCadError(
                        ErrorCode.FUSION_API_ERROR,
                        "Logical text provenance does not match the service-prepared same-command record",
                        details={"operation": op},
                    )
                public["provenance"] = expected.model_dump(
                    mode="json", exclude_none=True
                )
                public["same_operation_provenance"] = True
        else:
            visibility = data.get("visibility")
            if not isinstance(visibility, Mapping):
                raise FusionCadError(
                    ErrorCode.FUSION_API_ERROR,
                    "Visibility operation lacks typed semantic visibility evidence",
                    details={"operation": op},
                )
            target = payload.get("target")
            expected_target = (
                target.get("ref") if isinstance(target, Mapping) else target
            )
            requested = (
                payload.get("visible")
                if op == "set"
                else op in {"show", "show_only", "isolate"}
            )
            valid_visibility = (
                visibility.get("operation") == op
                and isinstance(visibility.get("local_visible"), bool)
                and isinstance(visibility.get("parent_visible"), bool)
                and isinstance(visibility.get("effective_visible"), bool)
                and visibility.get("effective_visible")
                == (
                    visibility.get("local_visible") and visibility.get("parent_visible")
                )
            )
            if op != "restore":
                valid_visibility = (
                    valid_visibility
                    and visibility.get("target_ref") == expected_target
                    and re.fullmatch(
                        ENTITY_REF_PATTERN, str(visibility.get("target_ref") or "")
                    )
                    is not None
                    and visibility.get("requested_visible") is requested
                    and visibility.get("local_visible") is requested
                )
            if not valid_visibility:
                raise FusionCadError(
                    ErrorCode.FUSION_API_ERROR,
                    "Visibility adapter evidence does not prove the requested local and effective state",
                    details={"operation": op},
                )
            public["visibility"] = {
                key: visibility[key]
                for key in (
                    "operation",
                    "target_ref",
                    "state_ref",
                    "requested_visible",
                    "local_visible",
                    "parent_visible",
                    "effective_visible",
                )
                if key in visibility
            }
            if op in {"show_only", "isolate", "restore"}:
                scope = data.get("scope_evidence")
                scope_operation = (
                    scope.get("operation") if isinstance(scope, Mapping) else None
                )
                captured = scope.get("captured") if isinstance(scope, Mapping) else None
                changed_refs = (
                    scope.get("changed_refs") if isinstance(scope, Mapping) else None
                )
                restored = scope.get("restored") if isinstance(scope, Mapping) else None

                def _visibility_states(value: Any) -> dict[str, bool] | None:
                    if not isinstance(value, (list, tuple)):
                        return None
                    states: dict[str, bool] = {}
                    for entry in value:
                        if not isinstance(entry, Mapping):
                            return None
                        ref = entry.get("ref")
                        local = entry.get("local_visible")
                        if (
                            not isinstance(ref, str)
                            or re.fullmatch(ENTITY_REF_PATTERN, ref) is None
                            or ref in states
                            or not isinstance(local, bool)
                        ):
                            return None
                        states[ref] = local
                    return states

                captured_states = _visibility_states(captured)
                changed_set = (
                    set(changed_refs)
                    if isinstance(changed_refs, (list, tuple))
                    and all(
                        isinstance(ref, str) and re.fullmatch(ENTITY_REF_PATTERN, ref)
                        for ref in changed_refs
                    )
                    else None
                )
                valid_scope = (
                    isinstance(scope, Mapping)
                    and scope.get("scope") == "own_mutation"
                    and scope_operation in {"show_only", "isolate"}
                    and captured_states is not None
                    and changed_set == set(captured_states)
                    and len(changed_refs) == len(changed_set)
                )
                if op in {"show_only", "isolate"}:
                    valid_scope = (
                        valid_scope
                        and scope_operation == op
                        and scope.get("target_ref") == expected_target
                    )
                else:
                    restored_states = _visibility_states(restored)
                    valid_scope = (
                        valid_scope
                        and restored_states == captured_states
                        and isinstance(scope.get("state_ref"), str)
                        and scope.get("state_ref") == visibility.get("state_ref")
                    )
                if not valid_scope:
                    raise FusionCadError(
                        ErrorCode.CAPABILITY_UNAVAILABLE,
                        "Scoped visibility operation lacks own-mutation capture evidence",
                        details={"operation": op, "applied": False},
                    )
                if op == "restore" and data.get("restoration_verified") is not True:
                    raise FusionCadError(
                        ErrorCode.CAPABILITY_UNAVAILABLE,
                        "Visibility restore did not prove exact restoration",
                        details={"operation": op, "applied": False},
                    )
                public_scope = {
                    "scope": "own_mutation",
                    "operation": scope_operation,
                    "captured": [
                        {"ref": entry["ref"], "local_visible": entry["local_visible"]}
                        for entry in captured
                    ],
                    "changed_refs": list(changed_refs),
                }
                for key in ("target_ref", "state_ref"):
                    if key in scope:
                        public_scope[key] = scope[key]
                if op == "restore":
                    public_scope["restored"] = [
                        {"ref": entry["ref"], "local_visible": entry["local_visible"]}
                        for entry in restored
                    ]
                public["scope_evidence"] = public_scope
                if op == "restore":
                    public["restoration_verified"] = True
                    doc_ref = payload.get("document_ref") or self._revision_tracker.active_document_ref
                    self._visibility_restore_states.pop(str(doc_ref), None)
                else:
                    if not hasattr(self, "_visibility_restore_states"):
                        return cad_result.model_copy(
                            update={"data": ImmutableMapping(sanitize_public_payload(public))}
                        )
                    private_entries = []
                    for entry in captured:
                        if not isinstance(entry, Mapping) or not isinstance(entry.get("native_token"), str):
                            raise FusionCadError(
                                ErrorCode.CAPABILITY_UNAVAILABLE,
                                "Scoped visibility capture lacks exact native restore identity",
                                details={"operation": op, "applied": False},
                            )
                        private_entries.append(
                            {"ref": entry["ref"], "native_token": entry["native_token"], "local_visible": entry["local_visible"]}
                        )
                    doc_ref = payload.get("document_ref") or self._revision_tracker.active_document_ref
                    self._visibility_restore_states[str(doc_ref)] = {
                        "scope": "own_mutation", "operation": op,
                        "target_ref": expected_target, "state_ref": scope.get("state_ref"),
                        "captured": private_entries, "changed_refs": list(changed_refs),
                    }
        return cad_result.model_copy(
            update={
                "data": ImmutableMapping(sanitize_public_payload(public)),
                "summary": f"Fusion style {op} completed with verified semantic state",
            }
        )

    def assert_fresh_for_mutation(
        self,
        target: Any = None,
        expected_revision: str | None = None,
        *,
        document_ref: str | None = None,
        node_id: str | None = None,
    ) -> RevisionRecord:
        """Assert that the model revision is fresh for mutation (Bridge precheck optimization)."""
        doc_ref = document_ref
        exp_rev = expected_revision
        if isinstance(target, dict):
            doc_ref = doc_ref or target.get("document_ref") or target.get("document")
            if exp_rev is None:
                exp_rev = target.get("expected_revision")
        elif isinstance(target, BaseModel):
            doc_ref = doc_ref or getattr(target, "document_ref", None)
            if exp_rev is None:
                exp_rev = getattr(target, "expected_revision", None)
        elif isinstance(target, str):
            if target.startswith("doc_"):
                doc_ref = target
            elif exp_rev is None:
                exp_rev = target

        if doc_ref is None:
            doc_ref = self._revision_tracker.active_document_ref
        if not doc_ref:
            raise FusionCadError(
                ErrorCode.NO_ACTIVE_DESIGN,
                "No active design or document_ref provided for mutation freshness check",
            )

        return self._revision_tracker.assert_expected(doc_ref, exp_rev)

    def get_node_capabilities(self, node_id: str) -> CapabilityMatrix | None:
        cached = self._node_capabilities.get(node_id)
        if cached is None:
            return None
        if not isinstance(cached, _CachedNodeCapabilities):
            cached = _CachedNodeCapabilities(matrix=cached, session_generation=1)
            self._node_capabilities[node_id] = cached
        try:
            current_gen = self._desktop_nodes.get_session_generation(node_id)
        except (BridgeError, AttributeError):
            self._node_capabilities.pop(node_id, None)
            return None
        if current_gen != cached.session_generation:
            self._node_capabilities.pop(node_id, None)
            return None
        return cached.matrix

    def set_node_capabilities(
        self,
        node_id: str,
        matrix: CapabilityMatrix,
        generation: int | None = None,
    ) -> None:
        try:
            current_gen = self._desktop_nodes.get_session_generation(node_id)
        except (BridgeError, AttributeError):
            current_gen = 1

        if generation is not None and generation != current_gen:
            self._node_capabilities.pop(node_id, None)
            return

        target_gen = generation if generation is not None else current_gen
        self._node_capabilities[node_id] = _CachedNodeCapabilities(
            matrix=matrix, session_generation=target_gen
        )

    def invalidate_node_capabilities(self, node_id: str | None = None) -> None:
        if node_id is None:
            self._node_capabilities.clear()
        else:
            self._node_capabilities.pop(node_id, None)

    @staticmethod
    def is_domain_summary(summary: str | None) -> bool:
        if not isinstance(summary, str):
            return False
        return any(
            summary.startswith(f"{prefix}:")
            for prefix in (
                "read",
                "inspect",
                "view",
                "mutate",
                "validate",
                "transaction",
            )
        )

    @classmethod
    def _is_error_payload(cls, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return True
        if "isError" in payload and payload["isError"] is not False:
            return True
        if payload.get("status") in ("failed", "error") or "error" in payload:
            return True
        if isinstance(payload.get("content"), list):
            for block in payload["content"]:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, dict) and (
                            ("isError" in parsed and parsed["isError"] is not False)
                            or parsed.get("status") in ("failed", "error")
                            or "error" in parsed
                        ):
                            return True
                    except (ValueError, TypeError):
                        pass
        return False

    @classmethod
    def _resolve_safe_error_message(cls, err_code: ErrorCode, raw_details: Any) -> str:
        if (
            err_code == ErrorCode.NO_ACTIVE_DESIGN
            and isinstance(raw_details, Mapping)
            and "name" in raw_details
        ):
            return "Document lacks stable runtime identity"
        return get_safe_error_message(err_code)

    @classmethod
    def _extract_error_info(
        cls, payload: dict[str, Any]
    ) -> tuple[ErrorCode, str, dict[str, Any]]:
        err_code = ErrorCode.FUSION_API_ERROR
        raw_details: Any = None

        if isinstance(payload.get("content"), list):
            for block in payload["content"]:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, dict) and (
                            parsed.get("status") in ("failed", "error")
                            or "error" in parsed
                            or ("isError" in parsed and parsed["isError"] is not False)
                        ):
                            err = (
                                parsed.get("error")
                                if isinstance(parsed.get("error"), dict)
                                else {}
                            )
                            code_str = err.get("code") or parsed.get("code")
                            if code_str:
                                try:
                                    err_code = ErrorCode(str(code_str))
                                except ValueError:
                                    err_code = ErrorCode.FUSION_API_ERROR
                            raw_details = (
                                err.get("details") or parsed.get("details") or parsed
                            )
                            return (
                                err_code,
                                cls._resolve_safe_error_message(err_code, raw_details),
                                filter_trusted_diagnostics(raw_details),
                            )
                    except (ValueError, TypeError):
                        pass

        if "error" in payload:
            err = payload["error"]
            if isinstance(err, dict):
                code_str = err.get("code") or payload.get("code")
                if code_str:
                    try:
                        err_code = ErrorCode(str(code_str))
                    except ValueError:
                        err_code = ErrorCode.FUSION_API_ERROR
                raw_details = err.get("details") or payload.get("details")
            elif isinstance(err, str):
                pass
            return (
                err_code,
                cls._resolve_safe_error_message(err_code, raw_details),
                filter_trusted_diagnostics(raw_details),
            )

        code_str = payload.get("code")
        if code_str:
            try:
                err_code = ErrorCode(str(code_str))
            except ValueError:
                err_code = ErrorCode.FUSION_API_ERROR

        raw_details = payload.get("details")
        return (
            err_code,
            cls._resolve_safe_error_message(err_code, raw_details),
            filter_trusted_diagnostics(raw_details),
        )

    @classmethod
    def decode_domain_result(cls, raw_result: Any) -> CadResult:
        """Decode and validate a domain result against fusion.cad/v1 CadResult schema.

        Fails closed on malformed JSON, isError=True, non-bool isError, failed/error status,
        missing or incorrect api_version, invalid CadResult schema, or non-dict structures.
        """
        if not isinstance(raw_result, dict):
            raise FusionCadError(
                ErrorCode.FUSION_API_ERROR,
                "Unexpected non-dict result type from desktop node",
                details={"parsed_type": trusted_detail(type(raw_result).__name__)},
            )

        if "isError" in raw_result and raw_result["isError"] is not False:
            err_code, err_msg, err_details = cls._extract_error_info(raw_result)
            raise FusionCadError(err_code, err_msg, details=err_details)

        if "content" in raw_result:
            content_blocks = raw_result.get("content")
            if not isinstance(content_blocks, list) or len(content_blocks) == 0:
                raise FusionCadError(
                    ErrorCode.FUSION_API_ERROR,
                    "Native Fusion CAD execution returned empty content blocks",
                    details={"content_type": "blocks"},
                )

            for block in content_blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text = block.get("text", "")
                    if not isinstance(text, str) or not text.strip():
                        raise FusionCadError(
                            ErrorCode.FUSION_API_ERROR,
                            "Empty text content in native Fusion execution output",
                            details={"content_type": "text"},
                        )
                    malformed_err: FusionCadError | None = None
                    try:
                        parsed = json.loads(text)
                    except (ValueError, TypeError):
                        malformed_err = FusionCadError(
                            ErrorCode.FUSION_API_ERROR,
                            "Malformed non-JSON output from native Fusion script",
                            details={"content_type": "text"},
                        )
                    if malformed_err is not None:
                        raise malformed_err

                    if not isinstance(parsed, dict):
                        raise FusionCadError(
                            ErrorCode.FUSION_API_ERROR,
                            "Invalid domain output type: expected JSON object",
                            details={
                                "parsed_type": trusted_detail(type(parsed).__name__)
                            },
                        )

                    if (
                        ("isError" in parsed and parsed["isError"] is not False)
                        or parsed.get("status") in ("failed", "error")
                        or "error" in parsed
                    ):
                        err_code, err_msg, err_details = cls._extract_error_info(parsed)
                        raise FusionCadError(err_code, err_msg, details=err_details)

                    if parsed.get("api_version") != "fusion.cad/v1":
                        raise FusionCadError(
                            ErrorCode.FUSION_API_ERROR,
                            "Unrecognized domain output from native Fusion script: missing or invalid api_version 'fusion.cad/v1'",
                            details={"content_type": "json"},
                        )

                    candidate = dict(parsed)
                    candidate.pop("isError", None)
                    val_err: FusionCadError | None = None
                    try:
                        return CadResult.model_validate(candidate)
                    except ValidationError as exc:
                        val_err = FusionCadError(
                            ErrorCode.FUSION_API_ERROR,
                            "Invalid fusion.cad/v1 response schema",
                            details={
                                "validation_errors": sanitize_validation_errors(
                                    exc.errors()
                                )
                            },
                        )
                    if val_err is not None:
                        raise val_err

            raise FusionCadError(
                ErrorCode.FUSION_API_ERROR,
                "No valid CAD text output found in native execution content",
                details={"content_type": "blocks"},
            )

        if raw_result.get("status") in ("failed", "error") or "error" in raw_result:
            err_code, err_msg, err_details = cls._extract_error_info(raw_result)
            raise FusionCadError(err_code, err_msg, details=err_details)

        if raw_result.get("api_version") == "fusion.cad/v1":
            candidate = dict(raw_result)
            candidate.pop("isError", None)
            fallback_val_err: FusionCadError | None = None
            try:
                return CadResult.model_validate(candidate)
            except ValidationError as exc:
                fallback_val_err = FusionCadError(
                    ErrorCode.FUSION_API_ERROR,
                    "Invalid fusion.cad/v1 response schema",
                    details={
                        "validation_errors": sanitize_validation_errors(exc.errors())
                    },
                )
            if fallback_val_err is not None:
                raise fallback_val_err

        raise FusionCadError(
            ErrorCode.FUSION_API_ERROR,
            "Unrecognized domain output format from native Fusion script: missing or invalid api_version 'fusion.cad/v1'",
            details={"content_type": "unknown"},
        )

    def _prepare_pick_payload(self, payload: dict[str, Any], node_id: str) -> None:
        view_ref = payload.get("view_ref")
        if not isinstance(view_ref, str) or not view_ref:
            raise FusionCadError(ErrorCode.INVALID_ARGUMENT, "pick requires a bound view_ref")
        record = self.assert_view_fresh(
            view_ref,
            node_id,
            payload.get("document_ref") if isinstance(payload.get("document_ref"), str) else None,
        )
        expected_fp = self._revision_tracker.get_fingerprint(
            record.document_ref, record.model_revision
        )
        if not isinstance(expected_fp, str) or not expected_fp.strip():
            raise FusionCadError(
                ErrorCode.VIEW_STALE,
                "Bound screenshot model revision no longer has an authoritative fingerprint",
                details={"view_ref": view_ref, "document_ref": record.document_ref},
            )
        camera = record.camera
        payload["document_ref"] = record.document_ref
        payload["_pick_expected"] = {
            "document_ref": record.document_ref,
            "model_fingerprint": expected_fp.strip(),
            "camera": {
                "eye": list(camera.eye),
                "target": list(camera.target),
                "up": list(camera.up),
                "projection": camera.projection,
                "fov_deg": camera.fov_deg,
                "ortho_extent_width_cm": camera.ortho_extent_width_cm,
                "ortho_extent_height_cm": camera.ortho_extent_height_cm,
                "viewport_width": camera.viewport_width,
                "viewport_height": camera.viewport_height,
            },
            "visibility": dict(record.visibility_state),
            "section": dict(record.section_state),
            "image_width": record.viewport_width,
            "image_height": record.viewport_height,
        }

    def _finalize_pick_execution(
        self, cad_result: CadResult, *, payload: dict[str, Any]
    ) -> CadResult:
        data = dict(cad_result.data) if isinstance(cad_result.data, Mapping) else {}
        raw_candidates = data.get("candidates")
        if not isinstance(raw_candidates, (list, tuple)):
            raise FusionCadError(
                ErrorCode.FUSION_API_ERROR,
                "Screen-space pick result lacks an ordered candidate list",
            )
        raw_hit = data.get("hit")
        if not isinstance(raw_hit, bool):
            raise FusionCadError(
                ErrorCode.FUSION_API_ERROR,
                "Screen-space pick result lacks boolean hit state",
            )
        if data.get("candidate_count") not in (None, len(raw_candidates)):
            raise FusionCadError(
                ErrorCode.FUSION_API_ERROR,
                "Screen-space pick candidate_count does not match candidate list",
            )
        expected = payload.get("_pick_expected")
        doc_ref = expected.get("document_ref") if isinstance(expected, Mapping) else None
        if not isinstance(doc_ref, str) or not doc_ref:
            raise FusionCadError(ErrorCode.VIEW_STALE, "Pick result lost bound document authority")

        public_candidates: list[dict[str, Any]] = []
        allowed_kinds = {"body", "face", "edge", "vertex"}
        for idx, raw in enumerate(raw_candidates):
            if not isinstance(raw, Mapping):
                raise FusionCadError(ErrorCode.FUSION_API_ERROR, "Pick candidate is not a mapping")
            kind = str(raw.get("kind") or "").lower()
            if kind not in allowed_kinds:
                raise FusionCadError(
                    ErrorCode.FUSION_API_ERROR,
                    "Pick candidate returned an unsupported entity kind",
                    details={"candidate_index": idx},
                )
            native_token = raw.get("native_token") or raw.get("entityToken") or raw.get("token")
            if not isinstance(native_token, str) or not native_token:
                raise FusionCadError(
                    ErrorCode.FUSION_API_ERROR,
                    "Pick candidate lacks stable native identity",
                    details={"candidate_index": idx},
                )
            world_point = raw.get("world_point")
            if not isinstance(world_point, Mapping):
                raise FusionCadError(
                    ErrorCode.FUSION_API_ERROR,
                    "Pick candidate lacks a world hit point",
                    details={"candidate_index": idx},
                )
            try:
                coords = [float(world_point[k]) for k in ("x", "y", "z")]
            except (KeyError, TypeError, ValueError):
                raise FusionCadError(
                    ErrorCode.FUSION_API_ERROR,
                    "Pick candidate world hit point is invalid",
                    details={"candidate_index": idx},
                ) from None
            if not all(math.isfinite(v) for v in coords):
                raise FusionCadError(
                    ErrorCode.FUSION_API_ERROR,
                    "Pick candidate world hit point is non-finite",
                    details={"candidate_index": idx},
                )
            try:
                distance = float(raw.get("distance"))
            except (TypeError, ValueError):
                raise FusionCadError(
                    ErrorCode.FUSION_API_ERROR,
                    "Pick candidate distance is invalid",
                    details={"candidate_index": idx},
                ) from None
            if not math.isfinite(distance) or distance < 0.0:
                raise FusionCadError(
                    ErrorCode.FUSION_API_ERROR,
                    "Pick candidate distance is invalid",
                    details={"candidate_index": idx},
                )
            issued = self._ref_registry.issue(
                document_ref=doc_ref,
                kind=kind,
                name=str(raw.get("name")) if raw.get("name") else None,
                native_token=native_token,
            )
            public_candidates.append(
                {
                    "ref": issued.ref,
                    "kind": kind,
                    "depth": idx,
                    "world_point": {
                        "x": coords[0],
                        "y": coords[1],
                        "z": coords[2],
                        "frame": {"space": "world", "ref": None},
                    },
                    "distance": distance,
                }
            )
        if raw_hit != bool(public_candidates):
            raise FusionCadError(
                ErrorCode.FUSION_API_ERROR,
                "Screen-space pick hit state contradicts candidate list",
            )
        return cad_result.model_copy(
            update={
                "data": ImmutableMapping(
                    {
                        "hit": raw_hit,
                        "candidate_count": len(public_candidates),
                        "candidates": tuple(public_candidates),
                    }
                ),
                "summary": "Screen-space pick resolved to ordered opaque entity refs",
            }
        )

    def _finalize_view_operation(
        self,
        cad_result: CadResult,
        *,
        op: str,
        payload: dict[str, Any],
        node_id: str | None,
    ) -> CadResult:
        """Normalize a view operation result into canonical camera/visibility/section
        state and bind immutable screenshot ViewRefs.

        Camera operations update the node's current view context (invalidating
        old ViewRefs) and never touch document save or model revision. Screenshots
        bind an immutable ViewRef keyed to the current model revision; missing
        model revision fails closed rather than guessing.
        """
        data = dict(cad_result.data) if isinstance(cad_result.data, Mapping) else {}
        raw_camera = data.get("camera")
        if not isinstance(raw_camera, Mapping):
            raise FusionCadError(
                ErrorCode.PRECONDITION_FAILED,
                "View operation result is missing deterministic camera context; failing closed for exact view freshness",
                details={"operation": op},
            )
        raw_viewport = data.get("viewport")
        if isinstance(raw_viewport, Mapping):
            raw_camera = dict(raw_camera)
            raw_camera.setdefault("viewport_width", raw_viewport.get("width"))
            raw_camera.setdefault("viewport_height", raw_viewport.get("height"))
        camera = normalize_camera_context(raw_camera)
        visibility_state = canonicalize_visibility_payload(data.get("visibility"))
        section_state = canonicalize_section_payload(data.get("section"))

        doc_ref = (
            (cad_result.document.document_ref if cad_result.document else None)
            or payload.get("document_ref")
            or self._revision_tracker.active_document_ref
        )
        if not doc_ref:
            raise FusionCadError(
                ErrorCode.NO_ACTIVE_DESIGN,
                "View operation requires an active document context; failing closed",
                details={"operation": op},
            )
        if not node_id:
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                "View operation requires a desktop node context",
                details={"operation": op},
            )

        current = self._view_store.observe_camera(
            node_id, doc_ref, camera, visibility_state, section_state
        )

        if op == "screenshot":
            rec = self._revision_tracker.current(doc_ref)
            if rec is None:
                raise FusionCadError(
                    ErrorCode.NO_ACTIVE_DESIGN,
                    "Screenshot requires an observed model revision (capture a semantic read first); failing closed so the view can bind exact model freshness",
                    details={"document_ref": doc_ref},
                )
            view_ref = f"view_{uuid.uuid4().hex[:12]}"
            image_uri = f"resource://views/{view_ref}/image"
            record = self._view_store.bind(
                view_ref=view_ref,
                document_ref=doc_ref,
                model_revision=rec.revision,
                camera=camera,
                visibility_state=visibility_state,
                section_state=section_state,
                image=image_uri,
                width=data.get("width") or camera.viewport_width,
                height=data.get("height") or camera.viewport_height,
            )
            view_meta = {
                "view_ref": record.view_ref,
                "model_revision": record.model_revision,
                "camera_revision": record.camera_revision,
                "visibility_revision": record.visibility_revision,
                "width": record.viewport_width,
                "height": record.viewport_height,
                "image": record.image,
            }
            artifacts: list[Any] = []
            screenshot_b64 = data.get("screenshot_b64") or data.get("image_b64")
            if isinstance(screenshot_b64, str) and screenshot_b64:
                artifacts.append(
                    ImmutableMapping(
                        {
                            "type": "image",
                            "mime_type": "image/png",
                            "encoding": "base64",
                            "file_name": "fusion-cad-screenshot.png",
                            "data": screenshot_b64,
                        }
                    )
                )
            return cad_result.model_copy(
                update={
                    "data": ImmutableMapping(view_meta),
                    "artifacts": tuple(artifacts),
                    "document": DocumentState(
                        document_ref=doc_ref,
                        model_revision=record.model_revision,
                        name=cad_result.document.name if cad_result.document else None,
                        units="mm",
                    ),
                    "summary": f"Screenshot bound to immutable view {record.view_ref}",
                }
            )

        current_rec = self._revision_tracker.current(doc_ref)
        read_payload = {
            "camera": {
                "eye": list(camera.eye),
                "target": list(camera.target),
                "up": list(camera.up),
                "projection": camera.projection,
                "fov_deg": camera.fov_deg,
                "ortho_extent_width_cm": camera.ortho_extent_width_cm,
                "ortho_extent_height_cm": camera.ortho_extent_height_cm,
            },
            "viewport": {
                "width": camera.viewport_width,
                "height": camera.viewport_height,
            },
            "camera_revision": current.camera_revision,
            "visibility_revision": current.visibility_revision,
            "section_revision": current.section_revision,
            "visibility": sanitize_public_payload(visibility_state.get("entries", [])),
            "section": dict(section_state),
        }
        update: dict[str, Any] = {
            "data": ImmutableMapping(read_payload),
            "summary": f"View operation {op} captured camera context",
        }
        if current_rec is not None:
            update["document"] = DocumentState(
                document_ref=doc_ref,
                model_revision=current_rec.revision,
                name=cad_result.document.name if cad_result.document else None,
                units="mm",
            )
        return cad_result.model_copy(update=update)

    def _bind_screenshot_image_uri(self, external_ref: dict[str, Any]) -> None:
        """Bind the pending screenshot ViewRef image to the real emitted image URI.

        DesktopNodeService.external_result generates the authoritative image
        ResourceLink URI in metadata.resources[*].uri after store_external_result.
        The ViewRef's fabricated resource://views/... placeholder is promoted to
        that real URI exactly once, and the exported/model-visible JSON is
        rewritten so data.image equals it (base64 was already removed from the
        stored JSON by sanitize_binary store-time extraction).
        """
        reference = (
            external_ref.get("external_result")
            if isinstance(external_ref, dict) and "external_result" in external_ref
            else external_ref
        )
        if not isinstance(reference, dict):
            raise FusionCadError(
                ErrorCode.INTERNAL_ERROR,
                "Screenshot externalization returned no usable result reference",
            )
        full, metadata = self._desktop_nodes.external_result(reference)
        resources = metadata.get("resources") or []
        image_resource: dict[str, Any] | None = None
        for res in resources:
            if (
                isinstance(res, dict)
                and isinstance(res.get("uri"), str)
                and str(res.get("mime_type", "")).startswith("image/")
            ):
                image_resource = res
                break
        if image_resource is None:
            raise FusionCadError(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "Screenshot produced no external image resource URI; the immutable ViewRef image cannot bind to a fabricated placeholder",
                details={
                    "node_id": trusted_detail(str(external_ref.get("result_id", "")))
                },
            )
        image_uri = image_resource.get("uri")
        if not isinstance(image_uri, str) or not image_uri.strip():
            raise FusionCadError(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "Screenshot external image resource has no usable URI; the immutable ViewRef image cannot bind to a fabricated placeholder",
            )
        data = full.get("data") if isinstance(full, dict) else None
        if not isinstance(data, dict):
            raise FusionCadError(
                ErrorCode.INTERNAL_ERROR,
                "Screenshot external result payload is missing data",
            )
        view_ref = data.get("view_ref")
        if not isinstance(view_ref, str) or not view_ref:
            raise FusionCadError(
                ErrorCode.INTERNAL_ERROR,
                "Screenshot external result payload is missing view_ref",
            )
        self._view_store.set_image(view_ref, image_uri)
        fixed_data = dict(data)
        fixed_data["image"] = image_uri
        fixed = dict(full)
        fixed["data"] = fixed_data
        self._desktop_nodes.overwrite_external_result(reference, fixed)

    def _normalize_transaction_commit_refs(
        self,
        cad_result: CadResult,
        *,
        payload: dict[str, Any],
        target_doc: str | None,
    ) -> tuple[CadResult, list[tuple[str, str, str]]]:
        """Sanitize Task 13 adapter-private native hints before public emission.

        The runtime may return native tokens only as adapter-private commit evidence.
        We validate persisted provenance against the staged service-owned record,
        allocate public opaque refs without mutating the registry, and defer actual
        registry persistence until outward finalization has succeeded.
        """
        data = dict(cad_result.data) if isinstance(cad_result.data, Mapping) else {}
        raw_hints = data.pop("internal_ref_hints", None)
        if raw_hints is None:
            return cad_result, []
        if not target_doc or not isinstance(target_doc, str):
            raise FusionCadError(
                ErrorCode.NO_ACTIVE_DESIGN,
                "Transaction commit native-ref evidence lacks stable document identity",
            )
        if not isinstance(raw_hints, (list, tuple)) or len(raw_hints) != 1:
            raise FusionCadError(
                ErrorCode.FUSION_API_ERROR,
                "Task 13 commit must return exactly one internal ref hint",
                details={"operation": "commit"},
            )
        tx_id = payload.get("transaction_id")
        record = self._transaction_store.find(tx_id) if isinstance(tx_id, str) else None
        if record is None or len(record.plan) != 1 or record.plan[0].get("action_type") != "text_create":
            raise FusionCadError(
                ErrorCode.TRANSACTION_CONFLICT,
                "Task 13 commit ref evidence is not bound to the exact staged text_create spike",
                details={"operation": "commit"},
            )
        try:
            expected = ProvenanceRecord.model_validate(record.plan[0].get("provenance"))
            returned = ProvenanceRecord.model_validate(data.get("provenance"))
            persisted = ProvenanceRecord.model_validate(data.get("persisted_provenance"))
        except (ValidationError, TypeError, ValueError) as exc:
            raise FusionCadError(
                ErrorCode.FUSION_API_ERROR,
                "Transaction commit lacks valid persisted same-command provenance",
                details={"operation": "commit"},
            ) from exc
        if returned != expected or persisted != expected:
            raise FusionCadError(
                ErrorCode.FUSION_API_ERROR,
                "Transaction commit provenance does not match the staged service-owned record",
                details={"operation": "commit"},
            )

        hint = raw_hints[0]
        if not isinstance(hint, Mapping):
            raise FusionCadError(
                ErrorCode.FUSION_API_ERROR,
                "Transaction commit returned malformed internal ref evidence",
            )
        native_token = hint.get("native_token")
        kind = hint.get("kind")
        if not isinstance(native_token, str) or not native_token.strip():
            raise FusionCadError(
                ErrorCode.FUSION_API_ERROR,
                "Transaction commit returned unusable native ref evidence",
            )
        if not isinstance(kind, str) or not kind.strip():
            kind = "sketch_text"
        opaque_ref = f"ent_{uuid.uuid4().hex[:16]}"
        data["refs"] = [opaque_ref]
        data.pop("persisted_provenance", None)
        clean_data = ImmutableMapping(sanitize_public_payload(data))
        clean_result = cad_result.model_copy(
            update={"data": clean_data, "changed_refs": (opaque_ref,)}
        )
        return clean_result, [(opaque_ref, kind, native_token)]

    def _register_transaction_commit_refs(
        self,
        pending: list[tuple[str, str, str]],
        *,
        document_ref: str | None,
    ) -> None:
        if not pending:
            return
        if not document_ref:
            raise FusionCadError(
                ErrorCode.NO_ACTIVE_DESIGN,
                "Transaction commit cannot persist refs without document identity",
            )
        for opaque_ref, kind, native_token in pending:
            self._ref_registry.issue(
                document_ref=document_ref,
                kind=kind,
                native_token=native_token,
                opaque_ref=opaque_ref,
            )

    def _finalize_completed_execution(
        self,
        result: CadResult | dict[str, Any],
        *,
        effective_bundle_group: str,
        op: str,
        payload: dict[str, Any],
        begin_tx_id: str | None = None,
        begin_doc_ref: str | None = None,
        node_id: str | None = None,
    ) -> CadResult | dict[str, Any]:
        cad_result = (
            result
            if isinstance(result, CadResult)
            else self.decode_domain_result(result)
        )
        pending_transaction_refs: list[tuple[str, str, str]] = []

        # 0. Pre-validate transaction commit / abort / rollback before observing or mutating tracker state
        if effective_bundle_group == "transaction" and op in (
            "commit",
            "abort",
            "rollback",
        ):
            tx_id = payload.get("transaction_id")
            if isinstance(cad_result.data, (dict, Mapping)) and not tx_id:
                tx_id = cad_result.data.get("transaction_id")
            if not tx_id or not isinstance(tx_id, str) or not tx_id.strip():
                raise FusionCadError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"transaction_id is required for transaction {op}",
                    details={"operation": op},
                )
            stored_baseline = self._revision_tracker.get_transaction_baseline(tx_id)
            if stored_baseline is None and op == "commit":
                raise FusionCadError(
                    ErrorCode.INVALID_ARGUMENT,
                    "No stored baseline for transaction; call transaction:begin first",
                    details={"transaction_id": tx_id, "operation": op},
                )
            if stored_baseline is not None:
                if cad_result.status != "succeeded":
                    raise FusionCadError(
                        ErrorCode.FUSION_API_ERROR,
                        f"Transaction '{tx_id}' {op} failed or incomplete (status='{cad_result.status}'); preserving stored baseline",
                        details={
                            "transaction_id": tx_id,
                            "operation": op,
                            "status": cad_result.status,
                        },
                    )
                applied_val = (
                    cad_result.data.get("applied")
                    if isinstance(cad_result.data, (dict, Mapping))
                    else None
                )
                if not isinstance(applied_val, bool) or applied_val is not True:
                    raise FusionCadError(
                        ErrorCode.FUSION_API_ERROR,
                        f"Transaction '{tx_id}' {op} completed without applied=True (applied={applied_val!r}); preserving stored baseline",
                        details={
                            "transaction_id": tx_id,
                            "operation": op,
                            "applied": applied_val,
                        },
                    )
                doc_doc_ref = (
                    cad_result.document.document_ref if cad_result.document else None
                )
                data_doc_ref = (
                    cad_result.data.get("document_ref")
                    if isinstance(cad_result.data, (dict, Mapping))
                    else None
                )
                if doc_doc_ref and data_doc_ref and doc_doc_ref != data_doc_ref:
                    raise FusionCadError(
                        ErrorCode.WRONG_DOCUMENT,
                        f"Transaction '{tx_id}' {op} result document identity diverged between document state ('{doc_doc_ref}') and payload data ('{data_doc_ref}'); preserving stored baseline",
                        details={
                            "transaction_id": tx_id,
                            "bound_document": stored_baseline["document_ref"],
                            "result_document": doc_doc_ref,
                            "data_document": data_doc_ref,
                            "operation": op,
                        },
                    )
                res_doc = doc_doc_ref or data_doc_ref
                if not res_doc or not isinstance(res_doc, str) or not res_doc.strip():
                    raise FusionCadError(
                        ErrorCode.NO_ACTIVE_DESIGN,
                        f"Transaction '{tx_id}' {op} result lacks stable runtime document identity; preserving stored baseline",
                        details={"transaction_id": tx_id, "operation": op},
                    )
                if res_doc != stored_baseline["document_ref"]:
                    raise FusionCadError(
                        ErrorCode.WRONG_DOCUMENT,
                        f"Transaction '{tx_id}' {op} result document '{res_doc}' does not match bound document '{stored_baseline['document_ref']}'; preserving stored baseline",
                        details={
                            "transaction_id": tx_id,
                            "bound_document": stored_baseline["document_ref"],
                            "result_document": res_doc,
                            "operation": op,
                        },
                    )
                res_fp = (
                    cad_result.data.get("fingerprint")
                    if isinstance(cad_result.data, (dict, Mapping))
                    else None
                )
                if not res_fp or not isinstance(res_fp, str) or not res_fp.strip():
                    raise FusionCadError(
                        ErrorCode.FUSION_API_ERROR,
                        f"Transaction '{tx_id}' {op} completed without a real authoritative fingerprint; preserving stored baseline",
                        details={
                            "transaction_id": tx_id,
                            "operation": op,
                            "document_ref": res_doc,
                        },
                    )
                if (
                    op in ("abort", "rollback")
                    and res_fp != stored_baseline["baseline_fingerprint"]
                ):
                    raise FusionCadError(
                        ErrorCode.REVISION_CONFLICT,
                        f"Transaction '{tx_id}' {op} result fingerprint '{res_fp}' diverged from stored baseline; preserving stored baseline",
                        details={
                            "transaction_id": tx_id,
                            "operation": op,
                            "document_ref": res_doc,
                            "result_fingerprint": res_fp,
                            "baseline_fingerprint": stored_baseline[
                                "baseline_fingerprint"
                            ],
                        },
                    )

        tracker_snapshot = self._revision_tracker.snapshot()
        try:
            # 1. Observe document revision state if returned
            fp = None
            if isinstance(cad_result.data, (dict, Mapping)):
                fp = cad_result.data.get("fingerprint")
            target_doc = (
                (cad_result.document.document_ref if cad_result.document else None)
                or (
                    cad_result.data.get("document_ref")
                    if isinstance(cad_result.data, (dict, Mapping))
                    else None
                )
                or begin_doc_ref
                or payload.get("document_ref")
                or self._revision_tracker.active_document_ref
            )
            observed_rec = None
            if target_doc and fp and isinstance(fp, str) and fp.strip():
                observed_rec = self._revision_tracker.observe(target_doc, fp.strip())
                doc_name = (
                    cad_result.document.name
                    if cad_result.document
                    else (
                        cad_result.data.get("name")
                        if isinstance(cad_result.data, (dict, Mapping))
                        else None
                    )
                )
                cad_result = cad_result.model_copy(
                    update={
                        "document": DocumentState(
                            document_ref=target_doc,
                            model_revision=observed_rec.revision,
                            name=doc_name,
                            units="mm",
                        )
                    }
                )
            elif (
                target_doc
                and cad_result.document
                and cad_result.document.model_revision
            ):
                observed_rec = self._revision_tracker.current(target_doc)

            if effective_bundle_group == "transaction" and op == "commit":
                cad_result, pending_transaction_refs = self._normalize_transaction_commit_refs(
                    cad_result, payload=payload, target_doc=target_doc
                )

            # 2. Transaction begin: persist authoritative baseline ONLY after proven successful terminal execution
            if effective_bundle_group == "transaction" and op == "begin":
                tx_id = begin_tx_id or payload.get("transaction_id")
                if isinstance(cad_result.data, (dict, Mapping)) and not tx_id:
                    tx_id = cad_result.data.get("transaction_id")
                if not tx_id or not isinstance(tx_id, str) or not tx_id.strip():
                    raise FusionCadError(
                        ErrorCode.INVALID_ARGUMENT,
                        "transaction:begin completed without a transaction_id; cannot establish authoritative baseline",
                    )

                if (
                    not target_doc
                    or not isinstance(target_doc, str)
                    or not target_doc.strip()
                ):
                    raise FusionCadError(
                        ErrorCode.NO_ACTIVE_DESIGN,
                        "transaction:begin completed without an active document reference or stable runtime identity",
                        details={"transaction_id": tx_id},
                    )

                proven_fp = (
                    cad_result.data.get("fingerprint")
                    if isinstance(cad_result.data, (dict, Mapping))
                    else None
                )
                if (
                    not proven_fp
                    or not isinstance(proven_fp, str)
                    or not proven_fp.strip()
                ):
                    raise FusionCadError(
                        ErrorCode.FUSION_API_ERROR,
                        "transaction:begin terminal success with missing, empty, or whitespace real fingerprint; failing closed to prevent unusable baseline",
                        details={
                            "transaction_id": tx_id,
                            "document_ref": target_doc,
                            "fingerprint": proven_fp,
                        },
                    )

                rec = observed_rec or self._revision_tracker.current(target_doc)
                if rec is None or rec.fingerprint != proven_fp.strip():
                    rec = self._revision_tracker.observe(target_doc, proven_fp.strip())
                self._revision_tracker.begin_transaction(
                    tx_id,
                    document_ref=target_doc,
                    baseline_revision=rec.revision,
                    baseline_fingerprint=proven_fp.strip(),
                )
                latest_snapshot = self._snapshot_store.get_latest(target_doc)
                baseline_snapshot = (
                    latest_snapshot.model_dump(mode="json", exclude_none=True)
                    if latest_snapshot is not None
                    else {"structural_hash": proven_fp.strip(), "counts": {}, "refs": []}
                )
                self._transaction_store.begin(
                    tx_id,
                    document_ref=target_doc,
                    baseline_revision=rec.revision,
                    baseline_fingerprint=proven_fp.strip(),
                    baseline_snapshot=baseline_snapshot,
                )
                if isinstance(cad_result.data, dict) and tx_id:
                    cad_result.data["transaction_id"] = tx_id
                cad_result = cad_result.model_copy(
                    update={
                        "document": DocumentState(
                            document_ref=target_doc,
                            model_revision=rec.revision,
                            name=cad_result.document.name
                            if cad_result.document
                            else None,
                            units="mm",
                        )
                    }
                )

            # 3. Persist the declarative state transition only after terminal
            # desktop evidence. Preview evidence is explicitly non-durable.
            if effective_bundle_group == "transaction" and op == "stage":
                tx_id = payload.get("transaction_id")
                action = payload.get("action")
                if isinstance(tx_id, str) and isinstance(action, Mapping):
                    record = self._transaction_store.stage(tx_id, action)
                    if isinstance(cad_result.data, dict):
                        cad_result.data.update(
                            {"state": record.state.value, "plan_hash": record.plan_hash}
                        )
            if effective_bundle_group == "transaction" and op == "preview":
                tx_id = payload.get("transaction_id")
                record = self._transaction_store.find(tx_id) if isinstance(tx_id, str) else None
                if isinstance(tx_id, str) and record is not None and record.plan:
                    self._transaction_store.begin_preview(
                        tx_id, record.baseline_fingerprint
                    )
                    evidence = cad_result.model_dump(mode="json").get("data", {})
                    self._transaction_store.finish_preview(tx_id, preview=evidence)
            if effective_bundle_group == "transaction" and op == "commit":
                tx_id = payload.get("transaction_id")
                record = self._transaction_store.find(tx_id) if isinstance(tx_id, str) else None
                if isinstance(tx_id, str) and record is not None and record.plan:
                    self._transaction_store.begin_commit(
                        tx_id, record.baseline_fingerprint
                    )
                    evidence = cad_result.model_dump(mode="json").get("data", {})
                    self._transaction_store.finish_commit(tx_id, evidence)
            if effective_bundle_group == "transaction" and op in ("abort", "rollback"):
                tx_id = payload.get("transaction_id")
                if isinstance(tx_id, str) and self._transaction_store.find(tx_id) is not None:
                    self._transaction_store.rollback(tx_id)

            # 4. Transaction commit / abort / rollback: clear stored baseline ONLY after proven terminal execution
            if effective_bundle_group == "transaction" and op in (
                "commit",
                "abort",
                "rollback",
            ):
                tx_id = payload.get("transaction_id")
                if isinstance(cad_result.data, (dict, Mapping)) and not tx_id:
                    tx_id = cad_result.data.get("transaction_id")
                if tx_id:
                    self._revision_tracker.clear_transaction(tx_id)

            # 5. Semantic read normalization and snapshot store
            if effective_bundle_group == "read":
                if op == "model_snapshot":
                    detail = payload.get("detail", "compact")
                    raw_data = (
                        dict(cad_result.data)
                        if isinstance(cad_result.data, (dict, Mapping))
                        else {}
                    )
                    if cad_result.document:
                        raw_data.setdefault(
                            "document_ref", cad_result.document.document_ref
                        )
                        raw_data.setdefault(
                            "model_revision", cad_result.document.model_revision
                        )
                    snapshot = normalize_snapshot(
                        raw_data,
                        detail=detail,
                        ref_registry=self._ref_registry,
                    )
                    self._snapshot_store.put(snapshot)
                    doc_state = cad_result.document
                    if doc_state:
                        doc_state = doc_state.model_copy(
                            update={"snapshot_id": snapshot.snapshot_id}
                        )
                    cad_result = cad_result.model_copy(
                        update={
                            "document": doc_state,
                            "data": ImmutableMapping(
                                sanitize_public_payload(
                                    snapshot.model_dump(
                                        mode="python", exclude_none=True
                                    )
                                )
                            ),
                        }
                    )
                elif op == "feature_tree":
                    if isinstance(cad_result.data, (dict, Mapping)):
                        feats = cad_result.data.get("features", [])
                        if isinstance(feats, (list, tuple)):
                            norm_feats = [
                                sanitize_public_payload(
                                    normalize_feature(
                                        f,
                                        ref_registry=self._ref_registry,
                                        document_ref=target_doc or "doc_active",
                                    ).model_dump(mode="python", exclude_none=True)
                                )
                                for f in feats
                                if isinstance(f, Mapping)
                            ]
                            cad_result = cad_result.model_copy(
                                update={
                                    "data": ImmutableMapping(
                                        {
                                            "features": norm_feats,
                                            "count": len(norm_feats),
                                        }
                                    )
                                }
                            )
                elif op == "sketch":
                    if isinstance(cad_result.data, (dict, Mapping)):
                        sketch_dict = dict(
                            cad_result.data.get("sketch") or cad_result.data
                        )
                        sketch_res = normalize_sketch_read(
                            sketch_dict,
                            ref_registry=self._ref_registry,
                            document_ref=target_doc or "doc_active",
                            include_profiles=payload.get("include_profiles", True),
                            include_constraints=payload.get(
                                "include_constraints", True
                            ),
                        )
                        cad_result = cad_result.model_copy(
                            update={
                                "data": ImmutableMapping(
                                    sanitize_public_payload(
                                        sketch_res.model_dump(
                                            mode="python", exclude_none=True
                                        )
                                    )
                                )
                            }
                        )
                elif op == "parameters":
                    if isinstance(cad_result.data, (dict, Mapping)):
                        params_raw = (
                            cad_result.data.get("parameters") or cad_result.data
                        )
                        include_model = payload.get("include_model_params", True)
                        include_user = payload.get("include_user_params", True)
                        if isinstance(params_raw, Mapping):
                            filtered = {}
                            if include_model:
                                filtered["model_parameters"] = list(
                                    params_raw.get("model_parameters", [])
                                )
                            if include_user:
                                filtered["user_parameters"] = list(
                                    params_raw.get("user_parameters", [])
                                )
                            cad_result = cad_result.model_copy(
                                update={
                                    "data": ImmutableMapping(
                                        sanitize_public_payload(
                                            {"parameters": filtered}
                                        )
                                    )
                                }
                            )
                        elif isinstance(params_raw, (list, tuple)):
                            filtered_list = [
                                p
                                for p in params_raw
                                if (
                                    include_user
                                    if (isinstance(p, Mapping) and p.get("is_user"))
                                    else include_model
                                )
                            ]
                            cad_result = cad_result.model_copy(
                                update={
                                    "data": ImmutableMapping(
                                        {
                                            "parameters": tuple(
                                                sanitize_public_payload(p)
                                                for p in filtered_list
                                            )
                                        }
                                    )
                                }
                            )
                elif op == "query":
                    sel_input = payload.get("selector")
                    norm_sel = self._selector_engine.normalize(sel_input)
                    raw_candidates = []
                    if isinstance(cad_result.data, (dict, Mapping)):
                        raw_candidates = list(
                            cad_result.data.get("candidates")
                            or cad_result.data.get("entities")
                            or []
                        )
                    if not raw_candidates and target_doc:
                        latest_snap = self._snapshot_store.get_latest(target_doc)
                        if latest_snap:
                            raw_candidates = (
                                list(latest_snap.components)
                                + list(latest_snap.occurrences)
                                + list(latest_snap.bodies)
                                + list(latest_snap.sketches)
                                + list(latest_snap.features)
                            )
                    candidates = []
                    for idx, cand in enumerate(raw_candidates):
                        if isinstance(cand, Mapping):
                            d = dict(cand)
                            raw_ref = d.get("ref") or f"ent_query_{idx}"
                            native_tok = (
                                d.get("entityToken")
                                or d.get("native_token")
                                or d.get("token")
                            )
                            if target_doc:
                                iss = self._ref_registry.issue(
                                    document_ref=target_doc,
                                    kind=d.get("kind", "entity"),
                                    name=d.get("name"),
                                    component_path=d.get("component_path") or (),
                                    native_token=native_tok,
                                    opaque_ref=raw_ref
                                    if re.match(ENTITY_REF_PATTERN, raw_ref)
                                    else None,
                                )
                                d["ref"] = iss.ref
                            d_clean = sanitize_public_payload(d)
                            candidates.append(d_clean)
                        else:
                            candidates.append(cand)

                    query_res = self._selector_engine.query(norm_sel, candidates)
                    limit = int(payload.get("limit", 100))
                    limited_entities = query_res.entities[:limit]
                    limited_refs = query_res.refs[:limit]
                    cad_result = cad_result.model_copy(
                        update={
                            "data": ImmutableMapping(
                                {
                                    "matched_count": len(query_res.entities),
                                    "normalized_selector": norm_sel.model_dump(
                                        mode="python", exclude_none=True
                                    ),
                                    "refs": tuple(limited_refs),
                                    "entities": tuple(
                                        e.model_dump(mode="python", exclude_none=True)
                                        if isinstance(e, BaseModel)
                                        else sanitize_public_payload(e)
                                        for e in limited_entities
                                    ),
                                }
                            )
                        }
                    )
                elif op == "selection":
                    if isinstance(cad_result.data, (dict, Mapping)):
                        sel_ents = list(cad_result.data.get("entities", []))
                        norm_ents = []
                        norm_refs = []
                        for idx, item in enumerate(sel_ents):
                            if isinstance(item, Mapping):
                                d = dict(item)
                                raw_ref = d.get("ref") or f"ent_sel_{idx}"
                                native_tok = (
                                    d.get("entityToken")
                                    or d.get("native_token")
                                    or d.get("token")
                                )
                                if target_doc:
                                    iss = self._ref_registry.issue(
                                        document_ref=target_doc,
                                        kind=d.get("kind", "selection"),
                                        name=d.get("name"),
                                        native_token=native_tok,
                                        opaque_ref=raw_ref
                                        if re.match(ENTITY_REF_PATTERN, raw_ref)
                                        else None,
                                    )
                                    d["ref"] = iss.ref
                                norm_refs.append(d["ref"])
                                if "frame" not in d or d["frame"] is None:
                                    d["frame"] = {"space": "world", "ref": None}
                                d_clean = sanitize_public_payload(d)
                                norm_ents.append(d_clean)
                        cad_result = cad_result.model_copy(
                            update={
                                "data": ImmutableMapping(
                                    {
                                        "count": len(norm_ents),
                                        "refs": tuple(norm_refs),
                                        "entities": tuple(norm_ents),
                                    }
                                )
                            }
                        )

            # 5. Semantic inspect normalization
            if effective_bundle_group == "inspect" and isinstance(
                cad_result.data, (dict, Mapping)
            ):
                norm_inspect = normalize_inspect_result(
                    cad_result.data,
                    operation=op,
                    ref_registry=self._ref_registry,
                    document_ref=target_doc or "doc_active",
                )
                cad_result = cad_result.model_copy(
                    update={"data": ImmutableMapping(norm_inspect)}
                )

            # 5b. Task 10 metadata result normalization (reserved namespace only)
            if (
                effective_bundle_group == "mutate"
                and op in _METADATA_OPS
                and isinstance(cad_result.data, (dict, Mapping))
            ):
                cad_result = self._finalize_metadata_execution(
                    cad_result,
                    op=op,
                    payload=payload,
                    target_doc=target_doc if isinstance(target_doc, str) else None,
                )

            # 5c. Task 11 logical text/visibility evidence normalization.
            if (
                effective_bundle_group == "mutate"
                and op
                in {
                    "text_create",
                    "text_read",
                    "text_update",
                    "text_delete",
                    "text_extrude",
                    "text_cut",
                    "show",
                    "hide",
                    "set",
                    "show_only",
                    "isolate",
                    "restore",
                }
                and not (op == "set" and "name" in payload)
            ):
                cad_result = self._finalize_style_execution(
                    cad_result, op=op, payload=payload
                )

            if effective_bundle_group == "view" and op == "pick":
                cad_result = self._finalize_pick_execution(cad_result, payload=payload)

            # 6. Semantic view normalization: camera/visibility/section + immutable ViewRef
            if effective_bundle_group == "view" and op in _VIEW_FINALIZE_OPS:
                cad_result = self._finalize_view_operation(
                    cad_result, op=op, payload=payload, node_id=node_id
                )

            if effective_bundle_group == "validate" and op == "run":
                raw_evidence = (
                    dict(cad_result.data)
                    if isinstance(cad_result.data, (dict, Mapping))
                    else {}
                )
                validation_doc = (
                    raw_evidence.get("document_ref")
                    or target_doc
                    or self._revision_tracker.active_document_ref
                    or "doc_active"
                )
                normalized_evidence = self._normalize_validation_evidence(
                    raw_evidence, document_ref=validation_doc
                )
                current = self._revision_tracker.current(validation_doc)
                report = validate_model_evidence(
                    normalized_evidence,
                    profiles=tuple(payload.get("profiles") or P0_VALIDATION_PROFILES),
                    checks=tuple(payload.get("checks") or ()),
                    model_revision=current.revision if current is not None else None,
                )
                limitation_codes = raw_evidence.get("limitations")
                public_limitations = []
                if isinstance(limitation_codes, (list, tuple)) and (
                    "constraint_and_open_profile_state_unavailable" in limitation_codes
                ):
                    public_limitations.append(
                        "Authoritative fully-constrained and open-profile state is unavailable from proven runtime access; no state was inferred"
                    )
                cad_result = cad_result.model_copy(
                    update={
                        "summary": report.summary,
                        "data": ImmutableMapping(
                            {
                                "read_only": True,
                                "document_ref": validation_doc,
                                "finding_count": len(report.findings),
                                "limitations": public_limitations,
                            }
                        ),
                        "validation": ImmutableMapping(
                            sanitize_public_payload(
                                report.model_dump(mode="python", exclude_none=True)
                            )
                        ),
                        "document": DocumentState(
                            document_ref=validation_doc,
                            model_revision=current.revision if current is not None else "rev_0",
                            name=cad_result.document.name if cad_result.document else None,
                            units="mm",
                        ),
                    }
                )

            domain_payload = cad_result.model_dump(mode="python", exclude_none=True)
            if node_id and (
                has_binary_data(domain_payload) or self._is_oversized(domain_payload)
            ):
                sanitize_binary = (
                    effective_bundle_group == "view" and op == "screenshot"
                )
                store_err: FusionCadError | None = None
                try:
                    external_ref = self._desktop_nodes.store_external_result(
                        node_id, domain_payload, sanitize_binary=sanitize_binary
                    )
                except Exception:  # noqa: BLE001 - low-level storage errors stay internal only
                    store_err = FusionCadError(
                        ErrorCode.INTERNAL_ERROR,
                        "Failed to externalize binary result payload",
                        details={"node_id": trusted_detail(node_id)},
                    )
                if store_err is not None:
                    raise store_err
                if sanitize_binary:
                    self._bind_screenshot_image_uri(external_ref)
                self._register_transaction_commit_refs(
                    pending_transaction_refs, document_ref=target_doc
                )
                if node_id and target_doc:
                    self._active_document_refs_by_node[node_id] = target_doc
                return external_ref

            self._register_transaction_commit_refs(
                pending_transaction_refs, document_ref=target_doc
            )
            if node_id and target_doc:
                self._active_document_refs_by_node[node_id] = target_doc
            if isinstance(result, dict) and not isinstance(result, CadResult):
                return cad_result.model_dump(mode="python", exclude_none=True)
            return cad_result
        except Exception:
            self._revision_tracker.restore(tracker_snapshot)
            raise

    def _normalize_validation_evidence(
        self, raw: Mapping[str, Any], *, document_ref: str
    ) -> dict[str, Any]:
        """Replace runtime identities with document-scoped opaque refs."""
        normalized: dict[str, Any] = {}
        token_refs: dict[str, str] = {}
        entity_groups = ("features", "sketches", "references", "bodies", "text_outputs")

        for group in entity_groups:
            clean_items: list[dict[str, Any]] = []
            source_items = raw.get(group, ())
            if not isinstance(source_items, (list, tuple)):
                source_items = ()
            for source in source_items:
                if not isinstance(source, Mapping):
                    continue
                clean = dict(sanitize_public_payload(source))
                native_id = source.get("native_token") or source.get("native_id")
                kind = str(source.get("kind") or group.rstrip("s") or "entity")
                existing_ref = source.get("ref")
                if isinstance(existing_ref, str) and re.fullmatch(ENTITY_REF_PATTERN, existing_ref):
                    clean["ref"] = existing_ref
                elif isinstance(native_id, str) and native_id:
                    issued = self._ref_registry.issue(
                        document_ref=document_ref,
                        kind=kind,
                        native_token=native_id,
                        name=str(source.get("name")) if source.get("name") else None,
                    ).ref
                    clean["ref"] = issued
                    token_refs[native_id] = issued
                clean_items.append(clean)
            normalized[group] = clean_items

        for item in normalized.get("references", []):
            target = item.get("target_ref")
            if isinstance(target, str) and target in token_refs:
                item["target_ref"] = token_refs[target]
        for item in normalized.get("text_outputs", []):
            source_ref = item.get("source_ref")
            if isinstance(source_ref, str) and source_ref in token_refs:
                item["source_ref"] = token_refs[source_ref]
            output_refs = item.get("output_refs")
            if isinstance(output_refs, (list, tuple)):
                item["output_refs"] = [token_refs.get(str(ref), str(ref)) for ref in output_refs]

        timeline = raw.get("timeline")
        normalized["timeline"] = (
            dict(sanitize_public_payload(timeline))
            if isinstance(timeline, Mapping)
            else {"available": False}
        )
        return normalized

    def finalize_terminal_operation(
        self,
        op_status: dict[str, Any],
        full_result: Any,
    ) -> CadResult | dict[str, Any]:
        """Finalize a terminal desktop operation from the durable operation lifecycle.

        Persists authoritative baseline for transaction:begin or clears baseline
        for commit/abort/rollback ONLY after proven successful terminal execution.
        Failed, uncertain, or queued operations fail closed and do not manufacture
        or discard authoritative transaction state. Returns the finalized result
        (CadResult, or an external_result reference dict when binary payloads are
        externalized) so the caller renders the exact emitted artifacts.
        """
        status = op_status.get("status")
        if status not in ("succeeded", "late_succeeded"):
            if self._is_error_payload(full_result):
                err_code, err_msg, err_details = self._extract_error_info(full_result)
                raise FusionCadError(
                    err_code, err_msg, retryable=False, details=err_details
                )
            raise FusionCadError(
                ErrorCode.FUSION_API_ERROR,
                f"Cannot finalize incomplete or non-succeeded operation (status='{status}')",
                details={
                    "status": status,
                    "operation_id": op_status.get("operation_id"),
                },
            )

        if self._is_error_payload(full_result):
            err_code, err_msg, err_details = self._extract_error_info(full_result)
            raise FusionCadError(
                err_code, err_msg, retryable=False, details=err_details
            )

        cad_result = self.decode_domain_result(full_result)
        checkpoint = op_status.get("checkpoint") or {}
        if not isinstance(checkpoint, Mapping):
            checkpoint = {}
        finalization_payload = checkpoint.get("finalization_payload")
        payload = (
            dict(finalization_payload)
            if isinstance(finalization_payload, Mapping)
            else dict(checkpoint)
        )
        # Core routing/authority fields remain pinned to the durable checkpoint
        # for compatibility and to prevent a nested context from overriding them.
        for key in ("operation", "transaction_id", "document_ref"):
            if checkpoint.get(key) is not None:
                payload[key] = checkpoint[key]
        summary = str(op_status.get("summary") or "")

        group = checkpoint.get("group")
        op = checkpoint.get("operation") or payload.get("operation")
        if (not group or not op) and ":" in summary:
            parts = summary.split(":", 1)
            group = group or parts[0]
            op = op or parts[1]

        effective_bundle_group = (
            "mutate" if group in ("metadata", "style") else (group or "")
        )
        tx_id = checkpoint.get("transaction_id") or payload.get("transaction_id") or (
            cad_result.data.get("transaction_id")
            if isinstance(cad_result.data, (dict, Mapping))
            else None
        )
        doc_ref = checkpoint.get("document_ref") or payload.get("document_ref")
        node_id = checkpoint.get("node_id") or op_status.get("node_id")

        return self._finalize_completed_execution(
            cad_result,
            effective_bundle_group=effective_bundle_group,
            op=op or "",
            payload=payload,
            begin_tx_id=tx_id
            if (effective_bundle_group == "transaction" and op == "begin")
            else None,
            begin_doc_ref=doc_ref,
            node_id=node_id,
        )

    def _resolve_group(self, request: Any) -> str:
        if isinstance(request, FusionReadRequest.__args__):  # type: ignore[attr-defined]
            return "read"
        if isinstance(request, FusionInspectRequest.__args__):  # type: ignore[attr-defined]
            return "inspect"
        if isinstance(request, FusionViewRequest.__args__):  # type: ignore[attr-defined]
            return "view"
        if isinstance(request, FusionMetadataRequest.__args__):  # type: ignore[attr-defined]
            return "mutate"
        if isinstance(request, FusionStyleRequest.__args__):  # type: ignore[attr-defined]
            return "mutate"
        if isinstance(request, FusionValidateRequest.__args__):  # type: ignore[attr-defined]
            return "validate"
        if isinstance(request, FusionTransactionRequest.__args__):  # type: ignore[attr-defined]
            return "transaction"
        raise BridgeError(
            ErrorCode.INVALID_ARGUMENT,
            f"Unsupported request model type: {type(request).__name__}",
        )

    @classmethod
    def _validate_request_dict(
        cls, request_dict: dict[str, Any], group: str | None = None
    ) -> tuple[BaseModel, str]:
        if not isinstance(request_dict, dict):
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                f"Expected request to be a dict, got {type(request_dict).__name__}",
            )
        op = request_dict.get("operation")
        if not op or not isinstance(op, str):
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                "Operation name is required in request payload",
            )

        target_group = group
        if target_group is None:
            if op in (
                "describe",
                "bounding_box",
                "oriented_bbox",
                "centroid",
                "area",
                "perimeter",
                "volume",
                "distance",
                "minimum_distance",
                "angle",
                "parallel",
                "perpendicular",
                "coplanar",
                "concentric",
                "face_to_face_thickness",
            ):
                target_group = "inspect"
            elif op in (
                "camera_read",
                "camera_set",
                "fit",
                "zoom_entity",
                "orient_to_face",
                "standard_view",
                "screenshot",
                "pick",
            ):
                target_group = "view"
            elif op == "run":
                target_group = "validate"
            elif op in (
                "begin",
                "stage",
                "preview",
                "commit",
                "rollback",
                "abort",
                "status",
            ):
                target_group = "transaction"
            elif op in (
                "text_create",
                "text_read",
                "text_update",
                "text_delete",
                "text_extrude",
                "text_cut",
                "show",
                "hide",
                "show_only",
                "isolate",
                "restore",
            ):
                target_group = "style"
            elif op in (
                "get",
                "remove",
                "tag",
                "untag",
                "set_role",
                "clear_role",
                "provenance",
            ):
                target_group = "metadata"
            elif (
                op
                in (
                    "model_snapshot",
                    "entity",
                    "feature_tree",
                    "sketch",
                    "parameters",
                    "selection",
                    "capabilities",
                )
                or op == "visibility"
            ):
                target_group = "read"
            elif op == "query":
                target_group = "read" if "selector" in request_dict else "metadata"
            elif op == "set":
                target_group = "style" if "visible" in request_dict else "metadata"
            else:
                raise FusionCadError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"Unknown operation '{op}' in request payload",
                    details={"operation": op},
                )

        if target_group == "mutate":
            if (
                op
                in (
                    "get",
                    "remove",
                    "tag",
                    "untag",
                    "set_role",
                    "clear_role",
                    "provenance",
                )
                or (op == "set" and "name" in request_dict)
                or (op == "query" and "selector" not in request_dict)
            ):
                adapter = _GROUP_REQUEST_ADAPTERS["metadata"]
            else:
                adapter = _GROUP_REQUEST_ADAPTERS["style"]
            bundle_group = "mutate"
        elif target_group in _GROUP_REQUEST_ADAPTERS:
            adapter = _GROUP_REQUEST_ADAPTERS[target_group]
            bundle_group = (
                "mutate" if target_group in ("metadata", "style") else target_group
            )
        else:
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                f"Unknown request group '{target_group}'",
                details={"group": target_group},
            )

        val_err: FusionCadError | None = None
        try:
            validated = adapter.validate_python(request_dict)
            return validated, target_group, bundle_group
        except ValidationError as exc:
            safe_msg = format_safe_validation_message(
                f"Invalid {target_group} request payload", exc.errors()
            )
            val_err = FusionCadError(
                ErrorCode.INVALID_ARGUMENT,
                safe_msg,
                details={"validation_errors": sanitize_validation_errors(exc.errors())},
            )
        if val_err is not None:
            raise val_err

    def _classify_operation(
        self, group: str, payload: dict[str, Any]
    ) -> tuple[bool, bool, str]:
        op = str(payload.get("operation", ""))
        if not op:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "Operation name is required in request payload",
            )
        summary = f"{group}:{op}"

        effective_group = "mutate" if group in ("metadata", "style") else group

        if effective_group == "read" and op == "model_snapshot":
            is_async = payload.get("detail") == "full" or bool(
                payload.get("include_views")
            )
            return is_async, False, summary

        classification = _CAD_OPERATION_CLASSIFICATION.get((effective_group, op))
        if classification is None:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                f"Unknown or unclassified operation '{op}' for group '{group}'",
                details={"group": group, "operation": op},
            )
        is_async, is_mutation = classification
        return is_async, is_mutation, summary

    async def execute(
        self,
        request: BaseModel | dict[str, Any],
        group: str | None = None,
    ) -> CadResult | dict[str, Any]:
        if isinstance(request, _StrictCadBase):
            domain_group = group or self._resolve_group(request)
            effective_bundle_group = (
                "mutate" if domain_group in ("metadata", "style") else domain_group
            )
            node_id = request.node_id
            payload = request.model_dump(mode="json", exclude_none=True)
        elif isinstance(request, BaseModel):
            validated_model, domain_group, effective_bundle_group = (
                self._validate_request_dict(
                    request.model_dump(mode="python", exclude_none=True),
                    group=group,
                )
            )
            node_id = validated_model.node_id  # type: ignore[union-attr]
            payload = validated_model.model_dump(mode="json", exclude_none=True)
        elif isinstance(request, dict):
            validated_model, domain_group, effective_bundle_group = (
                self._validate_request_dict(request, group=group)
            )
            node_id = validated_model.node_id  # type: ignore[union-attr]
            payload = validated_model.model_dump(mode="json", exclude_none=True)
        else:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                f"Expected request to be BaseModel or dict, got {type(request).__name__}",
            )

        if not node_id or not isinstance(node_id, str):
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "node_id is required for Fusion CAD operations",
            )
        if "document_ref" not in payload:
            node_document_ref = self._active_document_refs_by_node.get(node_id)
            if node_document_ref is not None:
                payload["document_ref"] = node_document_ref

        # Enforce capability-first dispatch before script generation or execution
        op = str(payload.get("operation", ""))
        if effective_bundle_group == "validate" and op == "run":
            requested_profiles = tuple(payload.get("profiles") or ())
            if not requested_profiles or any(
                profile not in P0_VALIDATION_PROFILES
                for profile in requested_profiles
            ):
                raise FusionCadError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Validation profiles must be non-empty P0 profile names",
                    details={"profile_set": "invalid"},
                )
        required_cap = get_required_capability(domain_group, op, payload)
        if required_cap is not None:
            matrix = self.get_node_capabilities(node_id)
            if matrix is None:
                raise FusionCadError(
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                    "Node capability state is unprobed; invoke fusion_read(operation='capabilities') first",
                    retryable=False,
                    details={
                        "node_id": trusted_detail(node_id),
                        "capability": trusted_detail(required_cap),
                    },
                )
            legacy_capabilities = {
                "style.text_read": "style.sketch_text",
                "style.text_create": "style.sketch_text",
                "style.text_update": "style.sketch_text",
                "style.text_delete": "style.sketch_text",
                "style.text_extrude": "style.sketch_text",
                "style.text_cut": "style.sketch_text",
                "style.visibility": "design.access",
            }
            effective_cap = required_cap
            if matrix.get(required_cap) is None:
                effective_cap = legacy_capabilities.get(required_cap, required_cap)
            matrix.require(effective_cap, allow_degraded=False)

        is_async, is_mutation, summary = self._classify_operation(
            effective_bundle_group, payload
        )

        is_standalone_mutation = (effective_bundle_group == "mutate") and is_mutation
        is_transaction_preview_commit = (effective_bundle_group == "transaction") and (
            op in ("preview", "commit")
        )

        # Every mutation/preview/commit must require supported atomic revision safety
        if is_standalone_mutation or is_transaction_preview_commit:
            matrix = self.get_node_capabilities(node_id)
            if matrix is None:
                raise FusionCadError(
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                    "Node capability state is unprobed; invoke fusion_read(operation='capabilities') first",
                    retryable=False,
                    details={
                        "node_id": trusted_detail(node_id),
                        "capability": trusted_detail(
                            "revision.external_change_detection"
                        ),
                    },
                )
            matrix.require("revision.external_change_detection", allow_degraded=False)

        # Every standalone mutation must require expected_revision and reject missing revision
        if is_standalone_mutation and not payload.get("expected_revision"):
            raise FusionCadError(
                ErrorCode.REVISION_CONFLICT,
                "expected_revision is required for standalone mutation",
                details={
                    "document_ref": payload.get("document_ref")
                    or self._revision_tracker.active_document_ref,
                    "expected_revision": None,
                    "operation": op,
                },
            )

        # Finding 1: Transaction preview/commit must bind to stored baseline,
        # not caller-selected expected_revision, to prevent freshness bypass.
        # Staging also remains bound to stored transaction baseline.
        is_transaction_begin = (effective_bundle_group == "transaction") and (
            op == "begin"
        )
        is_transaction_preview_commit = (effective_bundle_group == "transaction") and (
            op in ("preview", "commit")
        )
        is_transaction_stage = (effective_bundle_group == "transaction") and (
            op == "stage"
        )
        if is_transaction_stage or is_transaction_preview_commit:
            tx_id = payload.get("transaction_id")
            if not tx_id:
                raise FusionCadError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"transaction_id is required for transaction {op}",
                )
            try:
                transaction = self._transaction_store.get(tx_id)
            except FusionCadError as exc:
                if exc.code != ErrorCode.INVALID_ARGUMENT:
                    raise
                transaction = None
            if transaction is not None and transaction.state in (
                TransactionState.COMMITTED,
                TransactionState.ABORTED,
                TransactionState.PREVIEWED,
            ):
                raise FusionCadError(
                    ErrorCode.TRANSACTION_CONFLICT,
                    "Transaction state does not permit this operation",
                    details={"transaction_id": tx_id, "operation": op},
                )
            stored_baseline = self._revision_tracker.get_transaction_baseline(tx_id)
            if stored_baseline is None:
                raise FusionCadError(
                    ErrorCode.INVALID_ARGUMENT,
                    "No stored baseline for transaction; call transaction:begin first",
                    details={"transaction_id": tx_id, "operation": op},
                )
            if (
                payload.get("document_ref")
                and payload["document_ref"] != stored_baseline["document_ref"]
            ):
                raise FusionCadError(
                    ErrorCode.WRONG_DOCUMENT,
                    f"Transaction '{tx_id}' is bound to document '{stored_baseline['document_ref']}', but request specified '{payload['document_ref']}'; transaction operations cannot switch documents",
                    details={
                        "transaction_id": tx_id,
                        "bound_document": stored_baseline["document_ref"],
                        "requested_document": payload["document_ref"],
                    },
                )
            # Override expected_revision/fingerprint with stored baseline
            payload["expected_revision"] = stored_baseline["baseline_revision"]
            payload["expected_fingerprint"] = stored_baseline["baseline_fingerprint"]
            payload["document_ref"] = stored_baseline["document_ref"]
            if transaction is not None and is_transaction_preview_commit:
                payload["plan"] = [dict(action) for action in transaction.plan]
                payload["plan_hash"] = transaction.plan_hash
                payload["baseline_snapshot"] = dict(transaction.baseline_snapshot)

        if op in ("abort", "rollback") and effective_bundle_group == "transaction":
            tx_id = payload.get("transaction_id")
            if not tx_id:
                raise FusionCadError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"transaction_id is required for transaction {op}",
                )
            stored_baseline = self._revision_tracker.get_transaction_baseline(tx_id)
            if stored_baseline is not None:
                if (
                    payload.get("document_ref")
                    and payload["document_ref"] != stored_baseline["document_ref"]
                ):
                    raise FusionCadError(
                        ErrorCode.WRONG_DOCUMENT,
                        f"Transaction '{tx_id}' is bound to document '{stored_baseline['document_ref']}', but request specified '{payload['document_ref']}'",
                        details={
                            "transaction_id": tx_id,
                            "bound_document": stored_baseline["document_ref"],
                            "requested_document": payload["document_ref"],
                        },
                    )
                payload["document_ref"] = stored_baseline["document_ref"]
            try:
                transaction = self._transaction_store.get(tx_id)
            except FusionCadError as exc:
                if exc.code != ErrorCode.INVALID_ARGUMENT:
                    raise
                transaction = None
            if transaction is not None and transaction.state in (
                TransactionState.COMMITTED,
                TransactionState.ABORTED,
            ):
                raise FusionCadError(
                    ErrorCode.TRANSACTION_CONFLICT,
                    "Transaction is already terminal",
                    details={"transaction_id": tx_id, "operation": op},
                )

        # Bridge revision freshness precheck (fail-fast optimization)
        if is_standalone_mutation or is_transaction_preview_commit:
            exp_rev = payload.get("expected_revision")
            doc_ref = (
                payload.get("document_ref")
                or self._revision_tracker.active_document_ref
            )
            if exp_rev is not None:
                if not doc_ref:
                    raise FusionCadError(
                        ErrorCode.NO_ACTIVE_DESIGN,
                        "No active design or document_ref provided for mutation freshness check",
                    )
                self.assert_fresh_for_mutation(payload, document_ref=doc_ref)
                known_fp = self._revision_tracker.get_fingerprint(doc_ref, exp_rev)
                if known_fp is not None:
                    payload["expected_fingerprint"] = known_fp
                else:
                    payload.pop("expected_fingerprint", None)
            elif "expected_fingerprint" in payload:
                payload.pop("expected_fingerprint", None)

        # Task 13 feasibility is intentionally narrower than the public staging
        # contract. Preserve freshness-error precedence, then require an actually
        # staged single logical-text spike before preview/commit dispatch.
        if (
            is_transaction_preview_commit
            and transaction is not None
            and transaction.plan
        ):
            if transaction.state is not TransactionState.STAGED:
                raise FusionCadError(
                    ErrorCode.TRANSACTION_CONFLICT,
                    "Transaction state does not permit preview or commit",
                    details={"transaction_id": transaction.transaction_id, "operation": op},
                )
            is_p0_spike = (
                len(transaction.plan) == 1
                and transaction.plan[0].get("action_type") == "text_create"
            )
            if not is_p0_spike:
                raise FusionCadError(
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                    "P0 transaction preview/commit feasibility is limited to the logical text creation spike",
                    details={"operation": op, "applied": False},
                )

        # Transaction begin: persist baseline after execution succeeds (below)
        if is_transaction_begin:
            _begin_tx_id = payload.get("transaction_id")
            if not _begin_tx_id:
                _begin_tx_id = f"tx_{uuid.uuid4().hex[:12]}"
                payload["transaction_id"] = _begin_tx_id
            _begin_doc_ref = (
                payload.get("document_ref")
                or self._revision_tracker.active_document_ref
            )
            exp_rev = payload.get("expected_revision")
            if exp_rev is not None and _begin_doc_ref:
                self.assert_fresh_for_mutation(payload, document_ref=_begin_doc_ref)
                known_fp = self._revision_tracker.get_fingerprint(
                    _begin_doc_ref, exp_rev
                )
                if known_fp is not None:
                    payload["expected_fingerprint"] = known_fp
                else:
                    payload.pop("expected_fingerprint", None)
            elif "expected_fingerprint" in payload:
                payload.pop("expected_fingerprint", None)

        # Remove caller-supplied synthetic authority
        payload.pop("mock_model_state", None)

        # Task 10: reserved-namespace metadata preparation. Metadata writes get
        # the one-command plan (explicit writes/removals plus provenance) applied
        # by the SAME script execution as any geometry change; foreign groups
        # fail closed before dispatch.
        # Durable command identity: for standalone mutations the SAME operation
        # id is used by the desktop operation journal and by the provenance
        # attribute written inside the same script execution.
        journal_operation_id: str | None = None
        if effective_bundle_group == "mutate" and is_mutation:
            journal_operation_id = f"op_{uuid.uuid4().hex[:12]}"
        if effective_bundle_group == "mutate" and op in _METADATA_OPS:
            self._prepare_metadata_payload(
                payload, op, operation_id=journal_operation_id
            )
        if effective_bundle_group == "mutate" and domain_group == "style":
            self._prepare_style_payload(payload, op, journal_operation_id)
        if effective_bundle_group == "transaction" and op == "stage":
            action = payload.get("action")
            if isinstance(action, dict) and action.get("action_type") == "text_create":
                tx_id = str(payload["transaction_id"])
                provenance_operation_id = (
                    f"op_{uuid.uuid5(uuid.NAMESPACE_URL, tx_id).hex[:12]}"
                )
                journal_operation_id = f"op_{uuid.uuid4().hex[:12]}"
                while journal_operation_id == provenance_operation_id:
                    journal_operation_id = f"op_{uuid.uuid4().hex[:12]}"
                plan_action = dict(action)
                plan_action.update(
                    {
                        "operation": "text_create",
                        "transaction_id": tx_id,
                        "document_ref": payload.get("document_ref"),
                    }
                )
                self._prepare_style_payload(
                    plan_action, "text_create", provenance_operation_id
                )
                payload["action"] = plan_action
        if effective_bundle_group == "transaction" and op == "commit":
            transaction = self._transaction_store.find(str(payload["transaction_id"]))
            if transaction is not None and transaction.plan:
                provenance = transaction.plan[0].get("provenance")
                if isinstance(provenance, Mapping):
                    operation_id = provenance.get("operation_id")
                    if isinstance(operation_id, str):
                        journal_operation_id = operation_id

        if effective_bundle_group == "view" and op == "pick":
            self._prepare_pick_payload(payload, node_id)

        if effective_bundle_group == "read" and op == "entity":
            raw_ref = payload.get("ref")
            if isinstance(raw_ref, str) and re.match(ENTITY_REF_PATTERN, raw_ref):
                doc_ref = (
                    payload.get("document_ref")
                    or self._revision_tracker.active_document_ref
                )
                record = (
                    self._ref_registry.get_internal_record(raw_ref, doc_ref)
                    if doc_ref is not None
                    else self._ref_registry.get_internal_record(raw_ref)
                )
                if record is None and doc_ref is not None:
                    other = self._ref_registry.get_internal_record(raw_ref)
                    if other is not None and other.document_ref != doc_ref:
                        raise FusionCadError(
                            ErrorCode.WRONG_DOCUMENT,
                            "Entity ref belongs to a different document than the effective read context",
                            details={"ref": raw_ref, "active_document_ref": doc_ref},
                        )
                if record is not None:
                    if not record.native_token:
                        raise FusionCadError(
                            ErrorCode.CAPABILITY_UNAVAILABLE,
                            "Entity ref has no native resolution hint; exact read resolution is unavailable",
                            details={"ref": raw_ref, "document_ref": record.document_ref},
                        )
                    payload.update(
                        {
                            "ref": record.ref,
                            "kind": record.kind,
                            "name": record.name,
                            "native_token": record.native_token,
                            "component_path": list(record.component_path),
                            "geometry_signature": (
                                dict(record.geometry_signature)
                                if record.geometry_signature
                                else None
                            ),
                        }
                    )

        # Inspection targets known to this service get exact native resolution hints;
        # view zoom/orient target operations reuse the exact Task5/Task7 ref machinery.
        if effective_bundle_group == "inspect" or (
            effective_bundle_group == "view" and op in ("zoom_entity", "orient_to_face")
        ):
            self._inject_inspect_target_hints(payload)

        script = self._script_bundle.build(effective_bundle_group, payload)
        # `read:capabilities` is publicly non-mutating, but its runtime probe
        # contains an empty PTransaction Start/Abort discriminator.  Treat only
        # the durable transport/journal entry as mutation-sensitive so an
        # uncertain Start/Abort outcome is never replayed as an ordinary read.
        journal_mutation = is_mutation or (
            effective_bundle_group == "read" and op == "capabilities"
        )
        checkpoint: dict[str, Any] = {
            "operation": op,
            "group": effective_bundle_group,
            "transaction_id": payload.get("transaction_id"),
            "document_ref": payload.get("document_ref"),
        }
        if is_async:
            # Terminal async finalization must use the same service-prepared
            # semantic request context that was dispatched. Persist only the
            # public/sanitized shape so adapter-private native tokens and
            # secret-like values never enter the durable operation journal.
            checkpoint["finalization_payload"] = self._finalization_context(
                payload, group=effective_bundle_group, operation=op
            )
        journal = {
            "mutation": journal_mutation,
            "summary": summary,
            "checkpoint": checkpoint,
        }
        if journal_operation_id is not None:
            journal["operation_id"] = journal_operation_id

        # Authoritative DesktopNodeService session_generation captured before dispatching read:capabilities
        probe_generation: int | None = None
        if effective_bundle_group == "read" and op == "capabilities":
            try:
                probe_generation = self._desktop_nodes.get_session_generation(node_id)
            except (BridgeError, AttributeError):
                probe_generation = None

        if is_async:
            try:
                sub_result = await self._desktop_nodes.submit(
                    node_id,
                    "fusion_mcp_execute",
                    {"script": script},
                    journal=journal,
                )
            except FusionCadError as exc:
                if exc.code == ErrorCode.REVISION_CONFLICT:
                    cur_fp = (
                        exc.details.get("current_fingerprint")
                        if isinstance(exc.details, (dict, Mapping))
                        else None
                    )
                    doc_ref = (
                        exc.details.get("document_ref")
                        if isinstance(exc.details, (dict, Mapping))
                        else None
                    )
                    doc_ref = doc_ref or self._revision_tracker.active_document_ref
                    if cur_fp and doc_ref:
                        self._revision_tracker.observe(doc_ref, cur_fp)
                raise

            if isinstance(sub_result, dict):
                if self._is_error_payload(sub_result):
                    err_code, err_msg, err_details = self._extract_error_info(
                        sub_result
                    )
                    if err_code == ErrorCode.REVISION_CONFLICT:
                        cur_fp = (
                            err_details.get("current_fingerprint")
                            if isinstance(err_details, (dict, Mapping))
                            else None
                        )
                        doc_ref = (
                            err_details.get("document_ref")
                            if isinstance(err_details, (dict, Mapping))
                            else None
                        )
                        doc_ref = doc_ref or self._revision_tracker.active_document_ref
                        if cur_fp and doc_ref:
                            self._revision_tracker.observe(doc_ref, cur_fp)
                    raise FusionCadError(
                        err_code, err_msg, retryable=False, details=err_details
                    )

                # If sub_result is queued/running/claimed:
                # Represent pending truthfully; NEVER manufacture or discard authoritative transaction state!
                if sub_result.get("status") in ("queued", "running", "claimed"):
                    return sub_result

                # If sub_result was already a completed terminal execution (e.g. from a test mock):
                if (
                    "content" in sub_result
                    or sub_result.get("status") in ("succeeded", "late_succeeded")
                    or sub_result.get("api_version") == "fusion.cad/v1"
                ):
                    cad_res = self.decode_domain_result(sub_result)
                    return self._finalize_completed_execution(
                        cad_res,
                        effective_bundle_group=effective_bundle_group,
                        op=op,
                        payload=payload,
                        begin_tx_id=_begin_tx_id if is_transaction_begin else None,
                        begin_doc_ref=_begin_doc_ref if is_transaction_begin else None,
                        node_id=node_id,
                    )

            return sub_result

        try:
            raw_result = await self._desktop_nodes.call(
                node_id,
                "fusion_mcp_execute",
                {"script": script},
                journal=journal,
            )
        except FusionCadError as exc:
            if exc.code == ErrorCode.REVISION_CONFLICT:
                cur_fp = (
                    exc.details.get("current_fingerprint")
                    if isinstance(exc.details, (dict, Mapping))
                    else None
                )
                doc_ref = (
                    exc.details.get("document_ref")
                    if isinstance(exc.details, (dict, Mapping))
                    else None
                )
                doc_ref = doc_ref or self._revision_tracker.active_document_ref
                if cur_fp and doc_ref:
                    self._revision_tracker.observe(doc_ref, cur_fp)
            raise

        if not isinstance(raw_result, dict):
            raise FusionCadError(
                ErrorCode.FUSION_API_ERROR,
                "Unexpected non-dict result type from desktop node",
                details={"parsed_type": trusted_detail(type(raw_result).__name__)},
            )

        # Handle external_result reference already returned by desktop node.
        # The retained workstation artifact is raw adapter evidence; replace it
        # with the finalized public payload so native/private fields cannot leak.
        if "external_result" in raw_result:
            full, _ = self._desktop_nodes.external_result(raw_result["external_result"])
            cad_result = self.decode_domain_result(full)
            finalized = self._finalize_completed_execution(
                cad_result,
                effective_bundle_group=effective_bundle_group,
                op=op,
                payload=payload,
                begin_tx_id=_begin_tx_id if is_transaction_begin else None,
                begin_doc_ref=_begin_doc_ref if is_transaction_begin else None,
                node_id=node_id,
            )
            if (
                isinstance(finalized, dict)
                and isinstance(finalized.get("external_result"), dict)
            ):
                return finalized
            public_payload = (
                finalized.model_dump(mode="python", exclude_none=True)
                if isinstance(finalized, CadResult)
                else finalized
            )
            self._desktop_nodes.overwrite_external_result(
                raw_result["external_result"], public_payload
            )
            return raw_result

        try:
            cad_result = self.decode_domain_result(raw_result)
        except FusionCadError as exc:
            if exc.code == ErrorCode.REVISION_CONFLICT:
                cur_fp = (
                    exc.details.get("current_fingerprint")
                    if isinstance(exc.details, (dict, Mapping))
                    else None
                )
                doc_ref = (
                    exc.details.get("document_ref")
                    if isinstance(exc.details, (dict, Mapping))
                    else None
                )
                doc_ref = doc_ref or self._revision_tracker.active_document_ref
                if cur_fp and doc_ref:
                    self._revision_tracker.observe(doc_ref, cur_fp)
            raise

        # If operation was capabilities read, persist the probed capability matrix
        # only if the authoritative session_generation is still current.
        if effective_bundle_group == "read" and op == "capabilities":
            if cad_result.capabilities:
                current_gen: int | None = None
                try:
                    current_gen = self._desktop_nodes.get_session_generation(node_id)
                except (BridgeError, AttributeError):
                    current_gen = None

                if probe_generation is not None and current_gen == probe_generation:
                    identity = None
                    if isinstance(cad_result.data, (dict, Mapping)):
                        try:
                            data_dict = dict(cad_result.data)
                            if (
                                "local_tool" not in data_dict
                                or data_dict["local_tool"] is None
                            ):
                                data_dict["local_tool"] = "fusion_mcp_execute"
                            if (
                                "implementation" not in data_dict
                                or data_dict["implementation"] is None
                            ):
                                data_dict["implementation"] = "fusion-desktop-mcp"
                            identity = FusionRuntimeIdentity.model_validate(data_dict)
                        except (ValidationError, ValueError, TypeError):
                            identity = None
                    matrix = CapabilityMatrix.from_records(
                        cad_result.capabilities,
                        identity=identity,
                    )
                    self.set_node_capabilities(
                        node_id, matrix, generation=probe_generation
                    )
                else:
                    # Generation changed during in-flight probe: discard result, leave unprobed/fail-closed
                    self._node_capabilities.pop(node_id, None)
            else:
                self._node_capabilities.pop(node_id, None)

        return self._finalize_completed_execution(
            cad_result,
            effective_bundle_group=effective_bundle_group,
            op=op,
            payload=payload,
            begin_tx_id=_begin_tx_id if is_transaction_begin else None,
            begin_doc_ref=_begin_doc_ref if is_transaction_begin else None,
            node_id=node_id,
        )
