from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.blender_hub.providers as providers_module
import app.blender_hub.supervisor as supervisor_module
from app.blender_hub.catalog import NamespacedToolCatalog, ProviderState
from app.blender_hub.providers import (
    HttpProviderConfig,
    ProviderConnectionError,
    ProviderKind,
    ProviderSessionFailure,
    StdioProviderConfig,
    UpstreamTool,
)
from app.blender_hub.supervisor import (
    ProviderCallFailure,
    ProviderSessionUnavailable,
    ProviderSupervisor,
    ProviderToolStale,
)


def upstream(
    name: str,
    *,
    read_only: bool = True,
    marker: str = "accepted",
) -> UpstreamTool:
    annotations = {"readOnlyHint": True} if read_only else {}
    return UpstreamTool(
        name=name,
        title=f"Title {name}",
        description=f"Description {name}",
        input_schema={"type": "object", "marker": marker},
        output_schema={"type": "object", "required": [marker]},
        annotations=annotations,
        publication_metadata={"_meta": {"marker": marker}},
    )


@dataclass
class FakeSession:
    tools: tuple[UpstreamTool, ...]
    result: object = field(default_factory=lambda: {"ok": True})
    initialize_error: BaseException | None = None
    list_error: BaseException | None = None
    call_error: BaseException | None = None
    close_error: BaseException | None = None
    calls: list[tuple[str, dict[str, object]]] = field(default_factory=list)
    initialized: int = 0
    listed: int = 0
    closed: int = 0

    async def initialize(self) -> None:
        self.initialized += 1
        if self.initialize_error is not None:
            raise self.initialize_error

    async def list_tools(self) -> tuple[UpstreamTool, ...]:
        self.listed += 1
        if self.list_error is not None:
            raise self.list_error
        return self.tools

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        self.calls.append((name, arguments))
        if self.call_error is not None:
            raise self.call_error
        return self.result

    async def close(self) -> None:
        self.closed += 1
        if self.close_error is not None:
            raise self.close_error


class ConversionFailingTool:
    def __init__(self, conversion_error: BaseException) -> None:
        self.conversion_error = conversion_error

    def model_dump(self, **_kwargs):
        raise self.conversion_error


class ConversionSdkSession:
    def __init__(self, conversion_error: BaseException) -> None:
        self.tool = ConversionFailingTool(conversion_error)
        self.list_succeeded = 0

    async def initialize(self) -> None:
        pass

    async def list_tools(self):
        result = SimpleNamespace(tools=(self.tool,))
        self.list_succeeded += 1
        return result


class TrackingMcpProviderSession(providers_module._McpProviderSession):
    def __init__(self, sdk_session: ConversionSdkSession) -> None:
        super().__init__("research-main", None, AsyncExitStack(), sdk_session)
        self.closed = 0

    async def close(self) -> None:
        self.closed += 1
        await super().close()


class QueueConnector:
    def __init__(
        self,
        *outcomes: FakeSession | TrackingMcpProviderSession | BaseException,
    ):
        self.outcomes = list(outcomes)
        self.configs: list[object] = []

    async def connect(
        self, config: object
    ) -> FakeSession | TrackingMcpProviderSession:
        self.configs.append(config)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def research_config(provider_id: str = "research-main", namespace: str = "research"):
    return HttpProviderConfig(
        provider_id,
        namespace,
        ProviderKind.RESEARCH,
        "http://localhost:8123/mcp",
    )


def status(catalog: NamespacedToolCatalog, provider_id: str):
    return next(s for s in catalog.provider_statuses() if s.provider_id == provider_id)


def published(catalog: NamespacedToolCatalog, provider_id: str):
    return tuple(t for t in catalog.list_tools() if t.provider_id == provider_id)


def descriptor_evidence(tool):
    return (
        tool.name,
        tool.title,
        tool.description,
        tool.input_schema,
        tool.output_schema,
        tool.metadata,
        tool.publication_metadata,
        tool.mutating,
    )


# Phase 1: destructive replacement lifecycle and provider isolation.
def test_constructor_snapshots_configs_and_registers_all_offline_atomically():
    catalog = NamespacedToolCatalog()
    env = {"SAFE": "one"}
    config = StdioProviderConfig(
        "orca-main", "orca", ProviderKind.ORCA, ("orca-mcp",), Path("/tmp"), env
    )
    connector = QueueConnector(FakeSession((upstream("slice"),)))
    supervisor = ProviderSupervisor([config], catalog, lambda _config: connector)

    object.__setattr__(config, "namespace", "mutated")
    object.__setattr__(config, "argv", ("malicious",))
    env["SAFE"] = "changed"

    assert published(catalog, "orca-main") == ()
    assert status(catalog, "orca-main").state is ProviderState.OFFLINE
    assert status(catalog, "orca-main").error == "not_connected"
    assert supervisor is not None


def test_constructor_rejects_duplicates_before_any_catalog_mutation():
    catalog = NamespacedToolCatalog()
    first = research_config("one", "shared")
    duplicate = research_config("two", "shared")

    with pytest.raises(ValueError, match="namespace"):
        ProviderSupervisor([first, duplicate], catalog, lambda _config: QueueConnector())

    assert catalog.provider_statuses() == ()
    assert catalog.list_tools() == ()


@pytest.mark.asyncio
async def test_connect_is_destructive_and_reconnect_recovers_after_typed_failure():
    catalog = NamespacedToolCatalog()
    first = FakeSession((upstream("lookup"),))
    candidate = FakeSession(
        (upstream("replacement"),),
        initialize_error=ProviderSessionFailure("research-main", "initialize", "SdkSecret"),
    )
    recovered = FakeSession((upstream("recovered"),))
    connector = QueueConnector(first, candidate, recovered)
    supervisor = ProviderSupervisor(
        [research_config()], catalog, lambda _config: connector
    )

    assert (await supervisor.connect("research-main")).state is ProviderState.ONLINE
    old_handler = published(catalog, "research-main")[0].handler
    failed = await supervisor.reconnect("research-main")

    assert first.closed == 1
    assert candidate.closed == 1
    assert failed.state is ProviderState.OFFLINE
    assert "SdkSecret" in (failed.error or "")
    assert published(catalog, "research-main") == ()
    with pytest.raises(ProviderToolStale) as stale:
        await old_handler({})
    assert stale.value.__cause__ is None
    assert (await supervisor.reconnect("research-main")).state is ProviderState.ONLINE
    assert [tool.name for tool in published(catalog, "research-main")] == ["recovered"]


@pytest.mark.asyncio
async def test_old_close_typed_failure_stops_before_candidate_creation():
    catalog = NamespacedToolCatalog()
    old = FakeSession(
        (upstream("lookup"),),
        close_error=ProviderSessionFailure("research-main", "close", "CloseFailure"),
    )
    unused = FakeSession((upstream("never"),))
    connector = QueueConnector(old, unused)
    supervisor = ProviderSupervisor([research_config()], catalog, lambda _c: connector)
    await supervisor.connect("research-main")

    failed = await supervisor.reconnect("research-main")

    assert failed.state is ProviderState.OFFLINE
    assert "CloseFailure" in (failed.error or "")
    assert len(connector.configs) == 1
    assert unused.initialized == 0
    assert published(catalog, "research-main") == ()


@pytest.mark.asyncio
async def test_old_close_programming_failure_propagates_and_stops_candidate():
    catalog = NamespacedToolCatalog()
    primary = RuntimeError("close-programming-secret")
    old = FakeSession((upstream("lookup"),), close_error=primary)
    unused = FakeSession((upstream("never"),))
    connector = QueueConnector(old, unused)
    supervisor = ProviderSupervisor([research_config()], catalog, lambda _c: connector)
    await supervisor.connect("research-main")

    with pytest.raises(RuntimeError) as raised:
        await supervisor.reconnect("research-main")

    assert raised.value is primary
    assert len(connector.configs) == 1
    assert published(catalog, "research-main") == ()
    assert "close-programming-secret" not in (status(catalog, "research-main").error or "")


@pytest.mark.asyncio
async def test_non_sdk_candidate_failure_closes_once_and_propagates_original():
    catalog = NamespacedToolCatalog()
    primary = RuntimeError("do-not-leak-primary")
    candidate = FakeSession((upstream("x"),), list_error=primary)
    connector = QueueConnector(candidate)
    supervisor = ProviderSupervisor([research_config()], catalog, lambda _c: connector)

    with pytest.raises(RuntimeError) as raised:
        await supervisor.connect("research-main")

    assert raised.value is primary
    assert candidate.closed == 1
    current = status(catalog, "research-main")
    assert current.state is ProviderState.OFFLINE
    assert "do-not-leak-primary" not in (current.error or "")
    assert published(catalog, "research-main") == ()


@pytest.mark.asyncio
async def test_candidate_cleanup_programming_failure_does_not_replace_primary():
    catalog = NamespacedToolCatalog()
    primary = RuntimeError("primary-secret")
    candidate = FakeSession(
        (upstream("x"),), list_error=primary, close_error=ValueError("cleanup-secret")
    )
    supervisor = ProviderSupervisor(
        [research_config()], catalog, lambda _c: QueueConnector(candidate)
    )

    with pytest.raises(RuntimeError) as raised:
        await supervisor.connect("research-main")

    assert raised.value is primary
    assert candidate.closed == 1
    assert "primary-secret" not in (status(catalog, "research-main").error or "")
    assert "cleanup-secret" not in (status(catalog, "research-main").error or "")


@pytest.mark.asyncio
async def test_close_all_continues_siblings_after_sanitized_close_failure():
    catalog = NamespacedToolCatalog()
    bad = FakeSession(
        (upstream("bad"),),
        close_error=ProviderSessionFailure("bad", "close", "BrokenClose"),
    )
    good = FakeSession((upstream("good"),))
    connectors = {"bad": QueueConnector(bad), "good": QueueConnector(good)}
    configs = [research_config("bad", "badns"), research_config("good", "goodns")]
    supervisor = ProviderSupervisor(configs, catalog, lambda c: connectors[c.provider_id])
    await asyncio.gather(supervisor.connect("bad"), supervisor.connect("good"))

    statuses = await supervisor.close_all()

    assert bad.closed == good.closed == 1
    assert {item.provider_id for item in statuses} == {"bad", "good"}
    assert all(item.state is ProviderState.OFFLINE for item in statuses)
    assert catalog.list_tools() == ()


@pytest.mark.asyncio
async def test_close_all_continues_siblings_then_reraises_unexpected_close_failure():
    catalog = NamespacedToolCatalog()
    primary = RuntimeError("close-programming-secret")
    bad = FakeSession((upstream("bad"),), close_error=primary)
    good = FakeSession((upstream("good"),))
    connectors = {"bad": QueueConnector(bad), "good": QueueConnector(good)}
    configs = [research_config("bad", "badns"), research_config("good", "goodns")]
    supervisor = ProviderSupervisor(configs, catalog, lambda c: connectors[c.provider_id])
    await asyncio.gather(supervisor.connect("bad"), supervisor.connect("good"))

    with pytest.raises(RuntimeError) as raised:
        await supervisor.close_all()

    assert raised.value is primary
    assert raised.value.__cause__ is None
    assert bad.closed == good.closed == 1
    assert catalog.list_tools() == ()


# Phase 2: generation, registration, and refresh.
@pytest.mark.asyncio
async def test_refresh_replaces_generation_and_makes_captured_handler_stale():
    catalog = NamespacedToolCatalog()
    session = FakeSession((upstream("lookup", marker="v1"),))
    connector = QueueConnector(session)
    supervisor = ProviderSupervisor([research_config()], catalog, lambda _c: connector)
    await supervisor.connect("research-main")
    old = published(catalog, "research-main")[0].handler
    session.tools = (upstream("lookup", marker="v2"),)

    refreshed = await supervisor.refresh("research-main")

    assert refreshed.state is ProviderState.ONLINE
    with pytest.raises(ProviderToolStale) as raised:
        await old({})
    assert raised.value.__cause__ is None
    assert await supervisor.invoke("research.lookup", {"q": "new"}) == {"ok": True}
    assert session.calls == [("lookup", {"q": "new"})]
    assert published(catalog, "research-main")[0].input_schema["marker"] == "v2"


@pytest.mark.asyncio
async def test_typed_refresh_failure_retains_evidence_but_detaches_session():
    catalog = NamespacedToolCatalog()
    session = FakeSession((upstream("lookup"),))
    supervisor = ProviderSupervisor(
        [research_config()], catalog, lambda _c: QueueConnector(session)
    )
    await supervisor.connect("research-main")
    before = published(catalog, "research-main")[0]
    session.list_error = ProviderSessionFailure("research-main", "list", "SdkDown")

    refreshed = await supervisor.refresh("research-main")

    after = published(catalog, "research-main")[0]
    assert refreshed.state is ProviderState.DEGRADED
    assert before.input_schema == after.input_schema
    assert session.closed == 1
    with pytest.raises(ProviderSessionUnavailable) as raised:
        await after.handler({})
    assert raised.value.__cause__ is None
    assert session.calls == []


@pytest.mark.asyncio
async def test_refresh_registration_failure_retains_usable_old_surface_when_complete(monkeypatch):
    catalog = NamespacedToolCatalog()
    session = FakeSession((upstream("a"), upstream("b")))
    supervisor = ProviderSupervisor(
        [research_config()], catalog, lambda _c: QueueConnector(session)
    )
    await supervisor.connect("research-main")
    old = {t.name: t for t in published(catalog, "research-main")}
    session.tools = (upstream("a", marker="new"), upstream("b", marker="new"), upstream("c"))
    original_register = catalog.register_provider
    failure = RuntimeError("registration-secret")

    def reject(*_args: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(catalog, "register_provider", reject)
    with pytest.raises(RuntimeError) as raised:
        await supervisor.refresh("research-main")
    monkeypatch.setattr(catalog, "register_provider", original_register)

    assert raised.value is failure
    assert status(catalog, "research-main").state is ProviderState.DEGRADED
    assert "registration-secret" not in (status(catalog, "research-main").error or "")
    assert await old["a"].handler({}) == {"ok": True}
    assert session.closed == 0


@pytest.mark.asyncio
async def test_missing_prior_name_registration_failure_quarantines_retained_evidence(monkeypatch):
    catalog = NamespacedToolCatalog()
    session = FakeSession((upstream("a", marker="old"), upstream("b", marker="old")))
    supervisor = ProviderSupervisor(
        [research_config()], catalog, lambda _c: QueueConnector(session)
    )
    await supervisor.connect("research-main")
    old_handler = published(catalog, "research-main")[0].handler
    session.tools = (upstream("a", marker="new"),)
    original = catalog.register_provider
    calls = 0
    primary = RuntimeError("primary-publication-secret")

    def fail_new_then_accept_retained(provider_id, namespace, tools):
        nonlocal calls
        calls += 1
        materialized = tuple(tools)
        if calls == 1:
            raise primary
        return original(provider_id, namespace, materialized)

    monkeypatch.setattr(catalog, "register_provider", fail_new_then_accept_retained)
    with pytest.raises(RuntimeError) as raised:
        await supervisor.refresh("research-main")

    assert raised.value is primary
    assert session.closed == 1
    retained = published(catalog, "research-main")
    assert {t.name for t in retained} == {"a", "b"}
    assert all(t.input_schema["marker"] == "old" for t in retained)
    with pytest.raises(ProviderToolStale):
        await old_handler({})
    with pytest.raises(ProviderSessionUnavailable):
        await retained[0].handler({})


# Phase 3: bounded DCC surface policy.
def dcc_tools(*, missing: str | None = None, extra: bool = False):
    names = ["search", "describe", "load_skill", "call"]
    tools = [
        upstream(name, read_only=name != "call", marker=f"dcc-{name}")
        for name in names
        if name != missing
    ]
    if extra:
        tools.extend((upstream("scene_dump"), upstream("unsafe_alias")))
    return tuple(tools)


def dcc_config():
    return HttpProviderConfig(
        "dcc-main", "dcc", ProviderKind.DCC_GATEWAY, "http://localhost:8124/mcp"
    )


@pytest.mark.asyncio
async def test_dcc_publishes_exactly_canonical_tools_and_ignores_aliases():
    catalog = NamespacedToolCatalog()
    session = FakeSession(dcc_tools(extra=True))
    supervisor = ProviderSupervisor([dcc_config()], catalog, lambda _c: QueueConnector(session))

    connected = await supervisor.connect("dcc-main")

    assert connected.state is ProviderState.ONLINE
    assert {t.name for t in published(catalog, "dcc-main")} == {
        "search", "describe", "load_skill", "call"
    }


@pytest.mark.asyncio
async def test_incomplete_initial_dcc_surface_is_closed_and_offline():
    catalog = NamespacedToolCatalog()
    session = FakeSession(dcc_tools(missing="call", extra=True))
    supervisor = ProviderSupervisor([dcc_config()], catalog, lambda _c: QueueConnector(session))

    connected = await supervisor.connect("dcc-main")

    assert connected.state is ProviderState.OFFLINE
    assert connected.error == "canonical_surface_incomplete"
    assert session.closed == 1
    assert published(catalog, "dcc-main") == ()


@pytest.mark.asyncio
async def test_incomplete_dcc_refresh_republishes_exact_retained_evidence_unusable():
    catalog = NamespacedToolCatalog()
    session = FakeSession(dcc_tools(extra=True))
    supervisor = ProviderSupervisor([dcc_config()], catalog, lambda _c: QueueConnector(session))
    await supervisor.connect("dcc-main")
    old = {tool.name: tool for tool in published(catalog, "dcc-main")}
    session.tools = dcc_tools(missing="describe", extra=True)

    refreshed = await supervisor.refresh("dcc-main")

    assert refreshed.state is ProviderState.DEGRADED
    assert refreshed.error == "canonical_surface_incomplete"
    assert session.closed == 1
    fresh = {tool.name: tool for tool in published(catalog, "dcc-main")}
    assert set(fresh) == set(old)
    assert {
        name: descriptor_evidence(tool) for name, tool in fresh.items()
    } == {
        name: descriptor_evidence(tool) for name, tool in old.items()
    }
    with pytest.raises(ProviderToolStale):
        await old["search"].handler({})
    with pytest.raises(ProviderToolStale):
        await old["call"].handler({})
    with pytest.raises(ProviderSessionUnavailable):
        await fresh["search"].handler({})
    with pytest.raises(ProviderSessionUnavailable):
        await fresh["call"].handler({})
    assert session.calls == []


@pytest.mark.asyncio
async def test_incomplete_dcc_retained_republish_failure_clears_and_quarantines(monkeypatch):
    catalog = NamespacedToolCatalog()
    session = FakeSession(dcc_tools())
    supervisor = ProviderSupervisor([dcc_config()], catalog, lambda _c: QueueConnector(session))
    await supervisor.connect("dcc-main")
    old = published(catalog, "dcc-main")[0].handler
    session.tools = dcc_tools(missing="call")
    original = catalog.register_provider
    primary = RuntimeError("retained-republish-secret")
    calls = 0

    def fail_retained_then_clear(provider_id, namespace, tools):
        nonlocal calls
        calls += 1
        materialized = tuple(tools)
        if calls == 1:
            raise primary
        return original(provider_id, namespace, materialized)

    monkeypatch.setattr(catalog, "register_provider", fail_retained_then_clear)
    with pytest.raises(RuntimeError) as raised:
        await supervisor.refresh("dcc-main")

    assert raised.value is primary
    assert published(catalog, "dcc-main") == ()
    assert session.closed == 1
    assert status(catalog, "dcc-main").state is ProviderState.DEGRADED
    assert "retained-republish-secret" not in (status(catalog, "dcc-main").error or "")
    with pytest.raises(ProviderToolStale):
        await old({})


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [ProviderKind.THREE_MF, ProviderKind.ORCA, ProviderKind.RESEARCH])
async def test_non_dcc_providers_publish_every_discovered_tool(kind: ProviderKind):
    catalog = NamespacedToolCatalog()
    config = HttpProviderConfig("local", "tools", kind, "http://localhost:8125/mcp")
    session = FakeSession((upstream("one"), upstream("two"), upstream("three")))
    supervisor = ProviderSupervisor([config], catalog, lambda _c: QueueConnector(session))

    await supervisor.connect("local")

    assert {tool.name for tool in published(catalog, "local")} == {"one", "two", "three"}


# Phase 4: invocation, stale handlers, and locking.
@pytest.mark.asyncio
async def test_invoke_validates_arguments_then_delegates_to_catalog(monkeypatch):
    catalog = NamespacedToolCatalog()
    supervisor = ProviderSupervisor([research_config()], catalog, lambda _c: QueueConnector())
    seen: list[tuple[str, dict[str, object]]] = []

    async def invoke(name: str, arguments: dict[str, object]):
        seen.append((name, arguments))
        return "delegated"

    monkeypatch.setattr(catalog, "invoke", invoke)
    arguments = {"query": "mesh"}
    assert await supervisor.invoke("research.lookup", arguments) == "delegated"
    assert seen == [("research.lookup", arguments)]
    with pytest.raises(TypeError):
        await supervisor.invoke("research.lookup", [])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        await supervisor.invoke("research.lookup", {1: "bad"})  # type: ignore[dict-item]


@pytest.mark.asyncio
async def test_typed_call_failure_detaches_once_and_raises_sanitized_wrapper():
    catalog = NamespacedToolCatalog()
    session = FakeSession(
        (upstream("lookup"),),
        call_error=ProviderSessionFailure("research-main", "call", "TransportSecret"),
    )
    supervisor = ProviderSupervisor([research_config()], catalog, lambda _c: QueueConnector(session))
    await supervisor.connect("research-main")

    with pytest.raises(ProviderCallFailure) as raised:
        await supervisor.invoke("research.lookup", {"secret": "argument"})

    assert raised.value.provider_id == "research-main"
    assert raised.value.tool_name == "lookup"
    assert raised.value.phase == "call"
    assert raised.value.exception_type == "TransportSecret"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert session.closed == 1
    assert status(catalog, "research-main").state is ProviderState.DEGRADED


@pytest.mark.asyncio
async def test_normal_is_error_result_and_programming_exception_are_unchanged():
    catalog = NamespacedToolCatalog()
    result = {"isError": True, "content": [{"type": "text", "text": "provider error"}]}
    session = FakeSession((upstream("lookup"),), result=result)
    supervisor = ProviderSupervisor([research_config()], catalog, lambda _c: QueueConnector(session))
    await supervisor.connect("research-main")
    assert await supervisor.invoke("research.lookup", {}) is result

    primary = ValueError("conversion-bug")
    session.call_error = primary
    with pytest.raises(ValueError) as raised:
        await supervisor.invoke("research.lookup", {})
    assert raised.value is primary
    assert session.closed == 0
    assert status(catalog, "research-main").state is ProviderState.ONLINE


@pytest.mark.asyncio
async def test_same_provider_calls_serialize_while_different_providers_overlap():
    catalog = NamespacedToolCatalog()
    entered = asyncio.Event()
    release = asyncio.Event()

    @dataclass
    class BlockingSession(FakeSession):
        async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
            self.calls.append((name, arguments))
            entered.set()
            await release.wait()
            return self.result

    first = BlockingSession((upstream("read"),))
    second = FakeSession((upstream("read"),))
    connectors = {"one": QueueConnector(first), "two": QueueConnector(second)}
    configs = [research_config("one", "one"), research_config("two", "two")]
    supervisor = ProviderSupervisor(configs, catalog, lambda c: connectors[c.provider_id])
    await asyncio.gather(supervisor.connect("one"), supervisor.connect("two"))

    blocked = asyncio.create_task(supervisor.invoke("one.read", {}))
    await entered.wait()
    assert await supervisor.invoke("two.read", {}) == {"ok": True}
    queued = asyncio.create_task(supervisor.invoke("one.read", {}))
    await asyncio.sleep(0)
    assert len(first.calls) == 1
    release.set()
    await asyncio.gather(blocked, queued)
    assert len(first.calls) == 2


# Phase 5: races and cancellation.
@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["reconnect", "close"])
async def test_lifecycle_waits_for_inflight_call_and_never_redirects(operation: str):
    catalog = NamespacedToolCatalog()
    entered = asyncio.Event()
    release = asyncio.Event()

    @dataclass
    class BlockingSession(FakeSession):
        async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
            self.calls.append((name, arguments))
            entered.set()
            await release.wait()
            return {"owner": "old"}

    old = BlockingSession((upstream("lookup"),))
    replacement = FakeSession((upstream("lookup"),), result={"owner": "new"})
    connector = QueueConnector(old, replacement)
    supervisor = ProviderSupervisor([research_config()], catalog, lambda _c: connector)
    await supervisor.connect("research-main")

    call = asyncio.create_task(supervisor.invoke("research.lookup", {}))
    await entered.wait()
    lifecycle = asyncio.create_task(getattr(supervisor, operation)("research-main"))
    await asyncio.sleep(0)
    assert old.closed == 0
    assert len(connector.configs) == 1
    release.set()
    assert await call == {"owner": "old"}
    await lifecycle
    assert old.closed == 1


@pytest.mark.asyncio
async def test_cancelled_normal_call_does_not_degrade_or_detach_session():
    catalog = NamespacedToolCatalog()
    entered = asyncio.Event()

    @dataclass
    class CancellableSession(FakeSession):
        first: bool = True

        async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
            self.calls.append((name, arguments))
            if self.first:
                self.first = False
                entered.set()
                await asyncio.Event().wait()
            return self.result

    session = CancellableSession((upstream("lookup"),))
    supervisor = ProviderSupervisor([research_config()], catalog, lambda _c: QueueConnector(session))
    await supervisor.connect("research-main")
    call = asyncio.create_task(supervisor.invoke("research.lookup", {}))
    await entered.wait()
    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call

    assert session.closed == 0
    assert status(catalog, "research-main").state is ProviderState.ONLINE
    assert await supervisor.invoke("research.lookup", {}) == {"ok": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["connect", "reconnect"])
@pytest.mark.parametrize("stage", ["initialize", "list"])
async def test_candidate_stage_cancellation_closes_once_and_stays_empty(operation: str, stage: str):
    catalog = NamespacedToolCatalog()
    cancellation = asyncio.CancelledError()
    kwargs = {"initialize_error": cancellation} if stage == "initialize" else {"list_error": cancellation}
    candidate = FakeSession((upstream("lookup"),), **kwargs)
    connector = QueueConnector(candidate)
    supervisor = ProviderSupervisor([research_config()], catalog, lambda _c: connector)

    with pytest.raises(asyncio.CancelledError) as raised:
        await getattr(supervisor, operation)("research-main")

    assert raised.value is cancellation
    assert candidate.closed == 1
    assert published(catalog, "research-main") == ()
    current = status(catalog, "research-main")
    assert current.state is ProviderState.OFFLINE
    assert "replacement_cancelled" in (current.error or "")


@pytest.mark.asyncio
async def test_old_close_cancellation_wins_and_no_candidate_is_created():
    catalog = NamespacedToolCatalog()
    cancellation = asyncio.CancelledError()
    old = FakeSession((upstream("lookup"),), close_error=cancellation)
    candidate = FakeSession((upstream("replacement"),))
    connector = QueueConnector(old, candidate)
    supervisor = ProviderSupervisor([research_config()], catalog, lambda _c: connector)
    await supervisor.connect("research-main")

    with pytest.raises(asyncio.CancelledError) as raised:
        await supervisor.reconnect("research-main")

    assert raised.value is cancellation
    assert len(connector.configs) == 1
    assert candidate.closed == 0
    assert published(catalog, "research-main") == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["connect", "reconnect"])
@pytest.mark.parametrize("stage", ["policy", "publication", "registration"])
async def test_candidate_late_stage_cancellation_cleans_once_and_never_resurrects_old(
    monkeypatch, operation: str, stage: str
):
    catalog = NamespacedToolCatalog()
    old = FakeSession((upstream("old"),))
    candidate = FakeSession((upstream("new"),))
    connector = QueueConnector(*(old, candidate) if operation == "reconnect" else (candidate,))
    supervisor = ProviderSupervisor([research_config()], catalog, lambda _c: connector)
    old_handler = None
    if operation == "reconnect":
        await supervisor.connect("research-main")
        old_handler = published(catalog, "research-main")[0].handler

    cancellation = asyncio.CancelledError()
    if stage == "policy":
        monkeypatch.setattr(
            supervisor_module, "_select_surface", lambda *_args: (_ for _ in ()).throw(cancellation)
        )
    elif stage == "publication":
        monkeypatch.setattr(
            supervisor, "_build_publication", lambda *_args: (_ for _ in ()).throw(cancellation)
        )
    else:
        original = catalog.register_provider

        def cancel_nonempty(provider_id, namespace, tools):
            materialized = tuple(tools)
            if materialized:
                raise cancellation
            return original(provider_id, namespace, materialized)

        monkeypatch.setattr(catalog, "register_provider", cancel_nonempty)

    with pytest.raises(asyncio.CancelledError) as raised:
        await getattr(supervisor, operation)("research-main")

    assert raised.value is cancellation
    assert candidate.closed == 1
    assert old.closed == (1 if operation == "reconnect" else 0)
    assert published(catalog, "research-main") == ()
    assert status(catalog, "research-main").state is ProviderState.OFFLINE
    if old_handler is not None:
        with pytest.raises(ProviderToolStale):
            await old_handler({})
        assert old.calls == []


@pytest.mark.asyncio
async def test_primary_candidate_cancellation_survives_sanitized_cleanup_failure():
    primary = asyncio.CancelledError()
    candidate = FakeSession(
        (upstream("lookup"),),
        list_error=primary,
        close_error=ProviderSessionFailure("research-main", "close", "CleanupFailure"),
    )
    catalog = NamespacedToolCatalog()
    supervisor = ProviderSupervisor(
        [research_config()], catalog, lambda _c: QueueConnector(candidate)
    )

    with pytest.raises(asyncio.CancelledError) as raised:
        await supervisor.connect("research-main")

    assert raised.value is primary
    assert candidate.closed == 1
    assert published(catalog, "research-main") == ()


@pytest.mark.asyncio
async def test_candidate_cleanup_cancellation_wins_over_primary_cancellation():
    primary = asyncio.CancelledError()
    cleanup = asyncio.CancelledError()
    candidate = FakeSession(
        (upstream("lookup"),), list_error=primary, close_error=cleanup
    )
    catalog = NamespacedToolCatalog()
    supervisor = ProviderSupervisor(
        [research_config()], catalog, lambda _c: QueueConnector(candidate)
    )

    with pytest.raises(asyncio.CancelledError) as raised:
        await supervisor.connect("research-main")

    assert raised.value is cleanup
    assert candidate.closed == 1
    assert published(catalog, "research-main") == ()


@pytest.mark.asyncio
async def test_registration_returns_before_runtime_commit_without_await_boundary(monkeypatch):
    catalog = NamespacedToolCatalog()
    candidate = FakeSession((upstream("lookup"),))
    supervisor = ProviderSupervisor(
        [research_config()], catalog, lambda _c: QueueConnector(candidate)
    )
    runtime = supervisor._runtimes["research-main"]
    original = catalog.register_provider
    observations = []

    def observe_registration(provider_id, namespace, tools):
        materialized = tuple(tools)
        result = original(provider_id, namespace, materialized)
        if materialized:
            observations.append(
                (runtime.session, runtime.usable, runtime.selected, runtime.publication_generation)
            )
        return result

    monkeypatch.setattr(catalog, "register_provider", observe_registration)

    result = await supervisor.connect("research-main")

    assert observations == [(None, False, (), 1)]
    assert result.state is ProviderState.ONLINE
    assert runtime.session is candidate and runtime.usable is True
    assert tuple(tool.name for tool in runtime.selected) == ("lookup",)


@pytest.mark.asyncio
async def test_queued_mutating_old_handler_becomes_stale_without_reverse_lock_deadlock():
    catalog = NamespacedToolCatalog()
    session = FakeSession((upstream("write", read_only=False, marker="v1"),))
    supervisor = ProviderSupervisor(
        [research_config()], catalog, lambda _c: QueueConnector(session)
    )
    await supervisor.connect("research-main")
    old = published(catalog, "research-main")[0]

    await catalog._mutation_lock.acquire()
    queued = asyncio.create_task(catalog.invoke("research.write", {}))
    await asyncio.sleep(0)
    session.tools = (upstream("write", read_only=False, marker="v2"),)
    refreshed = asyncio.create_task(supervisor.refresh("research-main"))
    await asyncio.wait_for(refreshed, timeout=0.5)
    catalog._mutation_lock.release()

    with pytest.raises(ProviderToolStale):
        await asyncio.wait_for(queued, timeout=0.5)
    assert session.calls == []
    assert await supervisor.invoke("research.write", {}) == {"ok": True}
    assert session.calls == [("write", {})]
    assert old.mutating is True


@pytest.mark.asyncio
async def test_unusable_retained_surface_recovers_only_after_explicit_reconnect():
    catalog = NamespacedToolCatalog()
    failed = FakeSession((upstream("lookup"),))
    recovered = FakeSession((upstream("lookup", marker="recovered"),))
    connector = QueueConnector(failed, recovered)
    supervisor = ProviderSupervisor([research_config()], catalog, lambda _c: connector)
    await supervisor.connect("research-main")
    failed.list_error = ProviderSessionFailure("research-main", "list", "SdkDown")
    await supervisor.refresh("research-main")

    with pytest.raises(ProviderSessionUnavailable):
        await supervisor.invoke("research.lookup", {})
    assert len(connector.configs) == 1

    assert (await supervisor.reconnect("research-main")).state is ProviderState.ONLINE
    assert await supervisor.invoke("research.lookup", {}) == {"ok": True}
    assert recovered.calls == [("lookup", {})]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["connect", "reconnect"])
@pytest.mark.parametrize("outcome", ["cancel", "ordinary"])
@pytest.mark.parametrize(
    "stage", ["initialize", "list", "conversion", "policy", "publication", "registration"]
)
async def test_every_candidate_stage_exit_is_destructive_owned_and_recoverable(
    monkeypatch, operation: str, outcome: str, stage: str
):
    catalog = NamespacedToolCatalog()
    primary: BaseException = (
        asyncio.CancelledError()
        if outcome == "cancel"
        else RuntimeError("CANDIDATE_STAGE_SECRET")
    )
    old = FakeSession((upstream("old"),))
    conversion_sdk = ConversionSdkSession(primary) if stage == "conversion" else None
    candidate = (
        TrackingMcpProviderSession(conversion_sdk)
        if conversion_sdk is not None
        else FakeSession((upstream("new"),))
    )
    recovered = FakeSession((upstream("recovered"),))
    outcomes = (old, candidate, recovered) if operation == "reconnect" else (candidate, recovered)
    connector = QueueConnector(*outcomes)
    supervisor = ProviderSupervisor([research_config()], catalog, lambda _c: connector)
    old_handler = None
    if operation == "reconnect":
        await supervisor.connect("research-main")
        old_handler = published(catalog, "research-main")[0].handler
    runtime = supervisor._runtimes["research-main"]
    generation_before = runtime.publication_generation

    if stage == "initialize":
        candidate.initialize_error = primary
    elif stage == "list":
        candidate.list_error = primary
    elif stage == "policy":
        monkeypatch.setattr(
            supervisor_module, "_select_surface", lambda *_args: (_ for _ in ()).throw(primary)
        )
    elif stage == "publication":
        monkeypatch.setattr(
            supervisor, "_build_publication", lambda *_args: (_ for _ in ()).throw(primary)
        )
    else:
        original = catalog.register_provider

        def reject_nonempty(provider_id, namespace, tools):
            materialized = tuple(tools)
            if materialized:
                raise primary
            return original(provider_id, namespace, materialized)

        monkeypatch.setattr(catalog, "register_provider", reject_nonempty)

    with pytest.raises(type(primary)) as raised:
        await getattr(supervisor, operation)("research-main")

    assert raised.value is primary
    if stage == "conversion":
        assert conversion_sdk is not None
        assert conversion_sdk.list_succeeded == 1
    assert candidate.closed == 1
    assert old.closed == (1 if operation == "reconnect" else 0)
    assert runtime.session is None and runtime.usable is False
    assert runtime.publication_generation == generation_before + 1
    assert published(catalog, "research-main") == ()
    current = status(catalog, "research-main")
    assert current.state is ProviderState.OFFLINE
    assert "CANDIDATE_STAGE_SECRET" not in (current.error or "")
    if old_handler is not None:
        with pytest.raises(ProviderToolStale):
            await old_handler({})
        assert old.calls == []

    monkeypatch.undo()
    recovered_status = await supervisor.reconnect("research-main")
    assert recovered_status.state is ProviderState.ONLINE
    assert [tool.name for tool in published(catalog, "research-main")] == ["recovered"]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["connect", "reconnect"])
@pytest.mark.parametrize("stage", ["initialize", "list"])
async def test_typed_candidate_sdk_failures_cleanup_destructive_transaction(
    operation: str, stage: str
):
    catalog = NamespacedToolCatalog()
    old = FakeSession((upstream("old"),))
    failure = ProviderSessionFailure("research-main", stage, "SdkFailure")
    candidate = FakeSession(
        (upstream("new"),),
        **({"initialize_error": failure} if stage == "initialize" else {"list_error": failure}),
    )
    recovered = FakeSession((upstream("recovered"),))
    connector = QueueConnector(
        *((old, candidate, recovered) if operation == "reconnect" else (candidate, recovered))
    )
    supervisor = ProviderSupervisor([research_config()], catalog, lambda _c: connector)
    if operation == "reconnect":
        await supervisor.connect("research-main")

    result = await getattr(supervisor, operation)("research-main")

    runtime = supervisor._runtimes["research-main"]
    assert result.state is ProviderState.OFFLINE
    assert candidate.closed == 1
    assert old.closed == (1 if operation == "reconnect" else 0)
    assert runtime.session is None and runtime.usable is False
    assert published(catalog, "research-main") == ()
    assert (await supervisor.reconnect("research-main")).state is ProviderState.ONLINE


@pytest.mark.asyncio
async def test_successful_refresh_commits_only_after_registration_returns(monkeypatch):
    catalog = NamespacedToolCatalog()
    session = FakeSession((upstream("lookup", marker="v1"),))
    supervisor = ProviderSupervisor(
        [research_config()], catalog, lambda _c: QueueConnector(session)
    )
    await supervisor.connect("research-main")
    runtime = supervisor._runtimes["research-main"]
    prior_generation = runtime.publication_generation
    prior_selected = runtime.selected
    session.tools = (upstream("lookup", marker="v2"),)
    original = catalog.register_provider
    observed = []

    def observe(provider_id, namespace, tools):
        materialized = tuple(tools)
        result = original(provider_id, namespace, materialized)
        observed.append(
            (runtime.session, runtime.usable, runtime.selected, runtime.publication_generation)
        )
        return result

    monkeypatch.setattr(catalog, "register_provider", observe)

    result = await supervisor.refresh("research-main")

    assert observed == [(session, True, prior_selected, prior_generation)]
    assert result.state is ProviderState.ONLINE
    assert runtime.session is session and runtime.usable is True
    assert runtime.publication_generation == prior_generation + 1
    assert runtime.selected[0].input_schema["marker"] == "v2"


@pytest.mark.asyncio
async def test_ordinary_refresh_failure_propagates_without_poisoning_session():
    catalog = NamespacedToolCatalog()
    primary = ValueError("conversion-programming-error")
    session = FakeSession((upstream("lookup"),), list_error=primary)
    supervisor = ProviderSupervisor(
        [research_config()], catalog, lambda _c: QueueConnector(session)
    )
    session.list_error = None
    await supervisor.connect("research-main")
    session.list_error = primary

    with pytest.raises(ValueError) as raised:
        await supervisor.refresh("research-main")

    assert raised.value is primary
    assert session.closed == 0
    assert status(catalog, "research-main").state is ProviderState.ONLINE
    session.list_error = None
    assert await supervisor.invoke("research.lookup", {}) == {"ok": True}
