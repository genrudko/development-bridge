from __future__ import annotations

import json
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
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.models import CadResult, DocumentState
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
    ) -> None:
        self._desktop_nodes = desktop_nodes
        self._script_bundle = script_bundle or FusionCadScriptBundle()
        self._revision_tracker = revision_tracker or RevisionTracker()
        self._node_capabilities: dict[str, _CachedNodeCapabilities] = {}

    @property
    def revision_tracker(self) -> RevisionTracker:
        return self._revision_tracker

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
        self._node_capabilities[node_id] = _CachedNodeCapabilities(matrix=matrix, session_generation=target_gen)

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
            for prefix in ("read", "inspect", "view", "mutate", "validate", "transaction")
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
    def _extract_error_info(cls, payload: dict[str, Any]) -> tuple[ErrorCode, str, dict[str, Any]]:
        err_msg = "Native Fusion CAD execution failed"
        err_details: dict[str, Any] = {"raw": payload}
        err_code = ErrorCode.FUSION_API_ERROR

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
                            err = parsed.get("error") if isinstance(parsed.get("error"), dict) else {}
                            code_str = err.get("code") or parsed.get("code")
                            if code_str:
                                try:
                                    err_code = ErrorCode(str(code_str))
                                except ValueError:
                                    err_code = ErrorCode.FUSION_API_ERROR
                            err_msg = err.get("message") or parsed.get("message") or err_msg
                            err_details = err.get("details") or parsed.get("details") or parsed
                            return err_code, str(err_msg), err_details
                    except (ValueError, TypeError):
                        if text:
                            err_msg = text
                            return err_code, err_msg, err_details

        if "error" in payload:
            err = payload["error"]
            if isinstance(err, dict):
                code_str = err.get("code") or payload.get("code")
                if code_str:
                    try:
                        err_code = ErrorCode(str(code_str))
                    except ValueError:
                        err_code = ErrorCode.FUSION_API_ERROR
                err_msg = err.get("message") or payload.get("message") or err_msg
                err_details = err.get("details") or payload.get("details") or err
            elif isinstance(err, str):
                err_msg = err
            return err_code, str(err_msg), err_details

        if "message" in payload:
            err_msg = str(payload["message"])
            code_str = payload.get("code")
            if code_str:
                try:
                    err_code = ErrorCode(str(code_str))
                except ValueError:
                    err_code = ErrorCode.FUSION_API_ERROR
            return err_code, err_msg, payload

        return err_code, err_msg, err_details

    @classmethod
    def decode_domain_result(cls, raw_result: Any) -> CadResult:
        """Decode and validate a domain result against fusion.cad/v1 CadResult schema.

        Fails closed on malformed JSON, isError=True, non-bool isError, failed/error status,
        missing or incorrect api_version, invalid CadResult schema, or non-dict structures.
        """
        if not isinstance(raw_result, dict):
            raise FusionCadError(
                ErrorCode.FUSION_API_ERROR,
                f"Unexpected non-dict result type from desktop node: {type(raw_result).__name__}",
                details={"raw_result": str(raw_result)},
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
                    details={"raw_result": raw_result},
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
                            details={"block": block},
                        )
                    try:
                        parsed = json.loads(text)
                    except (ValueError, TypeError) as exc:
                        raise FusionCadError(
                            ErrorCode.FUSION_API_ERROR,
                            f"Malformed non-JSON output from native Fusion script: {text[:200]}",
                            details={"raw_output": text},
                        ) from exc

                    if not isinstance(parsed, dict):
                        raise FusionCadError(
                            ErrorCode.FUSION_API_ERROR,
                            f"Invalid domain output type (expected JSON object, got {type(parsed).__name__})",
                            details={"raw_output": text},
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
                            f"Unrecognized domain output from native Fusion script: expected api_version 'fusion.cad/v1', got {parsed.get('api_version')!r}",
                            details={"parsed": parsed},
                        )

                    candidate = dict(parsed)
                    candidate.pop("isError", None)
                    try:
                        return CadResult.model_validate(candidate)
                    except ValidationError as exc:
                        raise FusionCadError(
                            ErrorCode.FUSION_API_ERROR,
                            f"Invalid fusion.cad/v1 response schema: {exc}",
                            details={"validation_errors": exc.errors()},
                        ) from exc

            raise FusionCadError(
                ErrorCode.FUSION_API_ERROR,
                "No valid CAD text output found in native execution content",
                details={"raw_result": raw_result},
            )

        if raw_result.get("status") in ("failed", "error") or "error" in raw_result:
            err_code, err_msg, err_details = cls._extract_error_info(raw_result)
            raise FusionCadError(err_code, err_msg, details=err_details)

        if raw_result.get("api_version") == "fusion.cad/v1":
            candidate = dict(raw_result)
            candidate.pop("isError", None)
            try:
                return CadResult.model_validate(candidate)
            except ValidationError as exc:
                raise FusionCadError(
                    ErrorCode.FUSION_API_ERROR,
                    f"Invalid fusion.cad/v1 response schema: {exc}",
                    details={"validation_errors": exc.errors()},
                ) from exc

        raise FusionCadError(
            ErrorCode.FUSION_API_ERROR,
            "Unrecognized domain output format from native Fusion script: missing or invalid api_version 'fusion.cad/v1'",
            details={"raw_result": raw_result},
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
        cad_result = result if isinstance(result, CadResult) else self.decode_domain_result(result)

        # 0. Pre-validate transaction commit / abort / rollback before observing or mutating tracker state
        if effective_bundle_group == "transaction" and op in ("commit", "abort", "rollback"):
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
                    f"No stored baseline for transaction '{tx_id}'; call transaction:begin first",
                    details={"transaction_id": tx_id, "operation": op},
                )
            if stored_baseline is not None:
                if cad_result.status != "succeeded":
                    raise FusionCadError(
                        ErrorCode.FUSION_API_ERROR,
                        f"Transaction '{tx_id}' {op} failed or incomplete (status='{cad_result.status}'); preserving stored baseline",
                        details={"transaction_id": tx_id, "operation": op, "status": cad_result.status},
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
                        details={"transaction_id": tx_id, "operation": op, "applied": applied_val},
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
                        details={"transaction_id": tx_id, "operation": op, "document_ref": res_doc},
                    )
                if op in ("abort", "rollback") and res_fp != stored_baseline["baseline_fingerprint"]:
                    raise FusionCadError(
                        ErrorCode.REVISION_CONFLICT,
                        f"Transaction '{tx_id}' {op} result fingerprint '{res_fp}' diverged from stored baseline; preserving stored baseline",
                        details={
                            "transaction_id": tx_id,
                            "operation": op,
                            "document_ref": res_doc,
                            "result_fingerprint": res_fp,
                            "baseline_fingerprint": stored_baseline["baseline_fingerprint"],
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
                or (cad_result.data.get("document_ref") if isinstance(cad_result.data, (dict, Mapping)) else None)
                or begin_doc_ref
                or payload.get("document_ref")
                or self._revision_tracker.active_document_ref
            )
            observed_rec = None
            if target_doc and fp and isinstance(fp, str) and fp.strip():
                observed_rec = self._revision_tracker.observe(target_doc, fp.strip())
                doc_name = (
                    cad_result.document.name if cad_result.document
                    else (cad_result.data.get("name") if isinstance(cad_result.data, (dict, Mapping)) else None)
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
            elif target_doc and cad_result.document and cad_result.document.model_revision:
                observed_rec = self._revision_tracker.current(target_doc)

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

                if not target_doc or not isinstance(target_doc, str) or not target_doc.strip():
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
                if not proven_fp or not isinstance(proven_fp, str) or not proven_fp.strip():
                    raise FusionCadError(
                        ErrorCode.FUSION_API_ERROR,
                        "transaction:begin terminal success with missing, empty, or whitespace real fingerprint; failing closed to prevent unusable baseline",
                        details={"transaction_id": tx_id, "document_ref": target_doc, "fingerprint": proven_fp},
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
                if isinstance(cad_result.data, dict) and tx_id:
                    cad_result.data["transaction_id"] = tx_id
                cad_result = cad_result.model_copy(
                    update={
                        "document": DocumentState(
                            document_ref=target_doc,
                            model_revision=rec.revision,
                            name=cad_result.document.name if cad_result.document else None,
                            units="mm",
                        )
                    }
                )

            # 3. Transaction commit / abort / rollback: clear stored baseline ONLY after proven terminal execution
            if effective_bundle_group == "transaction" and op in ("commit", "abort", "rollback"):
                tx_id = payload.get("transaction_id")
                if isinstance(cad_result.data, (dict, Mapping)) and not tx_id:
                    tx_id = cad_result.data.get("transaction_id")
                if tx_id:
                    self._revision_tracker.clear_transaction(tx_id)

            domain_payload = cad_result.model_dump(mode="python", exclude_none=True)
            if node_id and has_binary_data(domain_payload):
                try:
                    return self._desktop_nodes.store_external_result(node_id, domain_payload)
                except Exception as exc:
                    raise BridgeError(
                        ErrorCode.INTERNAL_ERROR,
                        f"Failed to externalize binary result payload: {exc}",
                    ) from exc

            if isinstance(result, dict) and not isinstance(result, CadResult):
                return cad_result.model_dump(mode="python", exclude_none=True)
            return cad_result
        except Exception:
            self._revision_tracker.restore(tracker_snapshot)
            raise

    def finalize_terminal_operation(
        self,
        op_status: dict[str, Any],
        full_result: Any,
    ) -> CadResult:
        """Finalize a terminal desktop operation from the durable operation lifecycle.

        Persists authoritative baseline for transaction:begin or clears baseline
        for commit/abort/rollback ONLY after proven successful terminal execution.
        Failed, uncertain, or queued operations fail closed and do not manufacture
        or discard authoritative transaction state.
        """
        status = op_status.get("status")
        if status not in ("succeeded", "late_succeeded"):
            if self._is_error_payload(full_result):
                err_code, err_msg, err_details = self._extract_error_info(full_result)
                raise FusionCadError(err_code, err_msg, retryable=False, details=err_details)
            raise FusionCadError(
                ErrorCode.FUSION_API_ERROR,
                f"Cannot finalize incomplete or non-succeeded operation (status='{status}')",
                details={"status": status, "operation_id": op_status.get("operation_id")},
            )

        if self._is_error_payload(full_result):
            err_code, err_msg, err_details = self._extract_error_info(full_result)
            raise FusionCadError(err_code, err_msg, retryable=False, details=err_details)

        cad_result = self.decode_domain_result(full_result)
        checkpoint = op_status.get("checkpoint") or {}
        summary = str(op_status.get("summary") or "")

        group = checkpoint.get("group")
        op = checkpoint.get("operation")
        if (not group or not op) and ":" in summary:
            parts = summary.split(":", 1)
            group = group or parts[0]
            op = op or parts[1]

        effective_bundle_group = "mutate" if group in ("metadata", "style") else (group or "")
        tx_id = checkpoint.get("transaction_id") or (
            cad_result.data.get("transaction_id") if isinstance(cad_result.data, (dict, Mapping)) else None
        )
        doc_ref = checkpoint.get("document_ref")

        self._finalize_completed_execution(
            cad_result,
            effective_bundle_group=effective_bundle_group,
            op=op or "",
            payload=checkpoint,
            begin_tx_id=tx_id if (effective_bundle_group == "transaction" and op == "begin") else None,
            begin_doc_ref=doc_ref,
        )
        return cad_result

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
    def _validate_request_dict(cls, request_dict: dict[str, Any], group: str | None = None) -> tuple[BaseModel, str]:
        if not isinstance(request_dict, dict):
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                f"Expected request to be a dict, got {type(request_dict).__name__}",
            )
        op = request_dict.get("operation")
        if not op or not isinstance(op, str):
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "Operation name is required in request payload",
                details={"request": request_dict},
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
            elif op in ("begin", "stage", "preview", "commit", "rollback", "abort", "status"):
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
            elif op in ("get", "remove", "tag", "untag", "set_role", "clear_role", "provenance"):
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
                raise BridgeError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"Unknown operation '{op}' in request payload",
                    details={"operation": op},
                )

        if target_group == "mutate":
            if (
                op in ("get", "remove", "tag", "untag", "set_role", "clear_role", "provenance")
                or (op == "set" and "name" in request_dict)
                or (op == "query" and "selector" not in request_dict)
            ):
                adapter = _GROUP_REQUEST_ADAPTERS["metadata"]
            else:
                adapter = _GROUP_REQUEST_ADAPTERS["style"]
            bundle_group = "mutate"
        elif target_group in _GROUP_REQUEST_ADAPTERS:
            adapter = _GROUP_REQUEST_ADAPTERS[target_group]
            bundle_group = "mutate" if target_group in ("metadata", "style") else target_group
        else:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                f"Unknown request group '{target_group}'",
                details={"group": target_group},
            )

        try:
            validated = adapter.validate_python(request_dict)
            return validated, target_group, bundle_group
        except ValidationError as exc:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                f"Invalid {target_group} request payload: {exc}",
                details={"validation_errors": exc.errors()},
            ) from exc

    def _classify_operation(self, group: str, payload: dict[str, Any]) -> tuple[bool, bool, str]:
        op = str(payload.get("operation", ""))
        if not op:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Operation name is required in request payload")
        summary = f"{group}:{op}"

        effective_group = "mutate" if group in ("metadata", "style") else group

        if effective_group == "read" and op == "model_snapshot":
            is_async = (payload.get("detail") == "full" or bool(payload.get("include_views")))
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
            effective_bundle_group = "mutate" if domain_group in ("metadata", "style") else domain_group
            node_id = request.node_id
            payload = request.model_dump(mode="json", exclude_none=True)
        elif isinstance(request, BaseModel):
            validated_model, domain_group, effective_bundle_group = self._validate_request_dict(
                request.model_dump(mode="python", exclude_none=True),
                group=group,
            )
            node_id = validated_model.node_id  # type: ignore[union-attr]
            payload = validated_model.model_dump(mode="json", exclude_none=True)
        elif isinstance(request, dict):
            validated_model, domain_group, effective_bundle_group = self._validate_request_dict(request, group=group)
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

        # Enforce capability-first dispatch before script generation or execution
        op = str(payload.get("operation", ""))
        required_cap = get_required_capability(domain_group, op, payload)
        if required_cap is not None:
            matrix = self.get_node_capabilities(node_id)
            if matrix is None:
                raise FusionCadError(
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                    f"Node '{node_id}' capability state is unprobed; invoke fusion_read(operation='capabilities') first",
                    retryable=False,
                    details={"node_id": node_id, "capability": required_cap},
                )
            matrix.require(required_cap, allow_degraded=False)

        is_async, is_mutation, summary = self._classify_operation(effective_bundle_group, payload)

        is_standalone_mutation = (effective_bundle_group == "mutate") and is_mutation
        is_transaction_preview_commit = (effective_bundle_group == "transaction") and (op in ("preview", "commit"))

        # Every mutation/preview/commit must require supported atomic revision safety
        if is_standalone_mutation or is_transaction_preview_commit:
            matrix = self.get_node_capabilities(node_id)
            if matrix is None:
                raise FusionCadError(
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                    f"Node '{node_id}' capability state is unprobed; invoke fusion_read(operation='capabilities') first",
                    retryable=False,
                    details={"node_id": node_id, "capability": "revision.external_change_detection"},
                )
            matrix.require("revision.external_change_detection", allow_degraded=False)

        # Every standalone mutation must require expected_revision and reject missing revision
        if is_standalone_mutation and not payload.get("expected_revision"):
                raise FusionCadError(
                    ErrorCode.REVISION_CONFLICT,
                    f"expected_revision is required for standalone mutation '{op}'",
                    details={
                        "document_ref": payload.get("document_ref") or self._revision_tracker.active_document_ref,
                        "expected_revision": None,
                        "operation": op,
                    },
                )

        # Finding 1: Transaction preview/commit must bind to stored baseline,
        # not caller-selected expected_revision, to prevent freshness bypass.
        # Staging also remains bound to stored transaction baseline.
        is_transaction_begin = (effective_bundle_group == "transaction") and (op == "begin")
        is_transaction_preview_commit = (effective_bundle_group == "transaction") and (op in ("preview", "commit"))
        is_transaction_stage = (effective_bundle_group == "transaction") and (op == "stage")
        if is_transaction_stage or is_transaction_preview_commit:
            tx_id = payload.get("transaction_id")
            if not tx_id:
                raise FusionCadError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"transaction_id is required for transaction {op}",
                )
            stored_baseline = self._revision_tracker.get_transaction_baseline(tx_id)
            if stored_baseline is None:
                raise FusionCadError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"No stored baseline for transaction '{tx_id}'; call transaction:begin first",
                    details={"transaction_id": tx_id, "operation": op},
                )
            if payload.get("document_ref") and payload["document_ref"] != stored_baseline["document_ref"]:
                raise FusionCadError(
                    ErrorCode.WRONG_DOCUMENT,
                    f"Transaction '{tx_id}' is bound to document '{stored_baseline['document_ref']}', but request specified '{payload['document_ref']}'; transaction operations cannot switch documents",
                    details={"transaction_id": tx_id, "bound_document": stored_baseline["document_ref"], "requested_document": payload["document_ref"]},
                )
            # Override expected_revision/fingerprint with stored baseline
            payload["expected_revision"] = stored_baseline["baseline_revision"]
            payload["expected_fingerprint"] = stored_baseline["baseline_fingerprint"]
            payload["document_ref"] = stored_baseline["document_ref"]

        if op in ("abort", "rollback") and effective_bundle_group == "transaction":
            tx_id = payload.get("transaction_id")
            if not tx_id:
                raise FusionCadError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"transaction_id is required for transaction {op}",
                )
            stored_baseline = self._revision_tracker.get_transaction_baseline(tx_id)
            if stored_baseline is not None:
                if payload.get("document_ref") and payload["document_ref"] != stored_baseline["document_ref"]:
                    raise FusionCadError(
                        ErrorCode.WRONG_DOCUMENT,
                        f"Transaction '{tx_id}' is bound to document '{stored_baseline['document_ref']}', but request specified '{payload['document_ref']}'",
                        details={"transaction_id": tx_id, "bound_document": stored_baseline["document_ref"], "requested_document": payload["document_ref"]},
                    )
                payload["document_ref"] = stored_baseline["document_ref"]

        # Bridge revision freshness precheck (fail-fast optimization)
        if is_standalone_mutation or is_transaction_preview_commit:
            exp_rev = payload.get("expected_revision")
            doc_ref = payload.get("document_ref") or self._revision_tracker.active_document_ref
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

        # Transaction begin: persist baseline after execution succeeds (below)
        if is_transaction_begin:
            _begin_tx_id = payload.get("transaction_id")
            if not _begin_tx_id:
                import uuid
                _begin_tx_id = f"tx_{uuid.uuid4().hex[:12]}"
                payload["transaction_id"] = _begin_tx_id
            _begin_doc_ref = payload.get("document_ref") or self._revision_tracker.active_document_ref
            exp_rev = payload.get("expected_revision")
            if exp_rev is not None and _begin_doc_ref:
                self.assert_fresh_for_mutation(payload, document_ref=_begin_doc_ref)
                known_fp = self._revision_tracker.get_fingerprint(_begin_doc_ref, exp_rev)
                if known_fp is not None:
                    payload["expected_fingerprint"] = known_fp
                else:
                    payload.pop("expected_fingerprint", None)
            elif "expected_fingerprint" in payload:
                payload.pop("expected_fingerprint", None)

        # Remove caller-supplied synthetic authority
        payload.pop("mock_model_state", None)

        script = self._script_bundle.build(effective_bundle_group, payload)
        journal = {
            "mutation": is_mutation,
            "summary": summary,
            "checkpoint": {
                "operation": op,
                "group": effective_bundle_group,
                "transaction_id": payload.get("transaction_id"),
                "document_ref": payload.get("document_ref"),
            },
        }

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
                    cur_fp = exc.details.get("current_fingerprint") if isinstance(exc.details, (dict, Mapping)) else None
                    doc_ref = exc.details.get("document_ref") if isinstance(exc.details, (dict, Mapping)) else None
                    doc_ref = doc_ref or self._revision_tracker.active_document_ref
                    if cur_fp and doc_ref:
                        self._revision_tracker.observe(doc_ref, cur_fp)
                raise

            if isinstance(sub_result, dict):
                if self._is_error_payload(sub_result):
                    err_code, err_msg, err_details = self._extract_error_info(sub_result)
                    if err_code == ErrorCode.REVISION_CONFLICT:
                        cur_fp = err_details.get("current_fingerprint") if isinstance(err_details, (dict, Mapping)) else None
                        doc_ref = err_details.get("document_ref") if isinstance(err_details, (dict, Mapping)) else None
                        doc_ref = doc_ref or self._revision_tracker.active_document_ref
                        if cur_fp and doc_ref:
                            self._revision_tracker.observe(doc_ref, cur_fp)
                    raise FusionCadError(err_code, err_msg, retryable=False, details=err_details)

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
                    return self._finalize_completed_execution(
                        sub_result,
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
                cur_fp = exc.details.get("current_fingerprint") if isinstance(exc.details, (dict, Mapping)) else None
                doc_ref = exc.details.get("document_ref") if isinstance(exc.details, (dict, Mapping)) else None
                doc_ref = doc_ref or self._revision_tracker.active_document_ref
                if cur_fp and doc_ref:
                    self._revision_tracker.observe(doc_ref, cur_fp)
            raise

        if not isinstance(raw_result, dict):
            raise FusionCadError(
                ErrorCode.FUSION_API_ERROR,
                f"Unexpected non-dict result type from desktop node: {type(raw_result).__name__}",
                details={"raw_result": str(raw_result)},
            )

        # Handle external_result reference already returned by desktop node
        if "external_result" in raw_result:
            full, _ = self._desktop_nodes.external_result(raw_result["external_result"])
            cad_result = self.decode_domain_result(full)
            self._finalize_completed_execution(
                cad_result,
                effective_bundle_group=effective_bundle_group,
                op=op,
                payload=payload,
                begin_tx_id=_begin_tx_id if is_transaction_begin else None,
                begin_doc_ref=_begin_doc_ref if is_transaction_begin else None,
                node_id=node_id,
            )
            return raw_result

        try:
            cad_result = self.decode_domain_result(raw_result)
        except FusionCadError as exc:
            if exc.code == ErrorCode.REVISION_CONFLICT:
                cur_fp = exc.details.get("current_fingerprint") if isinstance(exc.details, (dict, Mapping)) else None
                doc_ref = exc.details.get("document_ref") if isinstance(exc.details, (dict, Mapping)) else None
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
                            if "local_tool" not in data_dict or data_dict["local_tool"] is None:
                                data_dict["local_tool"] = "fusion_mcp_execute"
                            if "implementation" not in data_dict or data_dict["implementation"] is None:
                                data_dict["implementation"] = "fusion-desktop-mcp"
                            identity = FusionRuntimeIdentity.model_validate(data_dict)
                        except (ValidationError, ValueError, TypeError):
                            identity = None
                    matrix = CapabilityMatrix.from_records(
                        cad_result.capabilities,
                        identity=identity,
                    )
                    self.set_node_capabilities(node_id, matrix, generation=probe_generation)
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
