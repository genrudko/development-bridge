from app.tools import TOOLS


EXPECTED_LEGACY_TOOLS = {
    "workspace_status",
    "read_file",
    "apply_patch",
    "git_status",
    "git_diff",
    "git_branch",
    "git_log",
    "git_commit",
    "git_push",
    "github_status",
    "run_command",
    "search_workspace",
}


def test_legacy_tool_surface_is_preserved():
    assert {tool.name for tool in TOOLS} == EXPECTED_LEGACY_TOOLS

