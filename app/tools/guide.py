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
    if name.startswith("project_") or name in {
        "repository_status", "repository_clone", "repository_retention_set",
        "repository_gc_plan", "repository_gc_apply",
    }:
        return "projects"
    if name == "chatgpt_share_read":
        return "chatgpt-share"
    if name == "run_command":
        return "commands"
    return "bridge"


def guide_tools(registry: ToolRegistry, *, tool_surface: str = "full") -> tuple[RegisteredTool, ...]:
    async def bridge_guide(ctx, params, request_context):
        from app.tools.compact import exposed_tool_definitions
        visible_tool_count = len(exposed_tool_definitions(registry, tool_surface))
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
                    "prefer coordinator_wake_on_jobs instead of repeated job_status polling",
                    "after wake (or one sparse checkpoint), read terminal job_status",
                    "job_output once terminal",
                ],
                "preferred_event_flow": [
                    "queue one or more jobs",
                    "call coordinator_wake_on_jobs as the final MCP App-bearing tool in the turn; it renders/refreshes the coordinator listener",
                    "end the model turn",
                    "X wakes a fresh turn",
                    "call coordinator_ack with the continuation_id before other work",
                    "process any batched_messages returned by coordinator_ack in the same model turn",
                    "read terminal job_status and job_output once per terminal group",
                ],
            },
            "economy_mode": {
                "objective": "Treat every model/tool round-trip as a scarce resource: minimize tool calls, chat growth, and live ChatGPT Web traffic without reducing verification quality.",
                "rules": [
                    "Plan before calling tools. Prefer one bounded execution that performs check -> change -> targeted tests -> concise status over a conversational sequence of shell commands.",
                    "For work lasting more than a few seconds, prefer coordinator_exec_and_wake or repository_exec. Put long scripts/data in stdin instead of splitting them across calls.",
                    "Do not poll durable jobs at short intervals. Prefer coordinator_wake_on_jobs; after a wake, read terminal job_status and job_output once per terminal group. If wake is unavailable, use sparse bounded checkpoints only.",
                    "Batch related read-only probes into one bounded command or search. Search/list first, then read only files or ranges that are actually relevant. Do not re-read unchanged files, status, schemas, or logs.",
                    "Keep output bounded: use grep/tail/sed, explicit limits, diff --stat/diff --check, and targeted tests. Never dump full logs or large generated files into chat unless the result itself requires them.",
                    "Reuse known tool schemas and repository state. Do not repeat discovery/list_resources/bridge_guide or capability checks within the same chat unless runtime state actually changed.",
                    "At the start of a meaningful bounded operation, call bridge_dashboard once with a progress payload; this creates the operation and its single visible dashboard card.",
                    "After start, use work_progress_update only at meaningful milestones and completion, passing operation_id from bridge_dashboard; progress updates are durable and non-UI.",
                    "Mark the operation completed at the end; never call bridge_dashboard repeatedly inside the same operation.",
                    "Report only meaningful checkpoints: blocker, decision, test result, commit/deploy result, or final outcome. Do not narrate every tool call or paste raw stdout that does not change the decision.",
                    "Treat ChatGPT Web/Browser Host interactions as especially expensive. Do design, code review, and tests offline first; run one deliberate live acceptance when possible. Respect rate-limit/backoff state and never retry live UI actions during backoff.",
                    "When delegating work, give the executor one bounded outcome, exact scope, invariants, tests, and stop conditions so it can finish autonomously without asking the coordinator to dispatch each substep.",
                ],
                "executor_job_shape": "One job should normally be: inspect exact state -> make the smallest scoped change -> run targeted verification -> emit a short structured result. Split jobs only for true dependency boundaries, destructive-risk gates, or materially independent repositories.",
            },
            "executor_delegation": {
                "rule": "Economy Mode and evidence-first Bridge semantics are mandatory for delegated LLM executors. Codex/repository-native executors should inherit the repository AGENTS.md automatically; if an executor does not load repository instructions, include the compact policy below in its initial prompt without spending an extra tool call to fetch it.",
                "evidence_first": [
                    "A compact tool surface does not mean a capability is unavailable; check hidden capabilities with bridge_search -> bridge_schema -> bridge_call before declaring them missing.",
                    "Shell credentials are not evidence of Bridge authentication: gh or shell git may be unauthenticated while Bridge-native GitHub/git tools remain correctly credentialed.",
                    "Use Bridge-native write paths; do not replace git_push/GitHub tools with shell git push, gh auth, PAT files, embedded credentials, or other credential workarounds.",
                    "Do not mutate origin/remotes/workspace registration as a diagnostic experiment. GitHub identity helpers may inspect origin, while git_push targets the configured remote named by the exact push plan.",
                    "Treat error codes as evidence rather than diagnoses. Test one hypothesis with the smallest discriminating check and discard it if evidence disproves it.",
                    "A blocker must be proven with the exact tool, error code/details, relevant state checked, and why no safe Bridge-native path remains.",
                ],
                "prompt_suffix": "ECONOMY MODE + EVIDENCE FIRST: Treat tool/model round-trips and coordinator context as scarce. Work toward one bounded outcome: inspect exact state -> smallest scoped change -> targeted verification -> concise result. Batch related probes; do not re-read unchanged state; keep logs bounded; do not poll durable jobs frequently; report only blockers/decisions/tests/final status, not each tool call. A compact tool surface does not mean a capability is unavailable: use bridge_search -> bridge_schema -> bridge_call before declaring a capability missing. Shell credentials are not evidence of Bridge auth. Do not use shell git push, gh auth, PAT files, or credential workarounds when Bridge-native write paths exist. Do not mutate origin/remotes/workspace topology as diagnosis. Keep GitHub identity helpers separate from git_push semantics: git_push uses the configured remote named in its exact plan. Treat an error code as evidence, not a diagnosis; test one hypothesis with one minimal discriminating check. A blocker must include the exact tool, error code/details, facts checked, and why no safe native path remains. Do all design/testing offline before any live ChatGPT Web action, and never retry live UI during rate-limit/backoff. Stop and report only for a proven blocker, required operator input, destructive-risk gate, missing invariant, materially new scope, or completed bounded outcome.",
            },
            "operator_guidance": {
                "run_command": "Use only for short direct commands; it is idle-gated per repository, so work in other repositories does not block it. Use repository_exec for durable work.",
                "bridge_restart": "Guarded self-restart using a user-systemd trampoline plus narrow sudoers bootstrap; reconnect and verify afterward. It does not deploy production.",
                "coordinator": (
                    "Normal worker setup: discover registered routes with hidden coordinator_route_list and mount with coordinator_x_mount(route_id=...). "
                    "Current route mapping: development-bridge -> bridge, eod -> eod, AD5X product work -> ad5xwork; if uncertain use coordinator_route_list. "
                    "Normal workers must never call coordinator_route_takeover to begin ordinary work. Never ask the owner to copy a ChatGPT URL for ordinary executor setup; "
                    "URLs are only for exceptional initial bootstrap or manual takeover. Automatic rollover remains the normal physical-chat successor path; "
                    "cross-project route takeover fails closed with POLICY_VIOLATION. "
                    "coordinator_wake_on_jobs and coordinator_exec_and_wake render/refresh the coordinator MCP App themselves; make the scheduling call the final MCP App-bearing tool before ending the model turn. coordinator_continue still requires an already mounted destination when route/channel are omitted. Resilient job continuations keep one active continuation per channel, batch concurrent terminal groups without overwriting them, and deduplicate repeated events. Transport failures may retry X up to 3 attempts, but after a successful ui/message transport ACK the same continuation is never redelivered; the Bridge waits for exact model ACK and escalates to Telegram if it never arrives. Terminal groups use a bounded debounce window and successful Web turns impose a persisted global cooldown across logical routes so ChatGPT Web is not used as a high-frequency event bus. Browser Host rate-limit detection can impose a shared Web backoff that suppresses new X claims. The pre-terminal waiter is durable across Bridge restart. The MCP App injects technical continuation protocol through ui/update-model-context so the visible user message stays human-only; a one-line ref is used only as fallback when the host lacks that capability."
                ),
                "chatgpt_share_read": "Reads cookie-free public ChatGPT shares in recent, search, or full mode; private/authenticated shares are unsupported.",
                "git_safety": "Inspect repository status and revisions, keep changes repository/branch scoped, use change plans and git push plans, and do not overwrite unrelated work.",
                "github": "Issue, pull-request, review, checks, Actions run/job/log/artifact, dispatch, rerun, and cancel operations are available when configured.",
                "knowledge": "Search/read configured knowledge sources and threads; sync or export attachments only when configured.",
                "workspace": "Project, repository, file, task, job, change, and artifact tools are scoped by explicit project_id/repository_id.",
            },
            "tool_surface": tool_surface,
            "tool_count": visible_tool_count,
            "internal_tool_count": len(registry.definitions),
            "tools_by_category": (
                dict(sorted(catalog.items()))
                if tool_surface == "full"
                else {name: {"count": len(rows), "examples": [row["name"] for row in rows[:4]]} for name, rows in sorted(catalog.items())}
            ),
            "compact_discovery": (
                "Use bridge_search, bridge_schema, and bridge_call for hidden capabilities."
                if tool_surface == "compact" else None
            ),
        }))

    return (RegisteredTool(
        types.Tool(
            name="bridge_guide",
            description="START HERE: call first in new coordinator chats for bounded operating guidance and the live capability summary",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        bridge_guide,
        "v1",
    ),)
