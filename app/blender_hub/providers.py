from __future__ import annotations

import asyncio
import math
import os
import re
from contextlib import AsyncExitStack
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Protocol, TypeAlias
from urllib.parse import urlsplit

import httpx2
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z", re.ASCII)
_ENVIRONMENT_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z", re.ASCII)
_BASELINE_ENVIRONMENT_KEYS = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "TMPDIR",
    "LANG",
    "LC_ALL",
)
_MAX_ENVIRONMENT_BYTES = 16 * 1024


class ProviderKind(str, Enum):
    DCC_GATEWAY = "dcc_gateway"
    THREE_MF = "three_mf"
    ORCA = "orca"
    RESEARCH = "research"


def _validate_common(
    provider_id: str,
    namespace: str,
    kind: ProviderKind,
    read_timeout_seconds: float | None,
) -> None:
    for label, value in (("provider_id", provider_id), ("namespace", namespace)):
        if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
            raise ValueError(f"invalid {label}")
    if not isinstance(kind, ProviderKind):
        raise TypeError("kind must be a ProviderKind")
    if read_timeout_seconds is not None:
        if isinstance(read_timeout_seconds, bool) or not isinstance(
            read_timeout_seconds, (int, float)
        ):
            raise TypeError("read_timeout_seconds must be a number or None")
        if not math.isfinite(read_timeout_seconds) or read_timeout_seconds <= 0:
            raise ValueError("read_timeout_seconds must be positive and finite")


def _validate_http_url(url: str) -> None:
    if not isinstance(url, str):
        raise TypeError("url must be a string")
    if url != url.strip() or any(ord(character) < 32 for character in url):
        raise ValueError("provider URL must not contain whitespace controls")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid provider URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("provider URL must be absolute HTTP or HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("provider URL must not contain user-info")
    if parsed.query or parsed.fragment:
        raise ValueError("provider URL must not contain query or fragment")
    if "%" in parsed.netloc or "\\" in parsed.netloc:
        raise ValueError("provider URL authority must not be encoded")
    hostname = parsed.hostname
    if hostname is None or hostname.lower() not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("provider URL host must be loopback")
    if port is None or not 1 <= port <= 65535:
        raise ValueError("provider URL must contain an explicit valid port")


def _validate_environment_overrides(env: Mapping[str, str]) -> None:
    if not isinstance(env, Mapping):
        raise TypeError("env must be a mapping")
    if len(env) > 128:
        raise ValueError("env contains too many overrides")
    for key, value in env.items():
        if not isinstance(key, str) or _ENVIRONMENT_KEY.fullmatch(key) is None:
            raise ValueError("invalid environment key")
        if not isinstance(value, str):
            raise TypeError("environment values must be strings")
        if len(value) > 4096:
            raise ValueError("environment value is too long")


@dataclass(frozen=True, slots=True)
class HttpProviderConfig:
    provider_id: str
    namespace: str
    kind: ProviderKind
    url: str
    read_timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        _validate_common(
            self.provider_id, self.namespace, self.kind, self.read_timeout_seconds
        )
        _validate_http_url(self.url)


@dataclass(frozen=True, slots=True)
class StdioProviderConfig:
    provider_id: str
    namespace: str
    kind: ProviderKind
    argv: tuple[str, ...]
    cwd: Path | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    read_timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        _validate_common(
            self.provider_id, self.namespace, self.kind, self.read_timeout_seconds
        )
        if not isinstance(self.argv, tuple):
            raise TypeError("argv must be a tuple")
        if not 1 <= len(self.argv) <= 64:
            raise ValueError("argv must contain between 1 and 64 entries")
        for item in self.argv:
            if not isinstance(item, str):
                raise TypeError("argv entries must be strings")
            if not item or len(item) > 4096:
                raise ValueError("argv entries must contain 1 to 4096 characters")
        if self.cwd is not None and not isinstance(self.cwd, Path):
            raise TypeError("cwd must be a Path or None")
        _validate_environment_overrides(self.env)
        object.__setattr__(self, "env", MappingProxyType(dict(self.env)))


ProviderConfig: TypeAlias = HttpProviderConfig | StdioProviderConfig


def validate_provider_configs(
    configs: Iterable[ProviderConfig],
) -> tuple[ProviderConfig, ...]:
    validated = tuple(configs)
    provider_ids: set[str] = set()
    namespaces: set[str] = set()
    for config in validated:
        if not isinstance(config, (HttpProviderConfig, StdioProviderConfig)):
            raise TypeError("configs must contain provider configurations")
        if config.provider_id in provider_ids:
            raise ValueError(f"duplicate provider_id: {config.provider_id}")
        if config.namespace in namespaces:
            raise ValueError(f"duplicate namespace: {config.namespace}")
        provider_ids.add(config.provider_id)
        namespaces.add(config.namespace)
    return validated


def build_stdio_environment(
    config: StdioProviderConfig, environ: Mapping[str, str]
) -> dict[str, str]:
    if not isinstance(config, StdioProviderConfig):
        raise TypeError("config must be a StdioProviderConfig")
    merged = {
        key: environ[key]
        for key in _BASELINE_ENVIRONMENT_KEYS
        if key in environ
    }
    if any(not isinstance(value, str) for value in merged.values()):
        raise TypeError("baseline environment values must be strings")
    merged.update(config.env)
    size = sum(len(f"{key}={value}".encode("utf-8")) for key, value in merged.items())
    if size > _MAX_ENVIRONMENT_BYTES:
        raise ValueError("merged environment exceeds 16 KiB")
    return merged


def _immutable_json_value(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return value
    if isinstance(value, Mapping):
        copied: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            copied[key] = _immutable_json_value(item)
        return MappingProxyType(copied)
    if isinstance(value, (list, tuple)):
        return tuple(_immutable_json_value(item) for item in value)
    raise TypeError(f"value of type {type(value).__name__} is not JSON-safe")


def immutable_json_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("JSON evidence must be a mapping")
    snapshot = _immutable_json_value(value)
    assert isinstance(snapshot, Mapping)
    return snapshot


@dataclass(frozen=True, slots=True)
class UpstreamTool:
    name: str
    title: str | None
    description: str | None
    input_schema: Mapping[str, object]
    output_schema: Mapping[str, object] | None
    annotations: Mapping[str, object]
    publication_metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if self.title is not None and not isinstance(self.title, str):
            raise TypeError("title must be a string or None")
        if self.description is not None and not isinstance(self.description, str):
            raise TypeError("description must be a string or None")
        object.__setattr__(self, "input_schema", immutable_json_mapping(self.input_schema))
        if self.output_schema is not None:
            object.__setattr__(
                self, "output_schema", immutable_json_mapping(self.output_schema)
            )
        object.__setattr__(self, "annotations", immutable_json_mapping(self.annotations))
        object.__setattr__(
            self,
            "publication_metadata",
            immutable_json_mapping(self.publication_metadata),
        )


class ProviderSession(Protocol):
    async def initialize(self) -> None: ...

    async def list_tools(self) -> tuple[UpstreamTool, ...]: ...

    async def call_tool(
        self, name: str, arguments: dict[str, object]
    ) -> object: ...

    async def close(self) -> None: ...


class ProviderConnector(Protocol):
    async def connect(self, config: ProviderConfig) -> ProviderSession: ...


class ProviderSessionFailure(Exception):
    def __init__(self, provider_id: str, phase: str, exception_type: str) -> None:
        self.provider_id = provider_id
        self.phase = phase
        self.exception_type = exception_type
        super().__init__(f"provider {provider_id} failed during {phase} ({exception_type})")


class ProviderConnectionError(ProviderSessionFailure):
    def __init__(
        self, provider_id: str, phase: str = "connect", exception_type: str = "Exception"
    ) -> None:
        super().__init__(provider_id, phase, exception_type)


@dataclass(frozen=True, slots=True)
class _CleanupIssue:
    exception_type: str
    phase: str


async def _cleanup_once(stack: AsyncExitStack, phase: str) -> _CleanupIssue | None:
    try:
        await stack.aclose()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        exception_type = type(exc).__name__
    else:
        return None
    return _CleanupIssue(exception_type, phase)


def _convert_tool(tool: object) -> UpstreamTool:
    dumped = tool.model_dump(mode="json", by_alias=True, exclude_none=True)
    annotations_model = getattr(tool, "annotations", None)
    annotations = (
        annotations_model.model_dump(mode="json", by_alias=True, exclude_none=True)
        if annotations_model is not None
        else {}
    )
    publication = {
        key: dumped[key] for key in ("execution", "icons", "_meta") if key in dumped
    }
    return UpstreamTool(
        name=dumped["name"],
        title=dumped.get("title"),
        description=dumped.get("description"),
        input_schema=dumped["inputSchema"],
        output_schema=dumped.get("outputSchema"),
        annotations=annotations,
        publication_metadata=publication,
    )


class _McpProviderSession:
    def __init__(
        self,
        provider_id: str,
        read_timeout_seconds: float | None,
        stack: AsyncExitStack,
        session: ClientSession,
    ) -> None:
        self._provider_id = provider_id
        self._read_timeout_seconds = read_timeout_seconds
        self._stack: AsyncExitStack | None = stack
        self._session = session

    async def initialize(self) -> None:
        failure_type: str | None = None
        try:
            await self._session.initialize()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failure_type = type(exc).__name__
        if failure_type is not None:
            raise ProviderSessionFailure(
                self._provider_id, "initialize", failure_type
            ) from None

    async def list_tools(self) -> tuple[UpstreamTool, ...]:
        failure_type: str | None = None
        result = None
        try:
            result = await self._session.list_tools()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failure_type = type(exc).__name__
        if failure_type is not None:
            raise ProviderSessionFailure(self._provider_id, "list", failure_type) from None
        assert result is not None
        return tuple(_convert_tool(tool) for tool in result.tools)

    async def call_tool(
        self, name: str, arguments: dict[str, object]
    ) -> object:
        failure_type: str | None = None
        result = None
        try:
            result = await self._session.call_tool(
                name,
                arguments,
                read_timeout_seconds=self._read_timeout_seconds,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failure_type = type(exc).__name__
        if failure_type is not None:
            raise ProviderSessionFailure(self._provider_id, "call", failure_type) from None
        assert result is not None
        return result.model_dump(mode="json", by_alias=True, exclude_none=True)

    async def close(self) -> None:
        stack, self._stack = self._stack, None
        if stack is None:
            return
        issue = await _cleanup_once(stack, "close")
        if issue is not None:
            raise ProviderSessionFailure(
                self._provider_id, issue.phase, issue.exception_type
            ) from None


async def _finish_connection(
    config: ProviderConfig,
    stack: AsyncExitStack,
    enter_transport: object,
) -> ProviderSession:
    failure_type: str | None = None
    try:
        read_stream, write_stream = await stack.enter_async_context(enter_transport)
        session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
    except asyncio.CancelledError:
        await _cleanup_once(stack, "connect")
        raise
    except Exception as exc:
        failure_type = type(exc).__name__
    if failure_type is not None:
        await _cleanup_once(stack, "connect")
        raise ProviderConnectionError(
            config.provider_id, exception_type=failure_type
        ) from None
    return _McpProviderSession(
        config.provider_id, config.read_timeout_seconds, stack, session
    )


class StreamableHttpProvider:
    async def connect(self, config: HttpProviderConfig) -> ProviderSession:
        if not isinstance(config, HttpProviderConfig):
            raise TypeError("config must be an HttpProviderConfig")
        stack = AsyncExitStack()
        failure_type: str | None = None
        try:
            client = await stack.enter_async_context(
                httpx2.AsyncClient(
                    follow_redirects=False,
                    trust_env=False,
                    timeout=httpx2.Timeout(connect=30, read=300, write=30, pool=30),
                )
            )
        except asyncio.CancelledError:
            await _cleanup_once(stack, "connect")
            raise
        except Exception as exc:
            failure_type = type(exc).__name__
        if failure_type is not None:
            await _cleanup_once(stack, "connect")
            raise ProviderConnectionError(
                config.provider_id, exception_type=failure_type
            ) from None
        transport = streamable_http_client(config.url, http_client=client)
        return await _finish_connection(config, stack, transport)


class StdioProvider:
    async def connect(self, config: StdioProviderConfig) -> ProviderSession:
        if not isinstance(config, StdioProviderConfig):
            raise TypeError("config must be a StdioProviderConfig")
        stack = AsyncExitStack()
        parameters = StdioServerParameters(
            command=config.argv[0],
            args=list(config.argv[1:]),
            cwd=config.cwd,
            env=build_stdio_environment(config, os.environ),
        )
        return await _finish_connection(config, stack, stdio_client(parameters))
