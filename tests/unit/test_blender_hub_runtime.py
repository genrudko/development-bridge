import json
from pathlib import Path

import pytest

from app.blender_bridge.models import ToolSpec
from app.blender_bridge.provider_transport import ProviderHealth
from agents.blender_hub_runtime import (
    ProviderConfig,
    load_provider_configs,
    public_tool_metadata,
    tool_spec_from_mcp_dump,
)


def test_tool_metadata_classification_is_fail_closed_for_unknown_tools():
    raw = {
        "name": "create_object",
        "description": "Create object",
        "inputSchema": {"type": "object", "properties": {}},
    }

    spec = tool_spec_from_mcp_dump(raw)

    assert spec.name == "create_object"
    assert spec.mutating is None
    assert spec.idempotent is False


def test_standard_mcp_annotations_preserve_read_only_and_idempotent_hints():
    raw = {
        "name": "list_objects",
        "description": "List objects",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True, "idempotentHint": True},
    }

    spec = tool_spec_from_mcp_dump(raw)

    assert spec.mutating is False
    assert spec.idempotent is True


def test_dcc_style_metadata_is_also_understood():
    raw = {
        "name": "get_scene_info",
        "description": "Scene info",
        "inputSchema": {"type": "object", "properties": {}},
        "read_only": True,
        "idempotent": True,
    }

    spec = tool_spec_from_mcp_dump(raw)

    assert spec.mutating is False
    assert spec.idempotent is True


def test_public_tool_metadata_adds_namespace_without_losing_schema():
    raw = {
        "name": "list_objects",
        "description": "List objects",
        "inputSchema": {"type": "object", "properties": {"type": {"type": "string"}}},
        "annotations": {"readOnlyHint": True},
    }

    public = public_tool_metadata("dcc", raw)

    assert public["name"] == "dcc.list_objects"
    assert public["inputSchema"] == raw["inputSchema"]
    assert public["description"].startswith("[dcc]")
    assert public["x_blender_hub"]["provider"] == "dcc"
    assert public["x_blender_hub"]["mutating"] is False


def test_provider_config_loader_preserves_pins_and_rejects_duplicate_namespaces(tmp_path: Path):
    path = tmp_path / "providers.json"
    path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "namespace": "dcc",
                        "url": "http://127.0.0.1:9765/mcp",
                        "pin": "v0.2.4",
                    },
                    {
                        "namespace": "research",
                        "url": "http://127.0.0.1:9877/mcp",
                        "pin": "0.17.5",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    configs = load_provider_configs(path)

    assert configs == (
        ProviderConfig("dcc", "http://127.0.0.1:9765/mcp", "v0.2.4", True),
        ProviderConfig("research", "http://127.0.0.1:9877/mcp", "0.17.5", True),
    )

    path.write_text(
        json.dumps(
            {
                "providers": [
                    {"namespace": "dcc", "url": "http://127.0.0.1:1/mcp"},
                    {"namespace": "dcc", "url": "http://127.0.0.1:2/mcp"},
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate provider namespace"):
        load_provider_configs(path)


class FakeRuntimeTransport:
    def __init__(self, config, *, fail_connect=False):
        self.config = config
        self.fail_connect = fail_connect
        self.connected = False

    async def connect(self):
        if self.fail_connect:
            raise ConnectionError(f"{self.config.namespace} unavailable")
        self.connected = True

    async def close(self):
        self.connected = False

    async def reconnect(self):
        await self.connect()

    async def list_tools(self):
        return [
            ToolSpec(name="read_scene", description="", mutating=False, idempotent=True)
        ]

    def advertised_tools(self):
        return [
            {
                "name": f"{self.config.namespace}.read_scene",
                "description": "read",
                "inputSchema": {"type": "object", "properties": {}},
                "x_blender_hub": {
                    "provider": self.config.namespace,
                    "upstream_tool": "read_scene",
                    "mutating": False,
                    "idempotent": True,
                },
            }
        ]

    async def call_tool(self, name, arguments):
        return {"ok": True}

    async def health(self):
        return ProviderHealth(
            state="online" if self.connected else "offline", pin=self.config.pin
        )


@pytest.mark.asyncio
async def test_one_failed_provider_does_not_take_down_connected_provider():
    from agents.blender_hub_runtime import BlenderHubRuntime

    configs = (
        ProviderConfig("dcc", "http://127.0.0.1:9765/mcp", "v0.2.4"),
        ProviderConfig("research", "http://127.0.0.1:9877/mcp", "0.17.5"),
    )

    def factory(config):
        return FakeRuntimeTransport(config, fail_connect=config.namespace == "research")

    runtime = BlenderHubRuntime(configs, transport_factory=factory)
    await runtime.connect()
    try:
        advertised = {tool["name"] for tool in runtime.advertised_tools()}
        assert "dcc.read_scene" in advertised
        assert "research.read_scene" not in advertised
        status = {item["namespace"]: item for item in runtime.provider_status()}
        assert status["dcc"]["connected"] is True
        assert status["research"]["connected"] is False
        assert "unavailable" in status["research"]["error"]
    finally:
        await runtime.close()


def test_destructive_hint_wins_over_conflicting_read_only_hint():
    raw = {
        "name": "conflicting_tool",
        "annotations": {"readOnlyHint": True, "destructiveHint": True},
    }
    spec = tool_spec_from_mcp_dump(raw)
    assert spec.mutating is True
