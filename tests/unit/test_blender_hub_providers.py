from __future__ import annotations

import asyncio
import inspect
import math
import os
import traceback
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.blender_hub.providers as providers
from mcp.client import stdio as mcp_stdio
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

from app.blender_hub.providers import (
    HttpProviderConfig,
    ProviderKind,
    StdioProviderConfig,
    UpstreamTool,
    build_stdio_environment,
    validate_provider_configs,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8080/mcp",
        "https://LOCALHOST:443/mcp",
        "http://[::1]:9000/mcp",
    ],
)
def test_http_config_accepts_only_explicit_loopback_endpoints(url: str):
    config = HttpProviderConfig("local", "tools", ProviderKind.RESEARCH, url)

    assert config.url == url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.2:8080/mcp",
        "http://localhost.evil:8080/mcp",
        "http://127.0.0.1.evil:8080/mcp",
        "http://2130706433:8080/mcp",
        "http://0177.0.0.1:8080/mcp",
        "http://127.0.0.1/mcp",
        "http://127.0.0.1:0/mcp",
        "http://127.0.0.1:65536/mcp",
        "http://user@127.0.0.1:8080/mcp",
        "http://127.0.0.1:8080/mcp?token=x",
        "http://127.0.0.1:8080/mcp#fragment",
        "ftp://127.0.0.1:21/mcp",
        "//127.0.0.1:8080/mcp",
        "127.0.0.1:8080/mcp",
        "http://%31%32%37.0.0.1:8080/mcp",
        "http://localh\N{LATIN SMALL LETTER O WITH DIAERESIS}st:8080/mcp",
        "http://[::ffff:127.0.0.1]:8080/mcp",
        " http://localhost:8080/mcp",
        "http://local\nhost:8080/mcp",
        "http://localhost:8080/mcp\t",
    ],
)
def test_http_config_rejects_noncanonical_or_deceptive_urls(url: str):
    with pytest.raises(ValueError):
        HttpProviderConfig("local", "tools", ProviderKind.RESEARCH, url)


@pytest.mark.parametrize(
    ("provider_id", "namespace"),
    [
        ("", "valid"),
        ("-bad", "valid"),
        ("bad.dot", "valid"),
        ("x" * 65, "valid"),
        ("valid", ""),
        ("valid", "_bad"),
        ("valid", "bad.dot"),
        ("valid", "na\N{LATIN SMALL LETTER I WITH DIAERESIS}ve"),
        ("valid", "x" * 65),
    ],
)
def test_provider_identifiers_are_bounded_ascii_tokens(
    provider_id: str, namespace: str
):
    with pytest.raises(ValueError):
        HttpProviderConfig(
            provider_id,
            namespace,
            ProviderKind.RESEARCH,
            "http://localhost:8000/mcp",
        )


def test_provider_identifier_boundaries_are_accepted():
    config = HttpProviderConfig(
        "a" + "-" * 63,
        "Z" + "_" * 63,
        ProviderKind.DCC_GATEWAY,
        "http://localhost:1",
    )

    assert config.kind is ProviderKind.DCC_GATEWAY


@pytest.mark.parametrize("timeout", [0, -1, math.nan, math.inf, -math.inf])
def test_read_timeout_must_be_positive_and_finite(timeout: float):
    with pytest.raises(ValueError):
        HttpProviderConfig(
            "local",
            "tools",
            ProviderKind.RESEARCH,
            "http://localhost:8000/mcp",
            timeout,
        )


def test_stdio_config_validates_and_snapshots_operator_values():
    overrides = {"LANG": "C.UTF-8"}
    config = StdioProviderConfig(
        "orca-local",
        "orca",
        ProviderKind.ORCA,
        ("orca-mcp", "--stdio"),
        Path("/opt/orca"),
        overrides,
        2.5,
    )
    overrides["SECRET"] = "changed"

    assert config.argv == ("orca-mcp", "--stdio")
    assert config.cwd == Path("/opt/orca")
    assert dict(config.env) == {"LANG": "C.UTF-8"}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"argv": ()},
        {"argv": ("",)},
        {"argv": ("x" * 4097,)},
        {"argv": tuple("x" for _ in range(65))},
        {"argv": ["not-a-tuple"]},
        {"argv": (1,)},
        {"argv": ("cmd",), "cwd": "/tmp"},
        {"argv": ("cmd",), "env": {"BAD-KEY": "x"}},
        {"argv": ("cmd",), "env": {"9BAD": "x"}},
        {"argv": ("cmd",), "env": {"X" * 65: "x"}},
        {"argv": ("cmd",), "env": {"OK": 1}},
        {"argv": ("cmd",), "env": {"OK": "x" * 4097}},
        {"argv": ("cmd",), "env": {f"K{i}": "x" for i in range(129)}},
    ],
)
def test_stdio_config_rejects_invalid_process_contract(kwargs: dict[str, object]):
    with pytest.raises((TypeError, ValueError)):
        StdioProviderConfig(
            "local", "tools", ProviderKind.THREE_MF, **kwargs  # type: ignore[arg-type]
        )


def test_stdio_environment_uses_only_baseline_keys_then_overrides():
    config = StdioProviderConfig(
        "local",
        "tools",
        ProviderKind.THREE_MF,
        ("provider",),
        env={"PATH": "operator-path", "CUSTOM": "yes", "Path": "case-sensitive"},
    )

    merged = build_stdio_environment(
        config,
        {
            "PATH": "ambient-path",
            "PATHEXT": ".EXE",
            "SYSTEMROOT": "C:\\Windows",
            "SECRET_TOKEN": "must-not-leak",
        },
    )

    assert merged == {
        "PATH": "operator-path",
        "PATHEXT": ".EXE",
        "SYSTEMROOT": "C:\\Windows",
        "CUSTOM": "yes",
        "Path": "case-sensitive",
    }


def test_stdio_environment_rejects_merged_utf8_data_over_16_kib():
    config = StdioProviderConfig(
        "local",
        "tools",
        ProviderKind.THREE_MF,
        ("provider",),
        env={f"K{i}": "\N{EURO SIGN}" * 110 for i in range(50)},
    )

    with pytest.raises(ValueError):
        build_stdio_environment(config, {"PATH": "x"})


def test_duplicate_provider_ids_and_namespaces_are_rejected_atomically():
    first = HttpProviderConfig(
        "one", "shared", ProviderKind.RESEARCH, "http://localhost:8001"
    )
    duplicate_id = HttpProviderConfig(
        "one", "other", ProviderKind.ORCA, "http://localhost:8002"
    )
    duplicate_namespace = HttpProviderConfig(
        "two", "shared", ProviderKind.ORCA, "http://localhost:8003"
    )

    with pytest.raises(ValueError, match="provider_id"):
        validate_provider_configs([first, duplicate_id])
    with pytest.raises(ValueError, match="namespace"):
        validate_provider_configs([first, duplicate_namespace])
    assert validate_provider_configs(iter([first])) == (first,)


def test_config_validation_has_no_network_or_subprocess_side_effect(monkeypatch):
    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("configuration validation attempted an external side effect")

    monkeypatch.setattr("socket.create_connection", forbidden)
    monkeypatch.setattr("subprocess.Popen", forbidden)

    http = HttpProviderConfig(
        "http-local", "http", ProviderKind.RESEARCH, "http://localhost:8080/mcp"
    )
    stdio = StdioProviderConfig(
        "stdio-local", "stdio", ProviderKind.ORCA, ("provider", "--stdio")
    )

    assert validate_provider_configs([http, stdio]) == (http, stdio)


def test_upstream_tool_is_a_deep_immutable_json_snapshot():
    input_schema = {"type": "object", "properties": {"count": {"type": "integer"}}}
    annotations = {"readOnlyHint": True}
    publication = {"icons": [{"src": "icon.png"}], "_meta": {"group": "mesh"}}
    tool = UpstreamTool(
        "inspect",
        "Inspect",
        "Inspect a mesh",
        input_schema,
        None,
        annotations,
        publication,
    )
    input_schema["properties"]["count"]["type"] = "string"
    publication["icons"][0]["src"] = "changed.png"

    assert tool.input_schema["properties"]["count"]["type"] == "integer"
    assert tool.publication_metadata["icons"][0]["src"] == "icon.png"
    with pytest.raises(TypeError):
        tool.annotations["readOnlyHint"] = False
    with pytest.raises(TypeError):
        tool.publication_metadata["icons"][0]["src"] = "other.png"


@pytest.mark.parametrize(
    "schema",
    [
        {"value": object()},
        {"value": math.nan},
        {1: "non-string key"},
    ],
)
def test_upstream_tool_rejects_json_invalid_evidence(schema: dict[object, object]):
    with pytest.raises((TypeError, ValueError)):
        UpstreamTool("bad", None, None, schema, None, {}, {})  # type: ignore[arg-type]


class _AsyncContext:
    def __init__(self, value: object, events: list[str], label: str):
        self.value = value
        self.events = events
        self.label = label

    async def __aenter__(self):
        self.events.append(f"enter:{self.label}")
        return self.value

    async def __aexit__(self, *_args: object):
        self.events.append(f"exit:{self.label}")


@pytest.mark.asyncio
async def test_http_connector_owns_explicit_client_and_stages_session(monkeypatch):
    events: list[str] = []
    captured: dict[str, object] = {}

    class FakeHttpClient(_AsyncContext):
        def __init__(self, **kwargs: object):
            captured.update(kwargs)
            super().__init__(self, events, "http")

    sdk = SimpleNamespace()

    def fake_transport(url: str, *, http_client: object):
        captured["url"] = url
        captured["transport_client"] = http_client
        return _AsyncContext(("read", "write"), events, "transport")

    def fake_session(read: object, write: object):
        captured["streams"] = (read, write)
        return _AsyncContext(sdk, events, "session")

    monkeypatch.setattr(providers.httpx2, "AsyncClient", FakeHttpClient)
    monkeypatch.setattr(providers, "streamable_http_client", fake_transport)
    monkeypatch.setattr(providers, "ClientSession", fake_session)
    config = HttpProviderConfig(
        "http-local", "http", ProviderKind.RESEARCH,
        "http://localhost:8080/mcp", 7.5,
    )

    session = await providers.StreamableHttpProvider().connect(config)

    assert events == ["enter:http", "enter:transport", "enter:session"]
    assert captured["follow_redirects"] is False
    assert captured["trust_env"] is False
    timeout = captured["timeout"]
    assert (timeout.connect, timeout.read, timeout.write, timeout.pool) == (30, 300, 30, 30)
    assert captured["url"] == config.url
    assert isinstance(captured["transport_client"], FakeHttpClient)
    assert captured["streams"] == ("read", "write")
    assert events == ["enter:http", "enter:transport", "enter:session"]
    await session.close()
    await session.close()
    assert events[-3:] == ["exit:session", "exit:transport", "exit:http"]


@pytest.mark.asyncio
async def test_http_partial_entry_failure_is_sanitized_and_cleaned_once(monkeypatch):
    events: list[str] = []

    class EntryFailure(_AsyncContext):
        async def __aenter__(self):
            raise RuntimeError("PRIMARY_HTTP_SECRET")

    monkeypatch.setattr(
        providers.httpx2, "AsyncClient",
        lambda **_kwargs: _AsyncContext(object(), events, "http"),
    )
    monkeypatch.setattr(
        providers, "streamable_http_client",
        lambda *_args, **_kwargs: EntryFailure(None, events, "transport"),
    )
    config = HttpProviderConfig(
        "http-local", "http", ProviderKind.RESEARCH, "http://localhost:8080/mcp"
    )

    with pytest.raises(providers.ProviderConnectionError) as caught:
        await providers.StreamableHttpProvider().connect(config)

    error = caught.value
    assert (error.provider_id, error.phase, error.exception_type) == (
        "http-local", "connect", "RuntimeError"
    )
    assert error.__cause__ is None and error.__context__ is None
    assert "PRIMARY_HTTP_SECRET" not in repr(error)
    assert events == ["enter:http", "exit:http"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stage", "expected_events"),
    [
        ("client", []),
        ("transport", ["enter:client", "exit:client"]),
        (
            "session",
            ["enter:client", "enter:transport", "exit:transport", "exit:client"],
        ),
    ],
)
async def test_every_http_context_entry_failure_cleans_partial_stack_once(
    monkeypatch, stage: str, expected_events: list[str]
):
    events: list[str] = []

    class ConditionalContext(_AsyncContext):
        async def __aenter__(self):
            if self.label == stage:
                raise OSError("ENTRY_SECRET")
            return await super().__aenter__()

    monkeypatch.setattr(
        providers.httpx2,
        "AsyncClient",
        lambda **_kwargs: ConditionalContext(object(), events, "client"),
    )
    monkeypatch.setattr(
        providers,
        "streamable_http_client",
        lambda *_args, **_kwargs: ConditionalContext(
            ("read", "write"), events, "transport"
        ),
    )
    monkeypatch.setattr(
        providers,
        "ClientSession",
        lambda *_args: ConditionalContext(object(), events, "session"),
    )
    config = HttpProviderConfig(
        "partial", "partial", ProviderKind.RESEARCH, "http://localhost:8081/mcp"
    )

    with pytest.raises(providers.ProviderConnectionError) as caught:
        await providers.StreamableHttpProvider().connect(config)

    assert caught.value.exception_type == "OSError"
    assert "ENTRY_SECRET" not in repr(caught.value)
    assert events == expected_events


@pytest.mark.asyncio
async def test_stdio_connector_uses_public_sdk_and_exact_hub_fragment(monkeypatch):
    events: list[str] = []
    captured: dict[str, object] = {}
    sdk = SimpleNamespace()

    def fake_stdio(parameters: object):
        captured["parameters"] = parameters
        return _AsyncContext(("read", "write"), events, "stdio")

    def fake_session(read: object, write: object):
        captured["streams"] = (read, write)
        return _AsyncContext(sdk, events, "session")

    monkeypatch.setattr(providers, "stdio_client", fake_stdio)
    monkeypatch.setattr(providers, "ClientSession", fake_session)
    monkeypatch.setattr(
        providers.os, "environ", {"PATH": "ambient", "SECRET_SENTINEL": "hidden"}
    )
    config = StdioProviderConfig(
        "stdio-local", "stdio", ProviderKind.ORCA,
        ("provider", "--stdio"), Path("/opt/provider"),
        {"PATH": "hub-path", "CUSTOM": "yes"}, 4.0,
    )

    session = await providers.StdioProvider().connect(config)

    parameters = captured["parameters"]
    assert parameters.command == "provider"
    assert parameters.args == ["--stdio"]
    assert parameters.cwd == Path("/opt/provider")
    assert parameters.env == {"PATH": "hub-path", "CUSTOM": "yes"}
    assert "SECRET_SENTINEL" not in parameters.env
    assert captured["streams"] == ("read", "write")
    await session.close()
    assert events == ["enter:stdio", "enter:session", "exit:session", "exit:stdio"]


def test_pinned_stdio_sdk_environment_contract(monkeypatch):
    assert version("mcp") == "2.0.0"
    assert mcp_stdio.DEFAULT_INHERITED_ENV_VARS == [
        "HOME", "LOGNAME", "PATH", "SHELL", "TERM", "USER"
    ]
    ambient = {
        "HOME": "/safe", "PATH": "ambient-path", "SHELL": "() shell-function",
        "SECRET_SENTINEL": "must-not-leak",
    }
    monkeypatch.setattr(os, "environ", ambient)

    defaults = mcp_stdio.get_default_environment()
    hub = {"PATH": "hub-path", "CUSTOM": "yes"}
    child = defaults | hub

    assert defaults == {"HOME": "/safe", "PATH": "ambient-path"}
    assert child == {"HOME": "/safe", "PATH": "hub-path", "CUSTOM": "yes"}
    assert "SECRET_SENTINEL" not in child
    source = inspect.getsource(mcp_stdio.stdio_client)
    assert "get_default_environment() | (server.env or {})" in source


async def _connected_fake_http_session(monkeypatch, sdk: object, timeout: float = 6.0):
    events: list[str] = []
    monkeypatch.setattr(
        providers.httpx2, "AsyncClient",
        lambda **_kwargs: _AsyncContext(object(), events, "http"),
    )
    monkeypatch.setattr(
        providers, "streamable_http_client",
        lambda *_args, **_kwargs: _AsyncContext(("read", "write"), events, "transport"),
    )
    monkeypatch.setattr(
        providers, "ClientSession",
        lambda *_args: _AsyncContext(sdk, events, "session"),
    )
    config = HttpProviderConfig(
        "typed", "typed", ProviderKind.RESEARCH, "http://localhost:8123/mcp", timeout
    )
    return await providers.StreamableHttpProvider().connect(config)


@pytest.mark.asyncio
async def test_mcp_models_convert_with_json_aliases_and_call_timeout(monkeypatch):
    calls: list[object] = []
    tool = Tool(
        name="inspect", title="Inspect", description="Inspect mesh",
        inputSchema={"type": "object", "properties": {"n": {"type": "integer"}}},
        outputSchema={"type": "object"},
        annotations=ToolAnnotations(readOnlyHint=True),
        icons=[{"src": "icon.png"}],
        execution={"taskSupport": "optional"},
        _meta={"group": "mesh"},
    )
    result = CallToolResult(
        content=[TextContent(text="failed")], structuredContent={"ok": False},
        isError=True, resultType="input_required", _meta={"trace": 1},
    )

    class Sdk:
        async def initialize(self):
            calls.append("initialize")

        async def list_tools(self):
            calls.append("list")
            return SimpleNamespace(tools=[tool])

        async def call_tool(self, name, arguments, read_timeout_seconds=None):
            calls.append((name, arguments, read_timeout_seconds))
            return result

    session = await _connected_fake_http_session(monkeypatch, Sdk())
    await session.initialize()
    converted = (await session.list_tools())[0]
    arguments: dict[str, object] = {}
    converted_result = await session.call_tool("inspect", arguments)

    assert calls == ["initialize", "list", ("inspect", arguments, 6.0)]
    assert converted.name == "inspect" and converted.title == "Inspect"
    assert converted.input_schema["properties"]["n"]["type"] == "integer"
    assert dict(converted.annotations) == {"readOnlyHint": True}
    assert converted.publication_metadata == {
        "execution": {"taskSupport": "optional"},
        "icons": ({"src": "icon.png"},), "_meta": {"group": "mesh"},
    }
    assert converted_result == result.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["initialize", "list_tools", "call_tool"])
async def test_only_sdk_await_failures_are_sanitized(monkeypatch, method: str):
    class Sdk:
        async def initialize(self):
            if method == "initialize":
                raise RuntimeError("SDK_SECRET")

        async def list_tools(self):
            if method == "list_tools":
                raise LookupError("SDK_SECRET")
            return SimpleNamespace(tools=[])

        async def call_tool(self, *_args, **_kwargs):
            if method == "call_tool":
                raise ValueError("SDK_SECRET")
            return CallToolResult(content=[])

    session = await _connected_fake_http_session(monkeypatch, Sdk())
    operation = getattr(session, method)
    with pytest.raises(providers.ProviderSessionFailure) as caught:
        await (operation("tool", {}) if method == "call_tool" else operation())
    error = caught.value
    assert error.provider_id == "typed"
    assert error.phase == {"initialize": "initialize", "list_tools": "list", "call_tool": "call"}[method]
    assert "SDK_SECRET" not in repr(error)
    assert error.__cause__ is None and error.__context__ is None


@pytest.mark.asyncio
async def test_conversion_error_remains_original_and_session_usable(monkeypatch):
    class BadTool:
        name = "bad"
        title = description = outputSchema = annotations = execution = icons = None
        inputSchema = {"bad": object()}
        _meta = None

        def model_dump(self, **_kwargs):
            raise AssertionError("conversion bug")

    class Sdk:
        count = 0

        async def initialize(self): pass
        async def list_tools(self):
            self.count += 1
            return SimpleNamespace(tools=[BadTool()] if self.count == 1 else [])
        async def call_tool(self, *_args, **_kwargs):
            return CallToolResult(content=[])

    session = await _connected_fake_http_session(monkeypatch, Sdk())
    with pytest.raises(AssertionError, match="conversion bug"):
        await session.list_tools()
    assert await session.list_tools() == ()


@pytest.mark.asyncio
async def test_call_result_conversion_error_is_not_a_session_failure(monkeypatch):
    class BadResult:
        def model_dump(self, **_kwargs):
            raise TypeError("result conversion bug")

    class Sdk:
        count = 0

        async def initialize(self): pass
        async def list_tools(self): return SimpleNamespace(tools=[])
        async def call_tool(self, *_args, **_kwargs):
            self.count += 1
            return BadResult() if self.count == 1 else CallToolResult(content=[])

    session = await _connected_fake_http_session(monkeypatch, Sdk())
    with pytest.raises(TypeError, match="result conversion bug") as caught:
        await session.call_tool("tool", {})
    assert not isinstance(caught.value, providers.ProviderSessionFailure)
    assert (await session.call_tool("tool", {}))["isError"] is False


def _exception_graph_text(error: BaseException) -> str:
    pending = [error]
    seen: set[int] = set()
    pieces: list[str] = []
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        pieces.extend((str(current), repr(current)))
        for linked in (current.__cause__, current.__context__):
            if linked is not None:
                pending.append(linked)
        pending.extend(getattr(current, "exceptions", ()))
    return "\n".join(pieces)


@pytest.mark.asyncio
async def test_primary_entry_failure_wins_and_drops_cleanup_exception_group(monkeypatch):
    events: list[str] = []

    class FailingExit(_AsyncContext):
        async def __aexit__(self, *_args: object):
            events.append("exit:http")
            raise ExceptionGroup(
                "CLEANUP_GROUP_SECRET", [RuntimeError("CLEANUP_INNER_SECRET")]
            )

    class FailingTransport(_AsyncContext):
        async def __aenter__(self):
            raise LookupError("PRIMARY_ENTRY_SECRET")

    monkeypatch.setattr(
        providers.httpx2, "AsyncClient",
        lambda **_kwargs: FailingExit(object(), events, "http"),
    )
    monkeypatch.setattr(
        providers, "streamable_http_client",
        lambda *_args, **_kwargs: FailingTransport(None, events, "transport"),
    )
    config = HttpProviderConfig(
        "safe", "safe", ProviderKind.RESEARCH, "http://localhost:8124/mcp"
    )

    with pytest.raises(providers.ProviderConnectionError) as caught:
        await providers.StreamableHttpProvider().connect(config)

    error = caught.value
    rendered = "".join(traceback.format_exception(error)) + _exception_graph_text(error)
    assert error.exception_type == "LookupError"
    assert error.__cause__ is None and error.__context__ is None
    assert all(secret not in rendered for secret in (
        "PRIMARY_ENTRY_SECRET", "CLEANUP_GROUP_SECRET", "CLEANUP_INNER_SECRET"
    ))
    assert events == ["enter:http", "exit:http"]


@pytest.mark.asyncio
async def test_close_failure_is_sanitized_and_close_remains_idempotent(monkeypatch):
    events: list[str] = []

    class FailingExit(_AsyncContext):
        async def __aexit__(self, *_args: object):
            events.append(f"exit:{self.label}")
            if self.label == "http":
                raise RuntimeError("CLOSE_SECRET")

    monkeypatch.setattr(
        providers.httpx2, "AsyncClient",
        lambda **_kwargs: FailingExit(object(), events, "http"),
    )
    monkeypatch.setattr(
        providers, "streamable_http_client",
        lambda *_args, **_kwargs: _AsyncContext(("r", "w"), events, "transport"),
    )
    monkeypatch.setattr(
        providers, "ClientSession",
        lambda *_args: _AsyncContext(SimpleNamespace(), events, "session"),
    )
    config = HttpProviderConfig(
        "safe", "safe", ProviderKind.RESEARCH, "http://localhost:8124/mcp"
    )
    session = await providers.StreamableHttpProvider().connect(config)

    with pytest.raises(providers.ProviderSessionFailure) as caught:
        await session.close()
    assert (caught.value.phase, caught.value.exception_type) == ("close", "RuntimeError")
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert "CLOSE_SECRET" not in "".join(traceback.format_exception(caught.value))
    await session.close()
    assert events.count("exit:http") == 1


@pytest.mark.asyncio
async def test_cleanup_and_sdk_cancellation_are_not_converted(monkeypatch):
    class CancelExit(_AsyncContext):
        async def __aexit__(self, *_args: object):
            raise asyncio.CancelledError

    class CancelSdk:
        async def initialize(self):
            raise asyncio.CancelledError

    events: list[str] = []
    monkeypatch.setattr(
        providers.httpx2, "AsyncClient",
        lambda **_kwargs: CancelExit(object(), events, "http"),
    )
    monkeypatch.setattr(
        providers, "streamable_http_client",
        lambda *_args, **_kwargs: _AsyncContext(("r", "w"), events, "transport"),
    )
    monkeypatch.setattr(
        providers, "ClientSession",
        lambda *_args: _AsyncContext(CancelSdk(), events, "session"),
    )
    config = HttpProviderConfig(
        "cancel", "cancel", ProviderKind.RESEARCH, "http://localhost:8125/mcp"
    )
    session = await providers.StreamableHttpProvider().connect(config)
    with pytest.raises(asyncio.CancelledError):
        await session.initialize()
    with pytest.raises(asyncio.CancelledError):
        await session.close()
