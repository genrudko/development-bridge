from app.container import build_container
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry

SUPPORTED_TOOLS = {
    "bridge_info",
    "bridge_guide",
    "bridge_restart",
    "project_list",
    "project_describe",
    "repository_status",
    "repository_clone",
    "repository_retention_set",
    "repository_gc_plan",
    "repository_gc_apply",
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
    "job_artifact_export",
    "repository_exec",
    "github_repository_status",
    "github_repository_fork",
    "github_commit_checks",
    "github_release_list",
    "github_release_get",
    "github_release_plan",
    "github_release_apply",
    "github_issue_list",
    "github_issue_get",
    "github_issue_comments",
    "github_issue_create",
    "github_issue_update",
    "github_issue_comment",
    "github_pull_request_list",
    "github_pull_request_get",
    "github_pull_request_create",
    "github_pull_request_update",
    "github_pull_request_comment",
    "github_pull_request_reviews",
    "github_pull_request_review_comments",
    "github_pull_request_files",
    "github_pull_request_review",
    "github_pull_request_request_reviewers",
    "github_pull_request_merge",
    "github_actions_runs",
    "github_actions_run",
    "github_actions_jobs",
    "github_actions_job_logs",
    "github_actions_artifacts",
    "github_actions_artifact_export",
    "github_actions_dispatch",
    "github_actions_rerun",
    "github_actions_cancel",
    "knowledge_source_list",
    "knowledge_search",
    "knowledge_message",
    "knowledge_thread",
    "knowledge_source_add",
    "knowledge_source_sync",
    "knowledge_attachment_open",
    "knowledge_attachment_export",
    "chatgpt_share_read",
    "coordinator_x_mount",
    "coordinator_route_takeover",
    "coordinator_route_rollover_prepare",
    "coordinator_route_context_get",
    "coordinator_route_context_update",
    "coordinator_continue",
    "coordinator_ack",
    "coordinator_wake_on_jobs",
    "coordinator_exec_and_wake",
    "run_command",
    "telegram_supervisor_status",
    "telegram_send",
    "fusion_node_status",
    "fusion_tools",
    "fusion_call",
}


def test_registered_tool_surface_is_exact():
    registry = build_tool_registry(build_container(BridgeSettings()))

    assert {tool.name for tool in registry.definitions} == SUPPORTED_TOOLS
    assert len(registry.definitions) == 93
    assert {registry.get(name).source for name in SUPPORTED_TOOLS} == {
        "v1",
        "community-knowledge",
        "github-host",
        "chatgpt-share",
        "coordinator-x",
        "telegram-supervisor",
        "fusion-desktop",
    }

    fork_schema = registry.get("github_repository_fork").definition.input_schema
    assert fork_schema["required"] == [
        "project_id", "repository_id", "fork_repository_id",
    ]
    assert fork_schema["properties"]["fork_repository_id"]["pattern"] == (
        "^[a-z][a-z0-9-]{0,62}$"
    )
    assert fork_schema["additionalProperties"] is False


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
