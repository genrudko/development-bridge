from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

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


class QueueConnector:
    def __init__(self, *outcomes: FakeSession | BaseException):
        self.outcomes = list(outcomes)
        self.configs: list[object] = []

    async def connect(self, config: object) -> FakeSession:
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
    tools = [upstream(name, marker=f"dcc-{name}") for name in names if name != missing]
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
    assert fresh["search"].input_schema == old["search"].input_schema
    assert fresh["search"].metadata == old["search"].metadata
    with pytest.raises(ProviderToolStale):
        await old["search"].handler({})
    with pytest.raises(ProviderSessionUnavailable):
        await fresh["search"].handler({})


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
