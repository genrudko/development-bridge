from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from .models import ToolSpec


ProviderHealthState = Literal["online", "degraded", "offline"]
ProviderCallState = Literal["completed", "failed", "uncertain"]


class ProviderConnectionLost(ConnectionError):
    """The provider connection dropped before terminal outcome was known."""


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    state: ProviderHealthState
    version: str | None = None
    pin: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderCallResult:
    state: ProviderCallState
    value: Any = None
    error: str | None = None


class ProviderTransport(Protocol):
    async def list_tools(self) -> list[ToolSpec]: ...
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...
    async def reconnect(self) -> None: ...
    async def health(self) -> ProviderHealth: ...


class ManagedProviderClient:
    """Provider client with conservative disconnect/replay semantics."""

    def __init__(self, transport: ProviderTransport) -> None:
        self._transport = transport
        self._tools: dict[str, ToolSpec] = {}

    async def list_tools(self) -> list[ToolSpec]:
        tools = await self._transport.list_tools()
        self._tools = {tool.name: tool for tool in tools}
        return list(tools)

    async def reconnect(self) -> None:
        await self._transport.reconnect()

    async def health(self) -> ProviderHealth:
        return await self._transport.health()

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ProviderCallResult:
        try:
            tool = self._tools[name]
        except KeyError as exc:
            raise KeyError(f"provider tool not in current catalog: {name}") from exc

        try:
            value = await self._transport.call_tool(name, arguments)
        except ProviderConnectionLost as exc:
            if tool.mutating is not False:
                return ProviderCallResult(state="uncertain", error=str(exc))
            if not tool.idempotent:
                return ProviderCallResult(state="failed", error=str(exc))
            await self._transport.reconnect()
            try:
                value = await self._transport.call_tool(name, arguments)
            except ProviderConnectionLost as retry_exc:
                return ProviderCallResult(state="failed", error=str(retry_exc))
        except Exception as exc:
            return ProviderCallResult(state="failed", error=str(exc))

        return ProviderCallResult(state="completed", value=value)
