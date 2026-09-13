from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from app.blender_hub.catalog import (
    NamespacedToolCatalog,
    ProviderState,
    ProviderStatus,
    ProviderTool,
)
from app.blender_hub.providers import (
    HttpProviderConfig,
    ProviderConfig,
    ProviderConnector,
    ProviderSession,
    ProviderSessionFailure,
    ProviderKind,
    StdioProviderConfig,
    UpstreamTool,
)

DCC_CANONICAL_TOOLS = frozenset({"search", "describe", "load_skill", "call"})


class ProviderSessionUnavailable(RuntimeError):
    def __init__(self, provider_id: str, tool_name: str) -> None:
        self.provider_id = provider_id
        self.tool_name = tool_name
        self.phase = "call"
        super().__init__(f"provider_session_unavailable:{provider_id}:{tool_name}")


class ProviderToolStale(RuntimeError):
    def __init__(self, provider_id: str, tool_name: str) -> None:
        self.provider_id = provider_id
        self.tool_name = tool_name
        self.phase = "call"
        super().__init__(f"provider_tool_stale:{provider_id}:{tool_name}")


class ProviderCallFailure(RuntimeError):
    def __init__(
        self,
        provider_id: str,
        tool_name: str,
        phase: str = "call",
        exception_type: str = "Exception",
    ) -> None:
        self.provider_id = provider_id
        self.tool_name = tool_name
        self.phase = phase
        self.exception_type = exception_type
        super().__init__(
            f"provider_call_failure:{provider_id}:{tool_name}:{phase}:{exception_type}"
        )


@dataclass(slots=True)
class _Runtime:
    config: ProviderConfig
    session: ProviderSession | None = None
    usable: bool = False
    publication_generation: int = 0
    selected: tuple[UpstreamTool, ...] = ()
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _snapshot_config(config: ProviderConfig) -> ProviderConfig:
    if isinstance(config, HttpProviderConfig):
        return HttpProviderConfig(
            config.provider_id,
            config.namespace,
            config.kind,
            config.url,
            config.read_timeout_seconds,
        )
    if isinstance(config, StdioProviderConfig):
        environment = dict(config.env)
        return StdioProviderConfig(
            config.provider_id,
            config.namespace,
            config.kind,
            config.argv,
            config.cwd,
            environment,
            config.read_timeout_seconds,
        )
    raise TypeError("configs must contain provider configurations")


def _select_surface(
    config: ProviderConfig, tools: Iterable[UpstreamTool]
) -> tuple[UpstreamTool, ...] | None:
    selected = tuple(tools)
    if config.kind is not ProviderKind.DCC_GATEWAY:
        return selected
    by_name = {tool.name: tool for tool in selected if tool.name in DCC_CANONICAL_TOOLS}
    if set(by_name) != DCC_CANONICAL_TOOLS:
        return None
    return tuple(tool for tool in selected if tool.name in DCC_CANONICAL_TOOLS)


def _retain_usable_after_publication_failure(
    previous: Iterable[UpstreamTool], selected: Iterable[UpstreamTool]
) -> bool:
    return {tool.name for tool in previous}.issubset({tool.name for tool in selected})


class ProviderSupervisor:
    def __init__(
        self,
        configs: Iterable[ProviderConfig],
        catalog: NamespacedToolCatalog,
        connector_for: Callable[[ProviderConfig], ProviderConnector],
    ) -> None:
        snapshots = tuple(_snapshot_config(config) for config in configs)
        provider_ids: set[str] = set()
        namespaces: set[str] = set()
        for config in snapshots:
            if config.provider_id in provider_ids:
                raise ValueError(f"duplicate provider_id: {config.provider_id}")
            if config.namespace in namespaces:
                raise ValueError(f"duplicate namespace: {config.namespace}")
            provider_ids.add(config.provider_id)
            namespaces.add(config.namespace)
        self._catalog = catalog
        self._connector_for = connector_for
        self._runtimes = {config.provider_id: _Runtime(config) for config in snapshots}
        for config in snapshots:
            catalog.register_provider(config.provider_id, config.namespace, ())
            catalog.set_provider_status(
                config.provider_id, ProviderState.OFFLINE, "not_connected"
            )

    def _status(self, provider_id: str) -> ProviderStatus:
        return next(
            status
            for status in self._catalog.provider_statuses()
            if status.provider_id == provider_id
        )

    def _set_status(
        self, runtime: _Runtime, state: ProviderState, error: str | None = None
    ) -> ProviderStatus:
        self._catalog.set_provider_status(runtime.config.provider_id, state, error)
        return self._status(runtime.config.provider_id)

    def _clear(self, runtime: _Runtime, error: str) -> int:
        generation = runtime.publication_generation + 1
        self._catalog.register_provider(
            runtime.config.provider_id, runtime.config.namespace, ()
        )
        runtime.publication_generation = generation
        runtime.selected = ()
        runtime.session = None
        runtime.usable = False
        self._set_status(runtime, ProviderState.OFFLINE, error)
        return generation

    async def _close_best_effort(self, session: ProviderSession) -> ProviderSessionFailure | None:
        try:
            await session.close()
        except asyncio.CancelledError:
            raise
        except ProviderSessionFailure as exc:
            return exc
        return None

    async def _cleanup_after_primary(self, session: ProviderSession) -> None:
        try:
            await self._close_best_effort(session)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    def _build_publication(
        self,
        runtime: _Runtime,
        selected: Iterable[UpstreamTool],
        generation: int,
    ) -> tuple[ProviderTool, ...]:
        return tuple(
            ProviderTool(
                name=tool.name,
                handler=self._handler(runtime, tool.name, generation),
                metadata=tool.annotations,
                title=tool.title,
                description=tool.description,
                input_schema=tool.input_schema,
                output_schema=tool.output_schema,
                publication_metadata=tool.publication_metadata,
            )
            for tool in selected
        )

    def _handler(self, runtime: _Runtime, tool_name: str, generation: int):
        async def invoke(arguments: dict[str, object]) -> object:
            wrapper: ProviderCallFailure | None = None
            result: object | None = None
            async with runtime.lock:
                if generation != runtime.publication_generation:
                    raise ProviderToolStale(runtime.config.provider_id, tool_name) from None
                session = runtime.session
                if not runtime.usable or session is None:
                    raise ProviderSessionUnavailable(
                        runtime.config.provider_id, tool_name
                    ) from None
                try:
                    result = await session.call_tool(tool_name, arguments)
                except asyncio.CancelledError:
                    raise
                except ProviderSessionFailure as exc:
                    exception_type = exc.exception_type
                else:
                    return result
                runtime.session = None
                runtime.usable = False
                self._set_status(
                    runtime,
                    ProviderState.DEGRADED,
                    f"call:{exception_type}",
                )
                await self._cleanup_after_primary(session)
                wrapper = ProviderCallFailure(
                    runtime.config.provider_id,
                    tool_name,
                    exception_type=exception_type,
                )
            assert wrapper is not None
            raise wrapper from None

        return invoke

    async def connect(self, provider_id: str) -> ProviderStatus:
        return await self._replace(provider_id)

    async def reconnect(self, provider_id: str) -> ProviderStatus:
        return await self._replace(provider_id)

    async def _replace(self, provider_id: str) -> ProviderStatus:
        runtime = self._runtimes[provider_id]
        async with runtime.lock:
            old = runtime.session
            self._clear(runtime, "replacement_started")
            if old is not None:
                try:
                    issue = await self._close_best_effort(old)
                except asyncio.CancelledError:
                    self._set_status(runtime, ProviderState.OFFLINE, "replacement_cancelled:close")
                    raise
                except Exception as exc:
                    self._set_status(
                        runtime,
                        ProviderState.OFFLINE,
                        f"local_abort:close:{type(exc).__name__}",
                    )
                    raise
                if issue is not None:
                    return self._set_status(
                        runtime,
                        ProviderState.OFFLINE,
                        f"close:{issue.exception_type}",
                    )

            candidate: ProviderSession | None = None
            phase = "connect"
            primary: BaseException | None = None
            try:
                connector = self._connector_for(runtime.config)
                candidate = await connector.connect(runtime.config)
                phase = "initialize"
                await candidate.initialize()
                phase = "list"
                discovered = await candidate.list_tools()
                phase = "policy"
                selected = _select_surface(runtime.config, discovered)
                if selected is None:
                    rejected = candidate
                    candidate = None
                    await self._close_best_effort(rejected)
                    return self._set_status(
                        runtime,
                        ProviderState.OFFLINE,
                        "canonical_surface_incomplete",
                    )
                phase = "publication"
                generation = runtime.publication_generation
                publication = self._build_publication(runtime, selected, generation)
                self._catalog.register_provider(
                    runtime.config.provider_id, runtime.config.namespace, publication
                )
                runtime.session = candidate
                runtime.usable = True
                runtime.selected = selected
                runtime.publication_generation = generation
                candidate = None
                return self._set_status(runtime, ProviderState.ONLINE)
            except asyncio.CancelledError as exc:
                primary = exc
                self._set_status(
                    runtime, ProviderState.OFFLINE, f"replacement_cancelled:{phase}"
                )
            except ProviderSessionFailure as exc:
                primary = exc
                self._set_status(
                    runtime,
                    ProviderState.OFFLINE,
                    f"{exc.phase}:{exc.exception_type}",
                )
            except Exception as exc:
                primary = exc
                self._set_status(
                    runtime,
                    ProviderState.OFFLINE,
                    f"local_abort:{phase}:{type(exc).__name__}",
                )
            if candidate is not None:
                await self._cleanup_after_primary(candidate)
            assert primary is not None
            if isinstance(primary, ProviderSessionFailure):
                return self._status(provider_id)
            raise primary from None

    async def refresh(self, provider_id: str) -> ProviderStatus:
        runtime = self._runtimes[provider_id]
        async with runtime.lock:
            session = runtime.session
            if not runtime.usable or session is None:
                return self._status(provider_id)
            try:
                discovered = await session.list_tools()
            except asyncio.CancelledError:
                raise
            except ProviderSessionFailure as exc:
                runtime.session = None
                runtime.usable = False
                result = self._set_status(
                    runtime, ProviderState.DEGRADED, f"{exc.phase}:{exc.exception_type}"
                )
                await self._close_best_effort(session)
                return result

            selected = _select_surface(runtime.config, discovered)
            if selected is None:
                try:
                    return await self._quarantine(
                        runtime, session, "canonical_surface_incomplete"
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as primary:
                    if runtime.session is session:
                        await self._abort_quarantine(runtime, session, primary)
                    raise primary from None
            generation = runtime.publication_generation + 1
            publication = self._build_publication(runtime, selected, generation)
            try:
                self._catalog.register_provider(
                    runtime.config.provider_id, runtime.config.namespace, publication
                )
            except asyncio.CancelledError:
                raise
            except Exception as primary:
                if _retain_usable_after_publication_failure(runtime.selected, selected):
                    self._set_status(
                        runtime,
                        ProviderState.DEGRADED,
                        f"publication:{type(primary).__name__}",
                    )
                    raise
                try:
                    await self._quarantine(
                        runtime,
                        session,
                        f"publication:{type(primary).__name__}",
                        cleanup_primary=True,
                    )
                except Exception:
                    await self._abort_quarantine(runtime, session, primary)
                raise primary from None
            runtime.publication_generation = generation
            runtime.selected = selected
            runtime.session = session
            runtime.usable = True
            return self._set_status(runtime, ProviderState.ONLINE)

    async def _quarantine(
        self,
        runtime: _Runtime,
        session: ProviderSession,
        error: str,
        *,
        cleanup_primary: bool = False,
    ) -> ProviderStatus:
        generation = runtime.publication_generation + 1
        retained = self._build_publication(runtime, runtime.selected, generation)
        self._catalog.register_provider(
            runtime.config.provider_id, runtime.config.namespace, retained
        )
        runtime.publication_generation = generation
        runtime.session = None
        runtime.usable = False
        result = self._set_status(runtime, ProviderState.DEGRADED, error)
        if cleanup_primary:
            await self._cleanup_after_primary(session)
        else:
            await self._close_best_effort(session)
        return result

    async def _abort_quarantine(
        self, runtime: _Runtime, session: ProviderSession, primary: Exception
    ) -> None:
        generation = runtime.publication_generation + 1
        self._catalog.register_provider(
            runtime.config.provider_id, runtime.config.namespace, ()
        )
        runtime.publication_generation = generation
        runtime.selected = ()
        runtime.session = None
        runtime.usable = False
        self._set_status(
            runtime,
            ProviderState.DEGRADED,
            f"publication_abort:{type(primary).__name__}",
        )
        await self._cleanup_after_primary(session)

    async def close(self, provider_id: str) -> ProviderStatus:
        runtime = self._runtimes[provider_id]
        async with runtime.lock:
            session = runtime.session
            self._clear(runtime, "not_connected")
            if session is not None:
                issue = await self._close_best_effort(session)
                if issue is not None:
                    return self._set_status(
                        runtime, ProviderState.OFFLINE, f"close:{issue.exception_type}"
                    )
            return self._status(provider_id)

    async def close_all(self) -> tuple[ProviderStatus, ...]:
        statuses = []
        primary: Exception | None = None
        for provider_id in self._runtimes:
            try:
                statuses.append(await self.close(provider_id))
            except Exception as exc:
                if primary is None:
                    primary = exc
        if primary is not None:
            raise primary from None
        return tuple(statuses)

    async def invoke(
        self, qualified_name: str, arguments: dict[str, object]
    ) -> object:
        if not isinstance(arguments, dict) or any(
            not isinstance(key, str) for key in arguments
        ):
            raise TypeError("arguments must be a dict with string keys")
        return await self._catalog.invoke(qualified_name, arguments)
