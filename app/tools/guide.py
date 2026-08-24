from __future__ import annotations

from collections import defaultdict

from mcp import types

from app.api.registry import RegisteredTool, ToolRegistry
from app.api.results import success, to_mcp_result


def _category(name: str) -> str:
    if name.startswith("github_"):
        return "github"
    if name.startswith("knowledge_"):
        return "knowledge"
    if name.startswith("coordinator_"):
        return "coordinator"
    if name.startswith("job_") or name in {"repository_exec", "task_list", "task_start"}:
        return "jobs"
    if name.startswith("git_"):
        return "git"
    if name.startswith("file_"):
        return "files"
    if name.startswith("change_"):
        return "changes"
    if name.startswith("project_") or name in {"repository_status", "repository_clone"}:
        return "projects"
    if name == "chatgpt_share_read":
        return "chatgpt-share"
    if name == "run_command":
        return "commands"
    return "bridge"


def guide_tools(registry: ToolRegistry) -> tuple[RegisteredTool, ...]:
    async def bridge_guide(ctx, params, request_context):
        catalog: dict[str, list[dict[str, str]]] = defaultdict(list)
        for tool in registry.definitions:
            catalog[_category(tool.name)].append(
                {"name": tool.name, "purpose": tool.description or ""}
            )
        return to_mcp_result(success(request_context.request_id, {
            "start_here": "Call bridge_guide first in each new coordinator chat.",
            "durable_jobs": {
                "rule": "repository_exec is asynchronous; an initial queued status is normal and is never evidence that the worker is broken.",
                "lifecycle": [
                    "repository_exec",
                    "job_status until status is succeeded, failed, or cancelled",
                    "job_output once terminal",
                ],
                "preferred_event_flow": [
                    "queue one or more jobs",
                    "call coordinator_wake_on_jobs",
                    "end the model turn",
                    "X wakes a fresh turn",
                    "call coordinator_ack with the continuation_id before other work",
                    "process any batched_messages returned by coordinator_ack in the same model turn",
                    "read terminal job_status and job_output once per terminal group",
                ],
            },
            "operator_guidance": {
                "run_command": "Use only for short direct commands; it is idle-gated per repository, so work in other repositories does not block it. Use repository_exec for durable work.",
                "bridge_restart": "Guarded self-restart using a user-systemd trampoline plus narrow sudoers bootstrap; reconnect and verify afterward. It does not deploy production.",
                "coordinator": "Mount coordinator_x_mount in the chat/channel before coordinator_continue or coordinator_wake_on_jobs. Resilient job continuations keep one active continuation per channel, batch concurrent terminal groups without overwriting them, and deduplicate repeated events. Transport failures may retry X up to 3 attempts, but after a successful ui/message transport ACK the same continuation is never redelivered; the Bridge waits for exact model ACK and escalates to Telegram if it never arrives. The pre-terminal waiter is durable across Bridge restart. The MCP App injects technical continuation protocol through ui/update-model-context so the visible user message stays human-only; a one-line ref is used only as fallback when the host lacks that capability.",
                "chatgpt_share_read": "Reads cookie-free public ChatGPT shares in recent, search, or full mode; private/authenticated shares are unsupported.",
                "git_safety": "Inspect repository status and revisions, keep changes repository/branch scoped, use change plans and git push plans, and do not overwrite unrelated work.",
                "github": "Issue, pull-request, review, checks, Actions run/job/log/artifact, dispatch, rerun, and cancel operations are available when configured.",
                "knowledge": "Search/read configured knowledge sources and threads; sync or export attachments only when configured.",
                "workspace": "Project, repository, file, task, job, change, and artifact tools are scoped by explicit project_id/repository_id.",
            },
            "tool_count": len(registry.definitions),
            "tools_by_category": dict(sorted(catalog.items())),
        }))

    return (RegisteredTool(
        types.Tool(
            name="bridge_guide",
            description="START HERE: call first in new coordinator chats for bounded operating guidance and the complete live tool catalog",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        bridge_guide,
        "v1",
    ),)
