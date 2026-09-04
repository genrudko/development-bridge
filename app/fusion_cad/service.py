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
from app.fusion_cad.models import CadResult
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
    ) -> None:
        self._desktop_nodes = desktop_nodes
        self._script_bundle = script_bundle or FusionCadScriptBundle()
        self._node_capabilities: dict[str, _CachedNodeCapabilities] = {}

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
        if generation is None:
            try:
                generation = self._desktop_nodes.get_session_generation(node_id)
            except (BridgeError, AttributeError):
                generation = 1
        self._node_capabilities[node_id] = _CachedNodeCapabilities(matrix=matrix, session_generation=generation)

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
        script = self._script_bundle.build(effective_bundle_group, payload)
        journal = {"mutation": is_mutation, "summary": summary}

        if is_async:
            return await self._desktop_nodes.submit(
                node_id,
                "fusion_mcp_execute",
                {"script": script},
                journal=journal,
            )

        raw_result = await self._desktop_nodes.call(
            node_id,
            "fusion_mcp_execute",
            {"script": script},
            journal=journal,
        )

        if not isinstance(raw_result, dict):
            raise FusionCadError(
                ErrorCode.FUSION_API_ERROR,
                f"Unexpected non-dict result type from desktop node: {type(raw_result).__name__}",
                details={"raw_result": str(raw_result)},
            )

        # Handle external_result reference already returned by desktop node
        if "external_result" in raw_result:
            full, _ = self._desktop_nodes.external_result(raw_result["external_result"])
            self.decode_domain_result(full)
            return raw_result

        cad_result = self.decode_domain_result(raw_result)

        # If operation was capabilities read, persist the probed capability matrix
        if effective_bundle_group == "read" and op == "capabilities" and cad_result.capabilities:
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
            self.set_node_capabilities(node_id, matrix)

        domain_payload = cad_result.model_dump(mode="python", exclude_none=True)
        if has_binary_data(domain_payload):
            try:
                return self._desktop_nodes.store_external_result(node_id, domain_payload)
            except Exception as exc:
                raise BridgeError(
                    ErrorCode.INTERNAL_ERROR,
                    f"Failed to externalize binary result payload: {exc}",
                ) from exc

        return cad_result
