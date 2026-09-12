"""Windows Blender Hub: multiplex local MCP providers through Development Bridge."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections.abc import Callable
from contextlib import AsyncExitStack, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.blender_bridge.models import ProviderSpec, ToolSpec
from app.blender_bridge.provider_transport import (
    ManagedProviderClient,
    ProviderCallResult,
    ProviderConnectionLost,
    ProviderHealth,
)
from app.blender_bridge.service import BlenderBridgeService


_NAMESPACE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    namespace: str
    url: str
    pin: str | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        if _NAMESPACE.fullmatch(self.namespace) is None:
            raise ValueError(f"invalid provider namespace: {self.namespace!r}")
        parsed = urlsplit(self.url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in _LOCAL_HOSTS:
            raise ValueError(
                f"provider {self.namespace!r} URL must be loopback HTTP(S)"
            )
        if not parsed.path:
            raise ValueError(f"provider {self.namespace!r} URL must include an MCP path")
        if self.pin is not None and not self.pin.strip():
            raise ValueError(f"provider {self.namespace!r} pin must not be empty")


def load_provider_configs(path: Path) -> tuple[ProviderConfig, ...]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("providers"), list):
        raise ValueError("provider config must contain a providers list")
    configs: list[ProviderConfig] = []
    seen: set[str] = set()
    for raw in document["providers"]:
        if not isinstance(raw, dict):
            raise ValueError("each provider config must be an object")
        unknown = set(raw) - {"namespace", "url", "pin", "enabled"}
        if unknown:
            raise ValueError(f"unknown provider config fields: {sorted(unknown)}")
        config = ProviderConfig(
            namespace=str(raw["namespace"]),
            url=str(raw["url"]),
            pin=(str(raw["pin"]) if raw.get("pin") is not None else None),
            enabled=bool(raw.get("enabled", True)),
        )
        if config.namespace in seen:
            raise ValueError(f"duplicate provider namespace: {config.namespace}")
        seen.add(config.namespace)
        configs.append(config)
    return tuple(configs)


def _tool_annotations(raw: dict[str, Any]) -> dict[str, Any]:
    annotations = raw.get("annotations")
    return annotations if isinstance(annotations, dict) else {}


def tool_spec_from_mcp_dump(raw: dict[str, Any]) -> ToolSpec:
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("provider tool name must be a non-empty string")
    annotations = _tool_annotations(raw)
    read_only = raw.get("read_only") is True or annotations.get("readOnlyHint") is True
    destructive = (
        raw.get("destructive") is True
        or annotations.get("destructiveHint") is True
    )
    mutating: bool | None
    if destructive:
        mutating = True
    elif read_only:
        mutating = False
    else:
        mutating = None
    idempotent = raw.get("idempotent") is True or annotations.get("idempotentHint") is True
    schema = raw.get("inputSchema", raw.get("input_schema"))
    if schema is not None and not isinstance(schema, dict):
        raise ValueError(f"provider tool {name!r} input schema must be an object")
    description = raw.get("description")
    return ToolSpec(
        name=name,
        description=description if isinstance(description, str) else "",
        mutating=mutating,
        idempotent=idempotent,
        input_schema=schema,
    )


def public_tool_metadata(namespace: str, raw: dict[str, Any]) -> dict[str, Any]:
    spec = tool_spec_from_mcp_dump(raw)
    effective_mutating = spec.mutating is not False
    return {
        "name": f"{namespace}.{spec.name}",
        "description": f"[{namespace}] {spec.description}".rstrip(),
        "inputSchema": spec.input_schema or {"type": "object", "properties": {}},
        "x_blender_hub": {
            "provider": namespace,
            "upstream_tool": spec.name,
            "mutating": effective_mutating,
            "idempotent": spec.idempotent,
        },
    }


def _is_transport_error(exc: BaseException) -> bool:
    if isinstance(exc, (ConnectionError, OSError, TimeoutError, asyncio.TimeoutError)):
        return True
    module = type(exc).__module__.split(".", 1)[0]
    name = type(exc).__name__.lower()
    return module in {"httpx", "httpcore", "anyio"} and any(
        marker in name for marker in ("connect", "timeout", "network", "closed", "read")
    )


class McpProviderTransport:
    """One local Streamable HTTP MCP provider connection."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._stack: AsyncExitStack | None = None
        self._session: Any | None = None
        self._raw_tools: list[dict[str, Any]] = []

    async def connect(self) -> None:
        if self._stack is not None:
            return
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        stack = AsyncExitStack()
        try:
            streams = await stack.enter_async_context(streamable_http_client(self.config.url))
            session = await stack.enter_async_context(ClientSession(streams[0], streams[1]))
            await session.initialize()
            response = await session.list_tools()
            raw_tools = [
                tool.model_dump(mode="json", exclude_none=True)
                if hasattr(tool, "model_dump")
                else dict(tool)
                for tool in response.tools
            ]
        except BaseException:
            await stack.aclose()
            raise
        self._stack = stack
        self._session = session
        self._raw_tools = raw_tools

    async def close(self) -> None:
        stack, self._stack = self._stack, None
        self._session = None
        self._raw_tools = []
        if stack is not None:
            await stack.aclose()

    async def reconnect(self) -> None:
        await self.close()
        await self.connect()

    async def list_tools(self) -> list[ToolSpec]:
        await self.connect()
        return [tool_spec_from_mcp_dump(raw) for raw in self._raw_tools]

    def advertised_tools(self) -> list[dict[str, Any]]:
        return [public_tool_metadata(self.config.namespace, raw) for raw in self._raw_tools]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        await self.connect()
        assert self._session is not None
        try:
            result = await self._session.call_tool(name, arguments)
        except BaseException as exc:
            if _is_transport_error(exc):
                raise ProviderConnectionLost(str(exc)) from exc
            raise
        if hasattr(result, "model_dump"):
            return result.model_dump(mode="json", exclude_none=True)
        return result

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            state="online" if self._session is not None else "offline",
            pin=self.config.pin,
        )


class OperatorBackend(Protocol):
    async def ask(self, arguments: dict[str, Any]) -> dict[str, Any]: ...


class ConsoleOperatorBackend:
    """Minimal same-turn backend; GUI/N-panel replaces this without changing protocol."""

    async def ask(self, arguments: dict[str, Any]) -> dict[str, Any]:
        prompt_id = f"ask_{uuid4().hex}"
        question = str(arguments.get("question", "")).strip()
        if not question:
            raise ValueError("operator question must not be empty")
        choices = arguments.get("choices", [])
        if not isinstance(choices, list) or not all(isinstance(item, str) for item in choices):
            raise ValueError("operator choices must be a string list")
        suffix = f" [{' / '.join(choices)}]" if choices else ""
        value = await asyncio.to_thread(input, f"\n[Blender Hub] {question}{suffix}\n> ")
        return {
            "status": "answered",
            "prompt_id": prompt_id,
            "operation_id": arguments.get("operation_id"),
            "value": value,
        }


class BlenderHubRuntime:
    def __init__(
        self,
        configs: tuple[ProviderConfig, ...],
        *,
        operator: OperatorBackend | None = None,
        transport_factory: Callable[[ProviderConfig], Any] | None = None,
    ) -> None:
        self.configs = tuple(config for config in configs if config.enabled)
        self.operator = operator or ConsoleOperatorBackend()
        self._transport_factory = transport_factory or McpProviderTransport
        self.transports: dict[str, Any] = {}
        self.clients: dict[str, ManagedProviderClient] = {}
        self.provider_errors: dict[str, str] = {}
        self.service: BlenderBridgeService | None = None

    async def connect(self) -> None:
        providers: list[ProviderSpec] = []
        self.provider_errors.clear()
        for config in self.configs:
            transport = self._transport_factory(config)
            try:
                await transport.connect()
                client = ManagedProviderClient(transport)
                await client.list_tools()
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
                    raise
                with suppress(Exception):
                    await transport.close()
                self.provider_errors[config.namespace] = str(exc) or type(exc).__name__
                continue
            self.transports[config.namespace] = transport
            self.clients[config.namespace] = client
            providers.append(ProviderSpec(namespace=config.namespace, client=client))
        self.service = BlenderBridgeService(providers=tuple(providers))
        await self.service.refresh_catalog()

    async def close(self) -> None:
        for transport in reversed(tuple(self.transports.values())):
            with suppress(Exception):
                await transport.close()
        self.transports.clear()
        self.clients.clear()
        self.service = None

    def advertised_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for namespace, transport in self.transports.items():
            tools.extend(transport.advertised_tools())
        tools.append(
            {
                "name": "operator.ask",
                "description": "Ask the local Blender operator and wait for a same-turn answer",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "choices": {"type": "array", "items": {"type": "string"}},
                        "operation_id": {"type": "string"},
                    },
                    "required": ["question"],
                    "additionalProperties": False,
                },
                "x_blender_hub": {
                    "provider": "operator",
                    "upstream_tool": "ask",
                    "mutating": False,
                    "idempotent": False,
                },
            }
        )
        return tools

    async def dispatch(self, public_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if public_name == "operator.ask":
            return await self.operator.ask(arguments)
        if self.service is None:
            raise RuntimeError("Blender Hub is not connected")
        result = await self.service.call_tool(public_name, arguments)
        if isinstance(result, ProviderCallResult):
            return {
                "status": result.state,
                "value": result.value,
                "error": result.error,
            }
        if isinstance(result, dict):
            return result
        return {"status": "completed", "value": result}

    def provider_status(self) -> list[dict[str, Any]]:
        return [
            {
                "namespace": config.namespace,
                "url": config.url,
                "pin": config.pin,
                "connected": config.namespace in self.transports,
                "error": self.provider_errors.get(config.namespace),
            }
            for config in self.configs
        ]


def default_outbox_directory() -> Path:
    configured = os.environ.get("DEVELOPMENT_BRIDGE_BLENDER_OUTBOX")
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "DevelopmentBridgeBlender"
    return Path(configured) if configured else base / "outbox"


async def run(
    *,
    bridge_url: str,
    node_id: str,
    token: str,
    provider_config_path: Path,
    heartbeat_seconds: float,
    claim_wait_seconds: float,
    operator: OperatorBackend | None = None,
    status_sink: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    # Reuse the already-qualified outbound Bridge transport/result-delivery logic.
    from windows_fusion_agent import (
        BridgeClient,
        ResultOutbox,
        keepalive,
        submit_result_safely,
    )

    configs = load_provider_configs(provider_config_path)
    runtime = BlenderHubRuntime(configs, operator=operator)
    bridge = BridgeClient(bridge_url, node_id, token)
    outbox = ResultOutbox(default_outbox_directory())
    telemetry: dict[str, Any] = {
        "result_delivery_degraded": bool(outbox.count()),
        "result_outbox_count": outbox.count(),
    }
    await runtime.connect()
    tools = runtime.advertised_tools()
    await bridge.post(
        "register",
        {
            # Legacy DesktopNodeService field: true means this local workstation
            # can currently execute its advertised tools. Blender-facing APIs
            # translate it to hub_available.
            "fusion_available": True,
            "tools": tools,
            "telemetry": telemetry,
        },
    )
    keepalive_task = asyncio.create_task(
        keepalive(
            bridge,
            tools,
            heartbeat_seconds,
            fusion_url=None,
            telemetry=telemetry,
        )
    )
    if status_sink is not None:
        status_sink({
            "type": "connected",
            "providers": runtime.provider_status(),
            "tool_count": len(tools),
        })
    print(
        f"Blender Hub connected: providers={len(runtime.transports)} tools={len(tools)}",
        flush=True,
    )
    try:
        while True:
            command = (
                await bridge.post("claim", query=f"?wait={claim_wait_seconds:g}")
            ).get("command")
            if command is None:
                continue
            command_id = command["command_id"]
            try:
                result = await runtime.dispatch(
                    command["tool_name"], command.get("arguments", {})
                )
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
                    raise
                result = {
                    "status": "failed",
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
            await submit_result_safely(
                bridge,
                command_id,
                result,
                tools=tools,
                fusion_available=True,
                outbox=outbox,
            )
            telemetry["result_outbox_count"] = outbox.count()
            telemetry["result_delivery_degraded"] = bool(telemetry["result_outbox_count"])
    finally:
        keepalive_task.cancel()
        with suppress(asyncio.CancelledError):
            await keepalive_task
        await runtime.close()
        await bridge.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Development Bridge Blender Hub")
    parser.add_argument("--bridge-url", required=True)
    parser.add_argument("--node-id", default="blender-workstation")
    parser.add_argument("--token", default=os.environ.get("DEVELOPMENT_BRIDGE_DESKTOP_TOKEN"))
    parser.add_argument(
        "--providers",
        type=Path,
        default=Path(__file__).with_name("blender_hub_providers.json"),
    )
    parser.add_argument("--heartbeat-seconds", type=float, default=10.0)
    parser.add_argument("--claim-wait-seconds", type=float, default=20.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not args.token:
        raise SystemExit("DEVELOPMENT_BRIDGE_DESKTOP_TOKEN or --token is required")
    asyncio.run(
        run(
            bridge_url=args.bridge_url,
            node_id=args.node_id,
            token=args.token,
            provider_config_path=args.providers,
            heartbeat_seconds=args.heartbeat_seconds,
            claim_wait_seconds=args.claim_wait_seconds,
        )
    )


if __name__ == "__main__":
    main()
