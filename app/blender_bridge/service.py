from __future__ import annotations

import asyncio
from typing import Any

from .models import ProviderSpec, PublicTool


class BlenderBridgeService:
    def __init__(self, *, providers: tuple[ProviderSpec, ...]) -> None:
        self._providers = {provider.namespace: provider for provider in providers}
        self._catalog: dict[str, PublicTool] = {}
        self._mutation_lock = asyncio.Lock()

    async def refresh_catalog(self) -> tuple[PublicTool, ...]:
        catalog: dict[str, PublicTool] = {}
        for namespace, provider in self._providers.items():
            for tool in await provider.client.list_tools():
                public_name = f"{namespace}.{tool.name}"
                if public_name in catalog:
                    raise ValueError(f"duplicate public tool name: {public_name}")
                catalog[public_name] = PublicTool(
                    public_name=public_name,
                    provider_namespace=namespace,
                    upstream_name=tool.name,
                    description=tool.description,
                    mutating=tool.mutating is not False,
                    input_schema=tool.input_schema,
                )
        self._catalog = catalog
        return tuple(catalog.values())

    def resolve_tool(self, public_name: str) -> PublicTool:
        try:
            return self._catalog[public_name]
        except KeyError as exc:
            raise KeyError(f"unknown Blender Hub tool: {public_name}") from exc

    async def call_tool(self, public_name: str, arguments: dict[str, Any]) -> Any:
        tool = self.resolve_tool(public_name)
        provider = self._providers[tool.provider_namespace]
        if not tool.mutating:
            return await provider.client.call_tool(tool.upstream_name, arguments)
        async with self._mutation_lock:
            return await provider.client.call_tool(tool.upstream_name, arguments)
