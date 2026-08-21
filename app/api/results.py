from __future__ import annotations

import json
from typing import Any

from mcp import types
from pydantic import BaseModel, ConfigDict, Field

from .errors import BridgeError


class ErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ResultEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    api_version: str = "1.0"
    request_id: str
    ok: bool
    data: Any | None = None
    warnings: tuple[str, ...] = ()
    revision: str | None = None
    error: ErrorPayload | None = None


def success(
    request_id: str,
    data: Any,
    *,
    revision: str | None = None,
    warnings: tuple[str, ...] = (),
) -> ResultEnvelope:
    return ResultEnvelope(
        request_id=request_id,
        ok=True,
        data=data,
        revision=revision,
        warnings=warnings,
    )


def failure(request_id: str, error: BridgeError) -> ResultEnvelope:
    return ResultEnvelope(
        request_id=request_id,
        ok=False,
        error=ErrorPayload(
            code=error.code.value,
            message=error.message,
            retryable=error.retryable,
            details=error.details,
        ),
    )


def to_mcp_result(envelope: ResultEnvelope) -> types.CallToolResult:
    text = json.dumps(
        envelope.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
    )
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        isError=not envelope.ok,
    )

