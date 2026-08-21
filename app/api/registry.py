from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from mcp import types

from .context import RequestContext
from .errors import ToolNameConflictError


ToolHandler = Callable[[Any, Any, RequestContext], Awaitable[types.CallToolResult]]


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    definition: types.Tool
    handler: ToolHandler
    source: str


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> None:
        existing = self._tools.get(tool.definition.name)
        if existing is not None:
            raise ToolNameConflictError(
                f"tool {tool.definition.name!r} from {tool.source} conflicts "
                f"with {existing.source}"
            )
        self._tools[tool.definition.name] = tool

    def register_many(self, tools: Iterable[RegisteredTool]) -> None:
        for tool in tools:
            self.register(tool)

    @property
    def definitions(self) -> tuple[types.Tool, ...]:
        return tuple(tool.definition for tool in self._tools.values())

    def get(self, name: str) -> RegisteredTool | None:
        return self._tools.get(name)

