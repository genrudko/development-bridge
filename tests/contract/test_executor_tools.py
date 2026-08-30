from app.container import build_container
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry


def test_executor_tools_have_exact_closed_schemas():
    registry = build_tool_registry(build_container(BridgeSettings()))
    status = registry.get("executor_status").definition.input_schema
    start = registry.get("executor_start").definition.input_schema
    assert status["required"] == ["project_id", "repository_id"]
    assert status["additionalProperties"] is False
    assert start["required"] == ["project_id", "repository_id", "task", "task_kind"]
    assert start["additionalProperties"] is False
    props = start["properties"]
    assert props["task"]["maxLength"] == 65536
    assert props["task_kind"]["enum"] == ["implementation", "review", "other"]
    assert props["executor"]["enum"] == ["codex", "antigravity"]
    assert props["timeout_seconds"]["exclusiveMinimum"] == 0 and props["timeout_seconds"]["maximum"] == 3600
    assert props["output_limit_bytes"]["minimum"] == 1024 and props["output_limit_bytes"]["maximum"] == 1048576
