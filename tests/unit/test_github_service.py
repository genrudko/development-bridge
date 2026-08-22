from __future__ import annotations

import subprocess

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import CapabilityPolicy, CapabilitySet
from app.git import GitRunner
from app.github import GitHubHostService, resolve_github_origin
from app.projects import Repository
from tests.fixtures.github_transport import FakeGitHubTransport
from tests.fixtures.repositories import create_git_repository


def github_repository(tmp_path, capabilities=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    root = create_git_repository(tmp_path, "github-repo")
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/acme/widgets.git"],
        cwd=root, check=True,
    )
    return Repository(
        "project", "repo", root,
        CapabilitySet.from_mapping(capabilities or {"git_read": True, "git_write": True}),
    )


@pytest.mark.parametrize("origin", [
    "https://github.com/acme/widgets.git",
    "https://github.com/acme/widgets",
    "git@github.com:acme/widgets.git",
    "ssh://git@github.com/acme/widgets.git",
])
def test_github_origin_resolution(origin):
    identity = resolve_github_origin(origin)
    assert identity.slug == "acme/widgets"


@pytest.mark.parametrize("origin", [
    "https://gitlab.com/acme/widgets.git", "file:///tmp/repo",
    "https://user:secret@github.com/acme/widgets.git", "git@github.com:bad",
])
def test_github_origin_rejects_unsupported_targets(origin):
    with pytest.raises(BridgeError) as raised:
        resolve_github_origin(origin)
    assert raised.value.code is ErrorCode.GITHUB_REPOSITORY_UNAVAILABLE


@pytest.mark.asyncio
async def test_github_optional_configuration_and_capability_split(tmp_path):
    repository = github_repository(tmp_path)
    unconfigured = GitHubHostService(GitRunner(), CapabilityPolicy(), None)
    status = await unconfigured.repository_status(repository)
    assert status == {"configured": False, "owner": "acme", "repository": "widgets"}
    with pytest.raises(BridgeError) as missing:
        await unconfigured.issue_get(repository, 1)
    assert missing.value.code is ErrorCode.GITHUB_NOT_CONFIGURED

    read_only = github_repository(tmp_path / "second", {"git_read": True})
    transport = FakeGitHubTransport()
    transport.add("GET", "/repos/acme/widgets/issues?state=open&labels=&per_page=1", [])
    service = GitHubHostService(GitRunner(), CapabilityPolicy(), transport)
    assert await service.issue_list(read_only, limit=1) == {"issues": []}
    with pytest.raises(BridgeError) as denied:
        await service.issue_create(read_only, {"title": "No"})
    assert denied.value.code is ErrorCode.PERMISSION_DENIED


def issue(number=1, **updates):
    value = {"number": number, "title": "Issue", "body": "Body", "state": "open", "labels": [], "assignees": [], "user": {"login": "alice"}, "comments": 0, "html_url": f"https://github.com/acme/widgets/issues/{number}"}
    value.update(updates); return value


def pull(number=2, draft=True, head="a" * 40, **updates):
    value = issue(number, title="PR", draft=draft, merged=False, mergeable=True, mergeable_state="clean", head={"ref": "feature", "sha": head}, base={"ref": "main", "sha": "b" * 40}, node_id="PR_node")
    value.update(updates); return value


@pytest.mark.asyncio
async def test_github_issues_pr_checks_and_exact_head_merge(tmp_path):
    repository = github_repository(tmp_path)
    transport = FakeGitHubTransport()
    service = GitHubHostService(GitRunner(), CapabilityPolicy(), transport)
    repo = "/repos/acme/widgets"
    transport.add("GET", repo, {"default_branch": "main", "visibility": "public", "private": False, "archived": False, "html_url": "url"}, headers={"x-ratelimit-remaining": "4999"})
    transport.add("GET", repo + "/commits/" + "a" * 40 + "/check-runs?per_page=100", {"check_runs": [{"id": 1, "name": "test", "status": "completed", "conclusion": "success"}]})
    transport.add("GET", repo + "/commits/" + "a" * 40 + "/status?per_page=100", {"state": "success", "statuses": [{"context": "legacy", "state": "success"}]})
    transport.add("GET", repo + "/issues?state=open&labels=bug&per_page=10", [issue()])
    transport.add("GET", repo + "/issues/1", issue())
    transport.add("POST", repo + "/issues", issue())
    transport.add("PATCH", repo + "/issues/1", issue(title="Updated"))
    transport.add("POST", repo + "/issues/1/comments", {"id": 9, "body": "comment", "user": {"login": "alice"}})
    assert (await service.repository_status(repository))["configured"] is True
    checks = await service.commit_checks(repository, "a" * 40)
    assert checks["check_runs"][0]["name"] == "test" and checks["contexts"][0]["context"] == "legacy"
    assert (await service.issue_list(repository, state="open", labels=["bug"], limit=10))["issues"]
    assert (await service.issue_get(repository, 1))["number"] == 1
    assert (await service.issue_create(repository, {"title": "Issue"}))["number"] == 1
    assert (await service.issue_update(repository, 1, {"title": "Updated"}))["title"] == "Updated"
    assert (await service.issue_comment(repository, 1, "comment"))["body"] == "comment"

    transport.add("GET", repo + "/pulls?state=open&per_page=50", [pull()])
    transport.add("GET", repo + "/pulls/2", pull())
    transport.add("POST", repo + "/pulls", pull())
    transport.add("PATCH", repo + "/pulls/2", pull(title="Changed"))
    transport.add("POST", repo + "/issues/2/comments", {"id": 10, "body": "pr comment"})
    transport.add("GET", repo + "/pulls/2/reviews?per_page=50", [{"id": 3, "state": "APPROVED", "body": "ok", "user": {"login": "bob"}, "commit_id": "a" * 40}])
    transport.add("POST", repo + "/pulls/2/reviews", {"id": 4, "state": "APPROVED", "body": "ok", "user": {"login": "me"}})
    transport.add("POST", repo + "/pulls/2/requested_reviewers", pull())
    assert (await service.pull_list(repository, {"state": "open", "per_page": 50}))["pull_requests"]
    assert (await service.pull_get(repository, 2))["draft"] is True
    assert (await service.pull_create(repository, {"title": "PR", "head": "feature", "base": "main", "draft": True}))["draft"] is True
    assert (await service.pull_update(repository, 2, {"title": "Changed"}))["title"] == "Changed"
    assert (await service.pull_comment(repository, 2, "pr comment"))["body"] == "pr comment"
    assert (await service.pull_reviews(repository, 2))["reviews"][0]["state"] == "APPROVED"
    assert (await service.pull_review(repository, 2, {"event": "APPROVE", "body": "ok"}))["state"] == "APPROVED"
    assert (await service.request_reviewers(repository, 2, {"reviewers": ["bob"]}))["number"] == 2

    transport.add("GET", repo + "/pulls/2", pull(head="a" * 40))
    transport.add("PUT", repo + "/pulls/2/merge", {"merged": True, "sha": "c" * 40})
    merged = await service.pull_merge(repository, 2, "a" * 40, "squash")
    assert merged["merged"] is True
    transport.add("GET", repo + "/pulls/2", pull(head="d" * 40))
    with pytest.raises(BridgeError) as changed:
        await service.pull_merge(repository, 2, "a" * 40, "merge")
    assert changed.value.code is ErrorCode.GITHUB_CONFLICT

    transport.add("GET", repo + "/pulls/2", pull(draft=True))
    transport.add("POST", "/graphql", {"data": {}})
    transport.add("GET", repo + "/pulls/2", pull(draft=False))
    assert (await service.pull_update(repository, 2, {"draft": False}))["draft"] is False
    transport.add("GET", repo + "/pulls/2", pull(draft=False))
    transport.add("POST", "/graphql", {"data": {}})
    transport.add("GET", repo + "/pulls/2", pull(draft=True))
    assert (await service.pull_update(repository, 2, {"draft": True}))["draft"] is True


@pytest.mark.asyncio
async def test_github_actions_workflow_and_error_normalization(tmp_path):
    repository = github_repository(tmp_path)
    transport = FakeGitHubTransport(); service = GitHubHostService(GitRunner(), CapabilityPolicy(), transport)
    repo = "/repos/acme/widgets"
    run = {"id": 5, "name": "CI", "event": "push", "status": "completed", "conclusion": "success", "head_branch": "main", "head_sha": "a" * 40}
    transport.add("GET", repo + "/actions/runs?per_page=20", {"workflow_runs": [run]})
    transport.add("GET", repo + "/actions/runs/5", run)
    transport.add("GET", repo + "/actions/runs/5/jobs?per_page=10", {"jobs": [{"id": 7, "name": "test", "steps": [{"number": 1, "name": "run", "status": "completed"}]}]})
    transport.downloads[repo + "/actions/jobs/7/logs"] = b"line\n" * 100
    transport.add("GET", repo + "/actions/runs/5/artifacts?per_page=10", {"artifacts": [{"id": 8, "name": "build", "size_in_bytes": 3, "expired": False}]})
    transport.add("POST", repo + "/actions/workflows/ci.yml/dispatches", b"", status=204)
    transport.add("POST", repo + "/actions/runs/5/rerun", b"", status=201)
    transport.add("POST", repo + "/actions/runs/5/rerun-failed-jobs", b"", status=201)
    transport.add("POST", repo + "/actions/runs/5/cancel", b"", status=202)
    assert (await service.actions_runs(repository, {"workflow": None, "per_page": 20}))["runs"][0]["id"] == 5
    assert (await service.actions_run(repository, 5))["id"] == 5
    assert (await service.actions_jobs(repository, 5, 10))["jobs"][0]["id"] == 7
    logs = await service.actions_job_logs(repository, 7, 16)
    assert logs["truncated"] is True and len(logs["text"].encode()) == 16
    assert (await service.actions_artifacts(repository, 5, 10))["artifacts"][0]["id"] == 8
    assert (await service.actions_dispatch(repository, "ci.yml", "main", {}))["status"] == "dispatched"
    assert (await service.actions_rerun(repository, 5, False))["failed_only"] is False
    assert (await service.actions_rerun(repository, 5, True))["failed_only"] is True
    assert (await service.actions_cancel(repository, 5))["status"] == "cancel_requested"

    for status, code in ((404, ErrorCode.GITHUB_REPOSITORY_UNAVAILABLE), (422, ErrorCode.GITHUB_CONFLICT), (500, ErrorCode.GITHUB_API_ERROR)):
        transport.add("GET", repo + "/issues/99", {"message": "secret token must not leak"}, status=status)
        with pytest.raises(BridgeError) as raised:
            await service.issue_get(repository, 99)
        assert raised.value.code is code and "secret" not in raised.value.message
    transport.add("GET", repo + "/issues/99", {}, status=429)
    with pytest.raises(BridgeError) as limited:
        await service.issue_get(repository, 99)
    assert limited.value.code is ErrorCode.GITHUB_RATE_LIMITED


@pytest.mark.asyncio
async def test_pull_draft_graphql_errors_and_unchanged_state_fail_closed(tmp_path):
    repository = github_repository(tmp_path)
    repo = "/repos/acme/widgets"

    errors_transport = FakeGitHubTransport()
    errors_service = GitHubHostService(GitRunner(), CapabilityPolicy(), errors_transport)
    errors_transport.add("GET", repo + "/pulls/2", pull(draft=True))
    errors_transport.add(
        "POST",
        "/graphql",
        {"data": None, "errors": [{"message": "secret must not escape"}]},
    )
    with pytest.raises(BridgeError) as graphql_error:
        await errors_service.pull_update(repository, 2, {"draft": False})
    assert graphql_error.value.code is ErrorCode.GITHUB_CONFLICT
    assert "secret" not in graphql_error.value.message

    unchanged_transport = FakeGitHubTransport()
    unchanged_service = GitHubHostService(
        GitRunner(), CapabilityPolicy(), unchanged_transport
    )
    unchanged_transport.add("GET", repo + "/pulls/2", pull(draft=False))
    unchanged_transport.add("POST", "/graphql", {"data": {}})
    unchanged_transport.add("GET", repo + "/pulls/2", pull(draft=False))
    with pytest.raises(BridgeError) as unchanged:
        await unchanged_service.pull_update(repository, 2, {"draft": True})
    assert unchanged.value.code is ErrorCode.GITHUB_CONFLICT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("workflow", "encoded"),
    [
        ("ci.yml", "ci.yml"),
        ("123456", "123456"),
        ("Build and Test.yml", "Build%20and%20Test.yml"),
        ("../foo/bar?x#fragment", "..%2Ffoo%2Fbar%3Fx%23fragment"),
    ],
)
async def test_workflow_identifier_is_one_escaped_path_segment(
    tmp_path, workflow, encoded
):
    repository = github_repository(tmp_path)
    transport = FakeGitHubTransport()
    service = GitHubHostService(GitRunner(), CapabilityPolicy(), transport)
    repo = "/repos/acme/widgets"
    transport.add(
        "GET",
        f"{repo}/actions/workflows/{encoded}/runs?per_page=1",
        {"workflow_runs": []},
    )
    transport.add(
        "POST",
        f"{repo}/actions/workflows/{encoded}/dispatches",
        b"",
        status=204,
    )

    assert await service.actions_runs(
        repository, {"workflow": workflow, "per_page": 1}
    ) == {"runs": []}
    dispatched = await service.actions_dispatch(repository, workflow, "main", {})
    assert dispatched["workflow"] == workflow


@pytest.mark.asyncio
async def test_github_review_read_surfaces_are_bounded_and_normalized(tmp_path):
    repository = github_repository(tmp_path, {"git_read": True})
    transport = FakeGitHubTransport()
    service = GitHubHostService(GitRunner(), CapabilityPolicy(), transport)
    repo = "/repos/acme/widgets"
    conversation = {
        "id": 11,
        "body": "discussion",
        "user": {"login": "alice"},
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "html_url": "https://github.com/acme/widgets/issues/2#issuecomment-11",
    }
    transport.add(
        "GET", repo + "/issues/2/comments?per_page=2", [conversation] * 3
    )
    comments = await service.issue_comments(repository, 2, 2)
    assert comments == {"comments": [{
        "id": 11,
        "body": "discussion",
        "author": "alice",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "url": "https://github.com/acme/widgets/issues/2#issuecomment-11",
    }] * 2}

    inline = {
        "id": 12,
        "body": "inline",
        "user": {"login": "bob"},
        "commit_id": "a" * 40,
        "original_commit_id": "b" * 40,
        "path": "src/app.py",
        "line": 20,
        "original_line": 18,
        "start_line": 17,
        "side": "RIGHT",
        "start_side": "RIGHT",
        "in_reply_to_id": 10,
        "created_at": "2026-01-03T00:00:00Z",
        "updated_at": "2026-01-04T00:00:00Z",
        "html_url": "https://github.com/acme/widgets/pull/2#discussion_r12",
    }
    transport.add("GET", repo + "/pulls/2/comments?per_page=1", [inline, inline])
    review_comments = await service.pull_review_comments(repository, 2, 1)
    assert review_comments["comments"] == [{
        "id": 12,
        "body": "inline",
        "author": "bob",
        "commit_sha": "a" * 40,
        "original_commit_sha": "b" * 40,
        "path": "src/app.py",
        "line": 20,
        "original_line": 18,
        "start_line": 17,
        "side": "RIGHT",
        "start_side": "RIGHT",
        "in_reply_to_id": 10,
        "created_at": "2026-01-03T00:00:00Z",
        "updated_at": "2026-01-04T00:00:00Z",
        "url": "https://github.com/acme/widgets/pull/2#discussion_r12",
    }]

    oversized_patch = "я" * 40_000
    transport.add("GET", repo + "/pulls/2/files?per_page=3", [
        {"filename": "src/app.py", "status": "modified", "additions": 2, "deletions": 1, "changes": 3, "patch": "@@ normal"},
        {"filename": "src/large.py", "status": "modified", "additions": 1, "deletions": 1, "changes": 2, "patch": oversized_patch},
        {"filename": "new.py", "previous_filename": "old.py", "status": "renamed", "additions": 0, "deletions": 0, "changes": 0},
    ])
    files = (await service.pull_files(repository, 2, 3))["files"]
    assert files[0]["patch"] == "@@ normal" and files[0]["patch_truncated"] is False
    assert len(files[1]["patch"].encode("utf-8")) <= 65_536
    assert files[1]["patch_truncated"] is True
    assert files[2]["previous_filename"] == "old.py"
    assert files[2]["patch"] is None and files[2]["patch_truncated"] is False
