from __future__ import annotations

from mcp import types

from app.api.registry import RegisteredTool
from app.api.resources import DEFAULT_FILE_RESOURCE_INLINE_LIMIT, file_resource_blocks
from app.api.results import success, to_mcp_result
from app.api.schemas import IDENTIFIER_SCHEMA
from app.container import ApplicationContainer


GITHUB_ARTIFACT_INLINE_LIMIT = DEFAULT_FILE_RESOURCE_INLINE_LIMIT
NUMBER = {"type": "integer", "minimum": 1}
SHA = {"type": "string", "pattern": "^[0-9a-fA-F]{40}$"}
TEXT = {"type": "string", "maxLength": 65536}
NONEMPTY_TEXT = {"type": "string", "minLength": 1, "maxLength": 65536}
NAME = {"type": "string", "minLength": 1, "maxLength": 255}
NAMES = {"type": "array", "maxItems": 100, "items": NAME}


def github_tools(container: ApplicationContainer) -> tuple[RegisteredTool, ...]:
    def repository(arguments):
        return container.projects.repositories.get(
            arguments["project_id"], arguments["repository_id"]
        )

    def result(request_context, data):
        return to_mcp_result(success(request_context.request_id, data))

    async def repository_status(ctx, params, rc):
        return result(rc, await container.github.repository_status(repository(params.arguments)))

    async def repository_fork(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.repository_fork(
            repository(a), a["project_id"], a["fork_repository_id"], a.get("depth", 50)
        ))

    async def commit_checks(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.commit_checks(repository(a), a["sha"]))

    async def issue_list(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.issue_list(repository(a), state=a.get("state", "open"), labels=a.get("labels", []), limit=a.get("limit", 50)))

    async def issue_get(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.issue_get(repository(a), a["issue_number"]))

    async def issue_comments(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.issue_comments(repository(a), a["issue_number"], a.get("limit", 50)))

    async def issue_create(ctx, params, rc):
        a = params.arguments
        payload = {key: a[key] for key in ("title", "body", "labels", "assignees", "milestone") if key in a}
        return result(rc, await container.github.issue_create(repository(a), payload))

    async def issue_update(ctx, params, rc):
        a = params.arguments
        payload = {key: a[key] for key in ("title", "body", "state", "state_reason", "labels", "assignees", "milestone") if key in a}
        return result(rc, await container.github.issue_update(repository(a), a["issue_number"], payload))

    async def issue_comment(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.issue_comment(repository(a), a["issue_number"], a["body"]))

    async def pull_list(ctx, params, rc):
        a = params.arguments
        filters = {"state": a.get("state", "open"), "base": a.get("base"), "head": a.get("head"), "per_page": a.get("limit", 50)}
        return result(rc, await container.github.pull_list(repository(a), filters))

    async def pull_get(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.pull_get(repository(a), a["pull_number"]))

    async def pull_create(ctx, params, rc):
        a = params.arguments
        payload = {key: a[key] for key in ("title", "body", "head", "base", "draft") if key in a}
        payload.setdefault("draft", True)
        return result(rc, await container.github.pull_create(repository(a), payload))

    async def pull_update(ctx, params, rc):
        a = params.arguments
        payload = {key: a[key] for key in ("title", "body", "state", "base", "draft") if key in a}
        return result(rc, await container.github.pull_update(repository(a), a["pull_number"], payload))

    async def pull_comment(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.pull_comment(repository(a), a["pull_number"], a["body"]))

    async def pull_reviews(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.pull_reviews(repository(a), a["pull_number"], a.get("limit", 50)))

    async def pull_review_comments(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.pull_review_comments(repository(a), a["pull_number"], a.get("limit", 50)))

    async def pull_files(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.pull_files(repository(a), a["pull_number"], a.get("limit", 50)))

    async def pull_review(ctx, params, rc):
        a = params.arguments
        payload = {key: a[key] for key in ("event", "body") if key in a}
        return result(rc, await container.github.pull_review(repository(a), a["pull_number"], payload))

    async def request_reviewers(ctx, params, rc):
        a = params.arguments
        payload = {"reviewers": a.get("reviewers", []), "team_reviewers": a.get("team_reviewers", [])}
        return result(rc, await container.github.request_reviewers(repository(a), a["pull_number"], payload))

    async def pull_merge(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.pull_merge(repository(a), a["pull_number"], a["expected_head"], a.get("method", "merge")))

    async def actions_runs(ctx, params, rc):
        a = params.arguments
        filters = {key: a.get(key) for key in ("branch", "event", "status")}
        filters["head_sha"] = a.get("head_sha")
        filters["workflow"] = a.get("workflow")
        filters["per_page"] = a.get("limit", 50)
        return result(rc, await container.github.actions_runs(repository(a), filters))

    async def actions_run(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.actions_run(repository(a), a["run_id"]))

    async def actions_jobs(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.actions_jobs(repository(a), a["run_id"], a.get("limit", 50)))

    async def actions_job_logs(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.actions_job_logs(repository(a), a["job_id"], a.get("limit_bytes", 262144)))

    async def actions_artifacts(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.actions_artifacts(repository(a), a["run_id"], a.get("limit", 50)))

    async def actions_artifact_export(ctx, params, rc):
        a = params.arguments
        data, snapshot = await container.github_artifact_exports.export(repository(a), a["artifact_id"])
        response = result(rc, data)
        response.content.extend(file_resource_blocks(snapshot.path, uri=data["export_url"], file_name=snapshot.file_name, media_type=snapshot.media_type, size_bytes=snapshot.size_bytes, inline_limit=GITHUB_ARTIFACT_INLINE_LIMIT, description="Short-lived HTTPS link to an immutable GitHub Actions artifact"))
        return response

    async def actions_dispatch(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.actions_dispatch(repository(a), a["workflow"], a["ref"], a.get("inputs", {})))

    async def actions_rerun(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.actions_rerun(repository(a), a["run_id"], a.get("failed_only", False)))

    async def actions_cancel(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.actions_cancel(repository(a), a["run_id"]))

    async def release_list(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.release_list(repository(a), a.get("limit", 50)))

    async def release_get(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.release_get(repository(a), a["tag_name"]))

    async def release_plan(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.release_plan(
            repository(a), tag_name=a["tag_name"], target_sha=a["target_sha"],
            name=a["name"], body=a.get("body", ""), draft=a.get("draft", False),
            prerelease=a.get("prerelease", False), make_latest=a.get("make_latest", "true")
        ))

    async def release_apply(ctx, params, rc):
        a = params.arguments
        return result(rc, await container.github.release_apply(repository(a), a["plan_id"]))

    scope = {"project_id": IDENTIFIER_SCHEMA, "repository_id": IDENTIFIER_SCHEMA}
    issue_number = {"issue_number": NUMBER}
    pull_number = {"pull_number": NUMBER}
    limit = {"limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}}
    state = {"state": {"type": "string", "enum": ["open", "closed", "all"], "default": "open"}}
    issue_fields = {"title": {"type": "string", "minLength": 1, "maxLength": 512}, "body": TEXT, "labels": NAMES, "assignees": NAMES, "milestone": {"type": "integer", "minimum": 1}}

    definitions = (
        ("github_repository_status", "Show GitHub repository identity and host status", {}, [], repository_status),
        ("github_repository_fork", "Fork an upstream GitHub repository and register a writable managed workspace", {"fork_repository_id": IDENTIFIER_SCHEMA, "depth": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 50}}, ["fork_repository_id"], repository_fork),
        ("github_commit_checks", "Show check runs and commit status contexts", {"sha": SHA}, ["sha"], commit_checks),
        ("github_issue_list", "List bounded GitHub issues", {**state, "labels": NAMES, **limit}, [], issue_list),
        ("github_issue_get", "Get one GitHub issue", issue_number, ["issue_number"], issue_get),
        ("github_issue_comments", "List bounded GitHub issue conversation comments", {**issue_number, **limit}, ["issue_number"], issue_comments),
        ("github_issue_create", "Create a GitHub issue", issue_fields, ["title"], issue_create),
        ("github_issue_update", "Update a GitHub issue", {**issue_number, **issue_fields, "state": {"type": "string", "enum": ["open", "closed"]}, "state_reason": {"type": "string", "enum": ["completed", "not_planned", "reopened"]}}, ["issue_number"], issue_update),
        ("github_issue_comment", "Comment on a GitHub issue", {**issue_number, "body": NONEMPTY_TEXT}, ["issue_number", "body"], issue_comment),
        ("github_pull_request_list", "List bounded GitHub pull requests", {**state, "base": NAME, "head": NAME, **limit}, [], pull_list),
        ("github_pull_request_get", "Get one GitHub pull request", pull_number, ["pull_number"], pull_get),
        ("github_pull_request_create", "Create a GitHub pull request", {"title": issue_fields["title"], "body": TEXT, "head": NAME, "base": NAME, "draft": {"type": "boolean", "default": True}}, ["title", "head", "base"], pull_create),
        ("github_pull_request_update", "Update a GitHub pull request including draft state", {**pull_number, "title": issue_fields["title"], "body": TEXT, "state": {"type": "string", "enum": ["open", "closed"]}, "base": NAME, "draft": {"type": "boolean"}}, ["pull_number"], pull_update),
        ("github_pull_request_comment", "Comment on a GitHub pull request", {**pull_number, "body": NONEMPTY_TEXT}, ["pull_number", "body"], pull_comment),
        ("github_pull_request_reviews", "List bounded pull request reviews", {**pull_number, **limit}, ["pull_number"], pull_reviews),
        ("github_pull_request_review_comments", "List bounded inline pull request review comments", {**pull_number, **limit}, ["pull_number"], pull_review_comments),
        ("github_pull_request_files", "List bounded pull request file and patch evidence", {**pull_number, **limit}, ["pull_number"], pull_files),
        ("github_pull_request_review", "Submit a pull request review", {**pull_number, "event": {"type": "string", "enum": ["COMMENT", "APPROVE", "REQUEST_CHANGES"]}, "body": TEXT}, ["pull_number", "event"], pull_review),
        ("github_pull_request_request_reviewers", "Request pull request reviewers", {**pull_number, "reviewers": NAMES, "team_reviewers": NAMES}, ["pull_number"], request_reviewers),
        ("github_pull_request_merge", "Merge a pull request only at an exact expected head", {**pull_number, "expected_head": SHA, "method": {"type": "string", "enum": ["merge", "squash", "rebase"], "default": "merge"}}, ["pull_number", "expected_head"], pull_merge),
        ("github_actions_runs", "List bounded GitHub Actions runs", {"branch": NAME, "head_sha": SHA, "event": NAME, "status": NAME, "workflow": NAME, **limit}, [], actions_runs),
        ("github_actions_run", "Get one GitHub Actions run", {"run_id": NUMBER}, ["run_id"], actions_run),
        ("github_actions_jobs", "List bounded jobs for a GitHub Actions run", {"run_id": NUMBER, **limit}, ["run_id"], actions_jobs),
        ("github_actions_job_logs", "Read bounded logs for a GitHub Actions job", {"job_id": NUMBER, "limit_bytes": {"type": "integer", "minimum": 1024, "maximum": 1048576, "default": 262144}}, ["job_id"], actions_job_logs),
        ("github_actions_artifacts", "List bounded artifacts for a GitHub Actions run", {"run_id": NUMBER, **limit}, ["run_id"], actions_artifacts),
        ("github_actions_artifact_export", "Snapshot and export a GitHub Actions artifact through native MCP resources", {"artifact_id": NUMBER}, ["artifact_id"], actions_artifact_export),
        ("github_actions_dispatch", "Dispatch a GitHub Actions workflow", {"workflow": NAME, "ref": NAME, "inputs": {"type": "object", "maxProperties": 100, "additionalProperties": {"type": "string", "maxLength": 4096}}}, ["workflow", "ref"], actions_dispatch),
        ("github_actions_rerun", "Rerun all or failed GitHub Actions jobs", {"run_id": NUMBER, "failed_only": {"type": "boolean", "default": False}}, ["run_id"], actions_rerun),
        ("github_actions_cancel", "Cancel a GitHub Actions run", {"run_id": NUMBER}, ["run_id"], actions_cancel),
        ("github_release_list", "List bounded GitHub releases", {**limit}, [], release_list),
        ("github_release_get", "Get one GitHub release by tag", {"tag_name": NAME}, ["tag_name"], release_get),
        ("github_release_plan", "Plan a fail-closed GitHub release at an exact commit SHA", {"tag_name": NAME, "target_sha": SHA, "name": NAME, "body": TEXT, "draft": {"type": "boolean", "default": False}, "prerelease": {"type": "boolean", "default": False}, "make_latest": {"type": "string", "enum": ["true", "false", "legacy"], "default": "true"}}, ["tag_name", "target_sha", "name"], release_plan),
        ("github_release_apply", "Apply an unchanged GitHub release plan without moving existing tags", {"plan_id": {"type": "string", "pattern": "^sha256:[0-9a-fA-F]{64}$"}}, ["plan_id"], release_apply),
    )
    return tuple(
        RegisteredTool(types.Tool(name=name, description=description, inputSchema={"type": "object", "properties": {**scope, **properties}, "required": ["project_id", "repository_id", *required], "additionalProperties": False}), handler, "github-host")
        for name, description, properties, required, handler in definitions
    )
