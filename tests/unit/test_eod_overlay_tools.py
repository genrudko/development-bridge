from __future__ import annotations

import json
from types import SimpleNamespace
import pytest

from app.api.errors import BridgeError, ErrorCode
from app.api.registry import RegisteredTool, ToolRegistry
from app.capabilities import Capability, CapabilitySet
from app.projects.models import Repository
from app.tools.compact import compact_tools, exposed_tool_definitions, COMPACT_VISIBLE_TOOLS
from app.tools.eod_overlay import eod_overlay_tools
from app.tools.registry import build_tool_registry


class FakeOverlayService:
    def __init__(self):
        self.applied = []
        self.rolled_back = []

    async def apply(self, repository, paths=None):
        self.applied.append((repository, paths))
        return {
            "run_id": "test-run-123",
            "file_count": 1,
            "total_bytes": 100,
            "applied_files": ["src/templates/index.html"],
            "exit_code": 0,
            "stdout": "ok",
            "stderr": "",
        }

    async def rollback(self, repository):
        self.rolled_back.append(repository)
        return {
            "cleared": True,
            "exit_code": 0,
            "stdout": "cleared",
            "stderr": "",
        }


class FakeRepoRegistry:
    def __init__(self, repositories=None):
        self.repos = repositories or {}

    def get(self, project_id, repository_id):
        if (project_id, repository_id) in self.repos:
            return self.repos[(project_id, repository_id)]
        raise BridgeError(
            ErrorCode.REPOSITORY_NOT_FOUND,
            "Repository is not registered",
            details={"project_id": project_id, "repository_id": repository_id},
        )


def make_container(overlay_service=None, repos=None):
    if repos is None:
        repos = {
            ("eod", "eod"): Repository(
                project_id="eod",
                id="eod",
                root=SimpleNamespace(),
                capabilities=CapabilitySet(frozenset(Capability)),
            )
        }
    return SimpleNamespace(
        settings=SimpleNamespace(
            server=SimpleNamespace(name="development-bridge", tool_surface="full"),
            eod_browser=SimpleNamespace(enabled=False),
        ),
        projects=SimpleNamespace(repositories=FakeRepoRegistry(repos), list=lambda: ()),
        route_registry=SimpleNamespace(resolve=lambda *a, **k: None),
        coordinator=SimpleNamespace(session_binding=lambda *a, **k: None),
        eod_overlay=overlay_service or FakeOverlayService(),
    )


@pytest.mark.asyncio
async def test_apply_tool_schema_has_only_optional_paths():
    container = make_container()
    tools = {t.definition.name: t for t in eod_overlay_tools(container)}
    schema = tools["eod_development_overlay_apply"].definition.input_schema
    assert set(schema["properties"].keys()) == {"paths"}
    assert "project_id" not in schema["properties"]
    assert "repository_id" not in schema["properties"]
    assert schema.get("required") in (None, [])
    assert schema["additionalProperties"] is False


@pytest.mark.asyncio
async def test_rollback_tool_schema_has_empty_properties():
    container = make_container()
    tools = {t.definition.name: t for t in eod_overlay_tools(container)}
    schema = tools["eod_development_overlay_rollback"].definition.input_schema
    assert schema["properties"] == {}
    assert "project_id" not in schema["properties"]
    assert "repository_id" not in schema["properties"]
    assert schema["additionalProperties"] is False


@pytest.mark.asyncio
async def test_apply_tool_invokes_service_with_eod_repo():
    overlay = FakeOverlayService()
    container = make_container(overlay_service=overlay)
    tools = {t.definition.name: t for t in eod_overlay_tools(container)}

    apply_tool = tools["eod_development_overlay_apply"]
    params = SimpleNamespace(arguments={"paths": ["src/templates/index.html"]})
    request_context = SimpleNamespace(request_id="req-1")

    result = await apply_tool.handler(None, params, request_context)
    payload = json.loads(result.content[0].text)

    assert payload["data"]["run_id"] == "test-run-123"
    assert payload["data"]["file_count"] == 1
    assert len(overlay.applied) == 1
    assert overlay.applied[0][0].project_id == "eod"
    assert overlay.applied[0][0].id == "eod"
    assert overlay.applied[0][1] == ["src/templates/index.html"]


@pytest.mark.asyncio
async def test_rollback_tool_invokes_service_with_eod_repo():
    overlay = FakeOverlayService()
    container = make_container(overlay_service=overlay)
    tools = {t.definition.name: t for t in eod_overlay_tools(container)}

    rollback_tool = tools["eod_development_overlay_rollback"]
    params = SimpleNamespace(arguments={})
    request_context = SimpleNamespace(request_id="req-2")

    result = await rollback_tool.handler(None, params, request_context)
    payload = json.loads(result.content[0].text)

    assert payload["data"]["cleared"] is True
    assert len(overlay.rolled_back) == 1
    assert overlay.rolled_back[0].project_id == "eod"
    assert overlay.rolled_back[0].id == "eod"


def test_overlay_tools_are_hidden_from_compact_surface():
    registry = ToolRegistry()
    container = make_container()
    overlay_tools_tuple = eod_overlay_tools(container)
    registry.register_many(overlay_tools_tuple)
    registry.register_many(compact_tools(container, registry))

    visible_names = {t.name for t in exposed_tool_definitions(registry, "compact")}
    assert "eod_development_overlay_apply" not in visible_names
    assert "eod_development_overlay_rollback" not in visible_names
    assert visible_names <= set(COMPACT_VISIBLE_TOOLS)


@pytest.mark.asyncio
async def test_compact_bridge_search_and_schema_and_call_for_overlay():
    registry = ToolRegistry()
    container = make_container()
    overlay_tools_tuple = eod_overlay_tools(container)
    registry.register_many(overlay_tools_tuple)
    compact_tools_tuple = compact_tools(container, registry)
    registry.register_many(compact_tools_tuple)
    compact_dict = {t.definition.name: t for t in compact_tools_tuple}

    request_context = SimpleNamespace(request_id="req-test")

    # 1. bridge_search finds overlay tools
    search_res = await compact_dict["bridge_search"].handler(
        None, SimpleNamespace(arguments={"query": "overlay"}), request_context
    )
    search_text = search_res.content[0].text
    assert "eod_development_overlay_apply" in search_text
    assert "eod_development_overlay_rollback" in search_text

    # 2. bridge_schema returns input_schema
    schema_res = await compact_dict["bridge_schema"].handler(
        None, SimpleNamespace(arguments={"tool_name": "eod_development_overlay_apply"}), request_context
    )
    schema_text = schema_res.content[0].text
    assert "properties" in schema_text

    # 3. bridge_call delegates to hidden overlay tool
    call_res = await compact_dict["bridge_call"].handler(
        None,
        SimpleNamespace(arguments={
            "tool_name": "eod_development_overlay_apply",
            "arguments": {"paths": ["src/templates/index.html"]},
        }),
        request_context,
    )
    assert "test-run-123" in call_res.content[0].text
