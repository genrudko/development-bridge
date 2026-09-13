from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import TypeAlias
from urllib.parse import urlsplit

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
