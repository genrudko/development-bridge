from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.api.errors import BridgeError, ErrorCode
from app.fusion_cad.models import unfreeze_value

_VALID_GROUP_NAME = re.compile(r"^[A-Za-z0-9_]+$")


class _BundleBuilderDescriptor:
    def __get__(self, instance: Any, owner: Any = None) -> Any:
        if instance is None:
            def _class_build(group: str, payload: dict[str, Any] | BaseModel) -> str:
                return owner()._build(group, payload)
            return _class_build
        return instance._build


class FusionCadScriptBundle:
    """Builder for static versioned Fusion CAD Python scripts.

    Reads static versioned .py.txt script fragments and injects only JSON-serialized
    payloads using json.dumps(..., ensure_ascii=False, separators=(",", ":")).
    Raw model-authored Python source is strictly prohibited.
    """

    build = _BundleBuilderDescriptor()

    def __init__(self, scripts_dir: Path | None = None) -> None:
        self._scripts_dir = (
            scripts_dir
            if scripts_dir is not None
            else Path(__file__).parent / "fusion_scripts"
        )

    def _build(self, group: str, payload: dict[str, Any] | BaseModel) -> str:
        if not isinstance(group, str) or not _VALID_GROUP_NAME.match(group):
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                f"Invalid script group name: {group!r}",
                details={"group": group},
            )

        if isinstance(payload, BaseModel):
            payload_data = payload.model_dump(mode="json", exclude_none=True)
        elif isinstance(payload, (dict, Mapping)):
            payload_data = unfreeze_value(dict(payload))
        else:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                f"Script payload must be a dict or BaseModel, got {type(payload).__name__}",
            )

        try:
            serialized_payload = json.dumps(
                payload_data,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                f"Script payload failed JSON serialization: {exc}",
            ) from exc

        common_path = self._scripts_dir / "common.py.txt"
        if not common_path.exists():
            raise BridgeError(
                ErrorCode.INTERNAL_ERROR,
                f"Common script template missing at {common_path}",
            )

        group_path = self._scripts_dir / f"{group}.py.txt"
        if not group_path.exists():
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                f"Required script fragment for group '{group}' missing at {group_path}",
                details={"group": group},
            )

        common_script = common_path.read_text("utf-8")
        group_script = group_path.read_text("utf-8")

        marker = "# __GROUP_SCRIPT__"
        marker_count = common_script.count(marker)
        if marker_count == 0:
            raise BridgeError(
                ErrorCode.INTERNAL_ERROR,
                f"Common script template missing required '{marker}' marker at {common_path}",
            )
        if marker_count > 1:
            raise BridgeError(
                ErrorCode.INTERNAL_ERROR,
                f"Common script template contains duplicate '{marker}' markers ({marker_count}) at {common_path}",
            )

        if "__PAYLOAD_JSON__" not in common_script:
            raise BridgeError(
                ErrorCode.INTERNAL_ERROR,
                f"Common script template missing '__PAYLOAD_JSON__' marker at {common_path}",
            )

        escaped_literal = json.dumps(serialized_payload, ensure_ascii=False)
        rendered_script = common_script.replace("__PAYLOAD_JSON__", escaped_literal, 1)
        rendered_script = rendered_script.replace(marker, group_script, 1)

        return rendered_script
