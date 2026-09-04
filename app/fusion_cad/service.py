from __future__ import annotations

import base64
import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from app.api.errors import BridgeError, ErrorCode
from app.desktop_nodes.service import DesktopNodeService
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
)
from app.fusion_cad.scripts import FusionCadScriptBundle

_BASE64_MAGIC_PREFIXES: tuple[str, ...] = (
    "iVBORw0KGgo",  # PNG
    "/9j/",          # JPEG
    "R0lGOD",        # GIF
    "UklGR",         # WEBP
    "Qk",            # BMP
    "JVBERi0",       # PDF
    "UEsDB",         # ZIP / 3MF
)

_BINARY_MIME_PREFIXES: tuple[str, ...] = (
    "image/",
    "audio/",
    "video/",
    "model/",
)

_BINARY_MIME_EXACT: frozenset[str] = frozenset({
    "application/octet-stream",
    "application/pdf",
    "application/zip",
    "application/x-step",
    "application/sla",
    "application/vnd.ms-pki.stl",
    "application/step",
    "application/3mf",
})

_BINARY_KEY_SUFFIXES: tuple[str, ...] = (
    "_b64",
    "_base64",
    "Base64",
    "_binary",
    "_bytes",
    "_blob",
)

_BINARY_KEY_EXACT: frozenset[str] = frozenset({
    "data",
    "base64Data",
    "base64_data",
    "b64_data",
    "image_data",
    "binary_data",
    "raw_bytes",
    "thumbnail_b64",
    "screenshot_b64",
    "png_base64",
    "jpg_base64",
    "jpeg_base64",
    "stl_base64",
    "step_base64",
    "mesh_data",
    "buffer",
})


def _is_mime_binary(mime: Any) -> bool:
    if not isinstance(mime, str):
        return False
    mime_lower = mime.lower().strip()
    return mime_lower.startswith(_BINARY_MIME_PREFIXES) or mime_lower in _BINARY_MIME_EXACT


def _has_image_or_binary_data(value: Any) -> bool:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return True

    if isinstance(value, str):
        str_val = value.strip()
        if str_val.startswith("data:") and (
            ";base64," in str_val
            or any(prefix in str_val for prefix in ("image/", "model/", "application/octet-stream", "application/pdf"))
        ):
            return True
        if len(str_val) >= 16:
            for prefix in _BASE64_MAGIC_PREFIXES:
                if str_val.startswith(prefix):
                    return True
        if len(str_val) >= 64 and len(str_val) % 4 == 0 and re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", str_val):
            try:
                decoded = base64.b64decode(str_val, validate=True)
                if any(b == 0 or b > 127 for b in decoded[:32]):
                    return True
            except (ValueError, TypeError):
                pass
        return False

    if isinstance(value, dict):
        val_type = value.get("type")
        if isinstance(val_type, str) and val_type.lower() in ("image", "binary", "blob"):
            return True
        mime = value.get("mimeType") or value.get("mime_type") or value.get("contentType") or value.get("content_type")
        if _is_mime_binary(mime):
            return True
        encoding = value.get("encoding") or value.get("transfer_encoding")
        if isinstance(encoding, str) and encoding.lower() in ("base64", "binary", "hex"):
            return True
        for k, v in value.items():
            if isinstance(k, str) and (k in _BINARY_KEY_EXACT or k.endswith(_BINARY_KEY_SUFFIXES)):
                if isinstance(v, (bytes, bytearray, memoryview)):
                    return True
                if isinstance(v, str) and len(v.strip()) > 0:
                    return True
            if _has_image_or_binary_data(v):
                return True
        return False

    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            if _has_image_or_binary_data(item):
                return True

    return False


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

    # 3. fusion_view (camera mutations are state-changing view operations; screenshot is async)
    ("view", "camera_read"): (False, False),
    ("view", "pick"): (False, False),
    ("view", "camera_set"): (False, True),
    ("view", "fit"): (False, True),
    ("view", "zoom_entity"): (False, True),
    ("view", "orient_to_face"): (False, True),
    ("view", "standard_view"): (False, True),
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
    ("transaction", "begin"): (False, False),
    ("transaction", "stage"): (False, False),
    ("transaction", "status"): (False, False),
    ("transaction", "abort"): (False, False),
    ("transaction", "preview"): (True, False),
    ("transaction", "commit"): (True, True),
    ("transaction", "rollback"): (True, True),
}


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
        return "read"

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
        if isinstance(request, BaseModel):
            node_id = getattr(request, "node_id", None)
            resolved_group = group or self._resolve_group(request)
            payload = request.model_dump(mode="json", exclude_none=True)
        elif isinstance(request, dict):
            node_id = request.get("node_id")
            resolved_group = group or "read"
            payload = dict(request)
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

        is_async, is_mutation, summary = self._classify_operation(resolved_group, payload)
        script = self._script_bundle.build(resolved_group, payload)
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

        # Handle native execution error (isError: True)
        if raw_result.get("isError") is True:
            err_msg = "Native Fusion CAD execution failed"
            err_details: dict[str, Any] = {"raw_result": raw_result}
            err_code = ErrorCode.FUSION_API_ERROR

            if isinstance(raw_result.get("content"), list):
                for block in raw_result["content"]:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        try:
                            parsed_err = json.loads(text)
                            if isinstance(parsed_err, dict):
                                if parsed_err.get("status") == "failed" or "error" in parsed_err:
                                    e = parsed_err.get("error", {})
                                    code_str = e.get("code") or parsed_err.get("code")
                                    if code_str:
                                        try:
                                            err_code = ErrorCode(str(code_str))
                                        except ValueError:
                                            err_code = ErrorCode.FUSION_API_ERROR
                                    err_msg = e.get("message") or parsed_err.get("message") or err_msg
                                    err_details = e.get("details") or parsed_err.get("details") or err_details
                                    break
                                elif "message" in parsed_err:
                                    err_msg = str(parsed_err["message"])
                                    err_details = parsed_err
                                    break
                        except (ValueError, TypeError):
                            if text:
                                err_msg = text
                                break
            elif "message" in raw_result:
                err_msg = str(raw_result["message"])
            elif "error" in raw_result:
                err_msg = str(raw_result["error"])

            raise FusionCadError(err_code, err_msg, details=err_details)

        # Handle external_result reference already returned by desktop node
        if "external_result" in raw_result:
            return raw_result

        # Check for inline binary/image data in the raw result
        if _has_image_or_binary_data(raw_result):
            try:
                return self._desktop_nodes.store_external_result(node_id, raw_result)
            except Exception as exc:
                raise BridgeError(
                    ErrorCode.INTERNAL_ERROR,
                    f"Failed to externalize binary result payload: {exc}",
                ) from exc

        # Process MCP content blocks
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

                    if parsed.get("status") == "failed" or "error" in parsed:
                        err = parsed.get("error", {})
                        code_str = err.get("code") or parsed.get("code", "FUSION_API_ERROR")
                        try:
                            code = ErrorCode(str(code_str))
                        except ValueError:
                            code = ErrorCode.FUSION_API_ERROR
                        raise FusionCadError(
                            code,
                            err.get("message") or parsed.get("message", "CAD operation failed"),
                            details=err.get("details") or parsed.get("details", {}),
                        )

                    if _has_image_or_binary_data(parsed):
                        try:
                            return self._desktop_nodes.store_external_result(node_id, parsed)
                        except Exception as exc:
                            raise BridgeError(
                                ErrorCode.INTERNAL_ERROR,
                                f"Failed to externalize binary result payload: {exc}",
                            ) from exc

                    if parsed.get("api_version") != "fusion.cad/v1":
                        raise FusionCadError(
                            ErrorCode.FUSION_API_ERROR,
                            f"Unrecognized domain output from native Fusion script: expected api_version 'fusion.cad/v1', got {parsed.get('api_version')!r}",
                            details={"parsed": parsed},
                        )

                    try:
                        return CadResult.model_validate(parsed)
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

        # Fallback if raw_result was a bare dictionary (e.g. direct CAD result without content wrapper)
        if raw_result.get("api_version") == "fusion.cad/v1":
            try:
                return CadResult.model_validate(raw_result)
            except ValidationError as exc:
                raise FusionCadError(
                    ErrorCode.FUSION_API_ERROR,
                    f"Invalid fusion.cad/v1 response schema: {exc}",
                    details={"validation_errors": exc.errors()},
                ) from exc

        raise FusionCadError(
            ErrorCode.FUSION_API_ERROR,
            "Unrecognized domain output format from native Fusion script",
            details={"raw_result": raw_result},
        )
