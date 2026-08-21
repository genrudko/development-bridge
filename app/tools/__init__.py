from .execution import execution_call, execution_tools
from .git import git_call, git_tools
from .github import github_call, github_tools
from .search import search_call, search_tools
from .workspace import workspace_call, workspace_tools


TOOLS = (
    workspace_tools
    + git_tools
    + github_tools
    + execution_tools
    + search_tools
)


async def call_tool(ctx, params):
    for handler in (
        workspace_call,
        git_call,
        github_call,
        execution_call,
        search_call,
    ):
        result = await handler(ctx, params)

        if result is not None:
            return result

    return None

