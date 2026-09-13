from __future__ import annotations

import math
from pathlib import Path

import pytest

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
