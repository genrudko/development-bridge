from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

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


def _has_image_or_binary_data(value: Any) -> bool:
    if isinstance(value, (bytes, bytearray)):
        return True
    if isinstance(value, str):
        if value.startswith(("data:image/", "data:application/octet-stream")):
            return True
        if len(value) >= 32 and value.startswith(("iVBORw0KGgo", "/9j/", "R0lGOD", "UklGR")):
            return True

    elif isinstance(value, dict):
        if value.get("type") == "image":
            return True
        mime = value.get("mimeType") or value.get("mime_type")
        if isinstance(mime, str) and (mime.startswith("image/") or mime == "application/octet-stream"):
            return True
        for v in value.values():
            if _has_image_or_binary_data(v):
                return True
    elif isinstance(value, (list, tuple)):
        for item in value:
            if _has_image_or_binary_data(item):
                return True
    return False


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
        summary = f"{group}:{op}" if op else group

        if group == "read":
            if op == "model_snapshot":
                is_async = (payload.get("detail") == "full" or bool(payload.get("include_views")))
                return is_async, False, summary
            return False, False, summary

        if group == "inspect":
            return False, False, summary

        if group == "view":
            is_async = (op == "screenshot")
            return is_async, False, summary

        if group == "validate":
            is_async = (op == "run")
            return is_async, False, summary

        if group == "transaction":
            if op == "commit":
                return True, True, summary
            if op == "preview":
                return True, False, summary
            return False, False, summary

        if group == "mutate":
            # Check for fast read operations in metadata/style
            if op in ("get", "query", "provenance", "text_read"):
                return False, False, summary
            return True, True, summary

        return False, False, summary

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

        if isinstance(raw_result, dict) and "external_result" in raw_result:
            return raw_result

        # Enforce bounded model context: direct results must not return image/binary/base64 inline
        if _has_image_or_binary_data(raw_result):
            try:
                return self._desktop_nodes.store_external_result(node_id, raw_result)
            except Exception as exc:
                raise BridgeError(
                    ErrorCode.INTERNAL_ERROR,
                    f"Failed to externalize binary result payload: {exc}",
                ) from exc

        if isinstance(raw_result, dict) and "content" in raw_result:
            for block in raw_result.get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    try:
                        parsed = json.loads(text)
                    except (ValueError, TypeError):
                        continue
                    if isinstance(parsed, dict):
                        if parsed.get("status") == "failed" or "error" in parsed:
                            err = parsed.get("error", {})
                            code_str = err.get("code", "FUSION_API_ERROR")
                            try:
                                code = ErrorCode(code_str)
                            except ValueError:
                                code = ErrorCode.FUSION_API_ERROR
                            raise FusionCadError(
                                code,
                                err.get("message", "CAD operation failed"),
                                details=err.get("details", {}),
                            )
                        if _has_image_or_binary_data(parsed):
                            try:
                                return self._desktop_nodes.store_external_result(node_id, parsed)
                            except Exception as exc:
                                raise BridgeError(
                                    ErrorCode.INTERNAL_ERROR,
                                    f"Failed to externalize binary result payload: {exc}",
                                ) from exc
                        if parsed.get("api_version") == "fusion.cad/v1":
                            return CadResult.model_validate(parsed)
                        return parsed

        if isinstance(raw_result, dict):
            if _has_image_or_binary_data(raw_result):
                try:
                    return self._desktop_nodes.store_external_result(node_id, raw_result)
                except Exception as exc:
                    raise BridgeError(
                        ErrorCode.INTERNAL_ERROR,
                        f"Failed to externalize binary result payload: {exc}",
                    ) from exc
            if raw_result.get("api_version") == "fusion.cad/v1":
                return CadResult.model_validate(raw_result)
            return raw_result

        return {"raw_result": raw_result}
