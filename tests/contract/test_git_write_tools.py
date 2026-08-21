from app.container import build_container
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry


def tools():
    registry = build_tool_registry(build_container(BridgeSettings()))
    return registry, {tool.name: tool for tool in registry.definitions}


def test_git_write_tool_surface_replaces_legacy_names():
    registry, definitions = tools()
    assert {"git_stage", "git_commit", "git_push_plan", "git_push"} <= definitions.keys()
    for name in ("git_stage", "git_commit", "git_push_plan", "git_push"):
        assert registry.get(name).source == "v1"


def test_stage_and_commit_guards_are_optional():
    _, definitions = tools()
    stage = definitions["git_stage"].input_schema
    commit = definitions["git_commit"].input_schema
    assert stage["additionalProperties"] is False
    assert stage["required"] == ["project_id", "repository_id", "paths"]
    assert commit["required"] == [
        "project_id",
        "repository_id",
        "message",
        "idempotency_key",
    ]
    assert "expected_head" in commit["properties"]
    assert "expected_index_revision" in commit["properties"]


def test_push_requires_a_self_contained_plan_snapshot():
    _, definitions = tools()
    push = definitions["git_push"].input_schema
    assert push["additionalProperties"] is False
    assert set(push["required"]) == {
        "project_id",
        "repository_id",
        "plan_id",
        "local_branch",
        "local_head",
        "remote",
        "remote_branch",
        "remote_head",
        "set_upstream",
        "idempotency_key",
    }
    assert "command" not in push["properties"]
    assert "arguments" not in push["properties"]
