from app.container import build_container
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry


SUPPORTED_TOOLS = {
    "bridge_info",
    "project_list",
    "project_describe",
    "repository_status",
    "repository_clone",
    "file_list",
    "file_read",
    "file_search",
    "git_log",
    "git_show",
    "git_diff",
    "git_refs",
    "git_stage",
    "git_commit",
    "git_push_plan",
    "git_push",
    "git_fetch",
    "git_branch_create",
    "git_branch_switch",
    "git_fast_forward",
    "change_plan",
    "change_apply",
    "task_list",
    "task_start",
    "job_status",
    "job_output",
    "job_cancel",
    "job_artifact_list",
    "job_artifact_view",
    "knowledge_source_list",
    "knowledge_search",
    "knowledge_message",
    "knowledge_thread",
    "knowledge_source_add",
    "knowledge_source_sync",
    "knowledge_attachment_open",
    "knowledge_attachment_export",
}


def test_registered_tool_surface_is_exact():
    registry = build_tool_registry(build_container(BridgeSettings()))

    assert {tool.name for tool in registry.definitions} == SUPPORTED_TOOLS
    assert len(registry.definitions) == 37
    assert {registry.get(name).source for name in SUPPORTED_TOOLS} == {"v1", "community-knowledge"}


def test_legacy_global_workspace_names_are_absent():
    registry = build_tool_registry(build_container(BridgeSettings()))

    assert {
        "workspace_status",
        "read_file",
        "apply_patch",
        "git_status",
        "git_branch",
        "search_workspace",
        "github_status",
    }.isdisjoint(tool.name for tool in registry.definitions)
