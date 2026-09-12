from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    mutating: bool | None
    idempotent: bool = False
    input_schema: dict[str, Any] | None = None


class ProviderClient(Protocol):
    async def list_tools(self) -> list[ToolSpec]: ...
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    namespace: str
    client: ProviderClient


@dataclass(frozen=True, slots=True)
class PublicTool:
    public_name: str
    provider_namespace: str
    upstream_name: str
    description: str
    mutating: bool
    input_schema: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class OperatorPrompt:
    prompt_id: str
    question: str
    choices: tuple[str, ...]
    operation_id: str | None = None


@dataclass(frozen=True, slots=True)
class OperatorAnswer:
    prompt_id: str
    value: str
