from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.blender_hub.providers import immutable_json_mapping

ToolHandler = Callable[[dict[str, object]], Awaitable[object]]


class DuplicateToolName(ValueError):
    """A provider attempted to claim an existing name in a namespace."""


class ProviderUnavailable(RuntimeError):
    """The selected provider is not currently callable."""


class ProviderState(str, Enum):
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"


@dataclass(frozen=True, slots=True)
class ProviderTool:
    name: str
    handler: ToolHandler
    metadata: object = None
    title: str | None = None
    description: str | None = None
    input_schema: Mapping[str, object] = field(default_factory=dict)
    output_schema: Mapping[str, object] | None = None
    publication_metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CatalogTool:
    provider_id: str
    namespace: str
    name: str
    handler: ToolHandler
    metadata: object
    mutating: bool
    title: str | None = None
    description: str | None = None
    input_schema: Mapping[str, object] = field(default_factory=dict)
    output_schema: Mapping[str, object] | None = None
    publication_metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        return f"{self.namespace}.{self.name}"


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    provider_id: str
    namespace: str
    state: ProviderState
    error: str | None = None


def is_mutating(metadata: object) -> bool:
    """Classify conservatively; only a literal read-only hint bypasses locking."""
    if not isinstance(metadata, Mapping):
        return True
    destructive_hint = metadata.get("destructiveHint", False)
    if not isinstance(destructive_hint, bool) or destructive_hint:
        return True
    return metadata.get("readOnlyHint") is not True


def _snapshot_metadata(metadata: object) -> object:
    if isinstance(metadata, Mapping):
        return immutable_json_mapping(metadata)
    return metadata


def _mutable_json_copy(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _mutable_json_copy(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_mutable_json_copy(item) for item in value]
    return value


class NamespacedToolCatalog:
    def __init__(self) -> None:
        self._tools: dict[str, CatalogTool] = {}
        self._statuses: dict[str, ProviderStatus] = {}
        self._mutation_lock = asyncio.Lock()

    def register_provider(
        self, provider_id: str, namespace: str, tools: Iterable[ProviderTool]
    ) -> None:
        proposed = list(tools)
        qualified = [f"{namespace}.{item.name}" for item in proposed]
        duplicates = {name for name in qualified if qualified.count(name) > 1}
        occupied = {
            name
            for name, item in self._tools.items()
            if item.provider_id != provider_id
        }
        duplicates.update(name for name in qualified if name in occupied)
        if duplicates:
            raise DuplicateToolName(
                f"duplicate provider tool name: {sorted(duplicates)[0]}"
            )

        entries: list[CatalogTool] = []
        for item in proposed:
            metadata = _snapshot_metadata(item.metadata)
            entries.append(
                CatalogTool(
                    provider_id=provider_id,
                    namespace=namespace,
                    name=item.name,
                    handler=item.handler,
                    metadata=metadata,
                    mutating=is_mutating(metadata),
                    title=item.title,
                    description=item.description,
                    input_schema=immutable_json_mapping(item.input_schema),
                    output_schema=(
                        None
                        if item.output_schema is None
                        else immutable_json_mapping(item.output_schema)
                    ),
                    publication_metadata=immutable_json_mapping(
                        item.publication_metadata
                    ),
                )
            )

        self._tools = {
            name: item
            for name, item in self._tools.items()
            if item.provider_id != provider_id
        }
        for entry in entries:
            self._tools[entry.qualified_name] = entry
        self._statuses[provider_id] = ProviderStatus(
            provider_id=provider_id,
            namespace=namespace,
            state=ProviderState.ONLINE,
        )

    def set_provider_status(
        self, provider_id: str, state: ProviderState, error: str | None = None
    ) -> None:
        current = self._statuses[provider_id]
        self._statuses[provider_id] = ProviderStatus(
            provider_id=provider_id,
            namespace=current.namespace,
            state=state,
            error=error,
        )

    def list_tools(self) -> tuple[CatalogTool, ...]:
        return tuple(
            CatalogTool(
                provider_id=item.provider_id,
                namespace=item.namespace,
                name=item.name,
                handler=item.handler,
                metadata=_mutable_json_copy(item.metadata),
                mutating=item.mutating,
                title=item.title,
                description=item.description,
                input_schema=_mutable_json_copy(item.input_schema),
                output_schema=(
                    None
                    if item.output_schema is None
                    else _mutable_json_copy(item.output_schema)
                ),
                publication_metadata=_mutable_json_copy(item.publication_metadata),
            )
            for name in sorted(self._tools)
            for item in (self._tools[name],)
        )

    def provider_statuses(self) -> tuple[ProviderStatus, ...]:
        return tuple(self._statuses[key] for key in sorted(self._statuses))

    async def invoke(self, qualified_name: str, arguments: dict[str, object]) -> Any:
        tool = self._tools[qualified_name]
        status = self._statuses[tool.provider_id]
        if status.state is ProviderState.OFFLINE:
            raise ProviderUnavailable(
                f"provider '{tool.provider_id}' is offline: {status.error or 'unknown error'}"
            )
        if not tool.mutating:
            return await tool.handler(arguments)
        async with self._mutation_lock:
            return await tool.handler(arguments)
