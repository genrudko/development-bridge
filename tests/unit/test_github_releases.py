from __future__ import annotations

import subprocess

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import CapabilityPolicy, CapabilitySet
from app.git import GitRunner
from app.github import GitHubHostService
from app.projects import Repository
from tests.fixtures.github_transport import FakeGitHubTransport
from tests.fixtures.repositories import create_git_repository


def github_repository(tmp_path):
    root = create_git_repository(tmp_path, "release-repo")
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/acme/widgets.git"],
        cwd=root, check=True,
    )
    return Repository(
        "project", "repo", root,
        CapabilitySet.from_mapping({"git_read": True, "git_write": True}),
    )


def release(tag="v1.0.0", target="a" * 40, **updates):
    value = {
        "id": 10, "tag_name": tag, "target_commitish": target, "name": "Widgets v1.0.0",
        "body": "notes", "draft": False, "prerelease": False,
        "created_at": "2026-08-28T00:00:00Z", "published_at": "2026-08-28T00:01:00Z",
        "html_url": "https://github.com/acme/widgets/releases/tag/v1.0.0",
    }
    value.update(updates)
    return value


def add_plan_reads(transport, *, target="a" * 40, default="b" * 40, tag=None, rel=None, status="ahead"):
    repo = "/repos/acme/widgets"
    transport.add("GET", f"{repo}/commits/{target}", {"sha": target})
    transport.add("GET", repo, {"default_branch": "main"})
    transport.add("GET", f"{repo}/commits/main", {"sha": default})
    transport.add("GET", f"{repo}/compare/{target}...{default}?per_page=1", {"status": status})
    if tag is None:
        transport.add("GET", f"{repo}/git/ref/tags/v1.0.0", {}, status=404)
    else:
        transport.add("GET", f"{repo}/git/ref/tags/v1.0.0", tag)
    if rel is None:
        transport.add("GET", f"{repo}/releases/tags/v1.0.0", {}, status=404)
    else:
        transport.add("GET", f"{repo}/releases/tags/v1.0.0", rel)


@pytest.mark.asyncio
async def test_release_plan_apply_exact_non_head_commit_and_repeat_is_idempotent(tmp_path):
    repository = github_repository(tmp_path)
    transport = FakeGitHubTransport()
    service = GitHubHostService(GitRunner(), CapabilityPolicy(), transport)
    target, default = "a" * 40, "b" * 40

    add_plan_reads(transport, target=target, default=default)
    plan = await service.release_plan(
        repository, tag_name="v1.0.0", target_sha=target, name="Widgets v1.0.0", body="notes"
    )
    assert plan["applicable"] is True
    assert plan["action"] == "create_tag_and_release"
    assert plan["target_sha"] == target
    assert plan["default_sha"] == default
    assert plan["target_reachable"] is True

    add_plan_reads(transport, target=target, default=default)
    transport.add("POST", "/repos/acme/widgets/git/refs", {"ref": "refs/tags/v1.0.0", "object": {"type": "commit", "sha": target}}, status=201)
    transport.add("POST", "/repos/acme/widgets/releases", release(target=target), status=201)
    transport.add("GET", "/repos/acme/widgets/git/ref/tags/v1.0.0", {"ref": "refs/tags/v1.0.0", "object": {"type": "commit", "sha": target}})
    applied = await service.release_apply(repository, plan["plan_id"])
    assert applied["status"] == "applied"
    assert applied["tag_created"] is True and applied["release_created"] is True
    assert applied["target_sha"] == target
    create_ref = next(call for call in transport.calls if call[0] == "POST" and call[1].endswith("/git/refs"))
    assert create_ref[2] == {"ref": "refs/tags/v1.0.0", "sha": target}
    create_release = next(call for call in transport.calls if call[0] == "POST" and call[1].endswith("/releases"))
    assert create_release[2]["target_commitish"] == target

    tag_state = {"ref": "refs/tags/v1.0.0", "object": {"type": "commit", "sha": target}}
    add_plan_reads(transport, target=target, default=default, tag=tag_state, rel=release(target=target))
    repeated = await service.release_apply(repository, plan["plan_id"])
    assert repeated["status"] == "already_applied"
    assert repeated["tag_created"] is False and repeated["release_created"] is False


@pytest.mark.asyncio
async def test_release_same_tag_different_sha_fails_closed_without_write(tmp_path):
    repository = github_repository(tmp_path)
    transport = FakeGitHubTransport()
    service = GitHubHostService(GitRunner(), CapabilityPolicy(), transport)
    target = "a" * 40
    conflicting = {"ref": "refs/tags/v1.0.0", "object": {"type": "commit", "sha": "c" * 40}}
    add_plan_reads(transport, target=target, tag=conflicting)
    plan = await service.release_plan(
        repository, tag_name="v1.0.0", target_sha=target, name="Widgets v1.0.0", body="notes"
    )
    assert plan["applicable"] is False
    assert plan["action"] == "rejected"
    assert "tag_target_conflict" in plan["reasons"]

    add_plan_reads(transport, target=target, tag=conflicting)
    with pytest.raises(BridgeError) as raised:
        await service.release_apply(repository, plan["plan_id"])
    assert raised.value.code is ErrorCode.GITHUB_CONFLICT
    assert not any(method == "POST" for method, _path, _payload in transport.calls)


@pytest.mark.asyncio
async def test_release_partial_tag_state_can_resume_release_only(tmp_path):
    repository = github_repository(tmp_path)
    transport = FakeGitHubTransport()
    service = GitHubHostService(GitRunner(), CapabilityPolicy(), transport)
    target = "a" * 40
    add_plan_reads(transport, target=target)
    plan = await service.release_plan(
        repository, tag_name="v1.0.0", target_sha=target, name="Widgets v1.0.0", body="notes"
    )
    tag_state = {"ref": "refs/tags/v1.0.0", "object": {"type": "commit", "sha": target}}
    add_plan_reads(transport, target=target, tag=tag_state)
    transport.add("POST", "/repos/acme/widgets/releases", release(target=target), status=201)
    transport.add("GET", "/repos/acme/widgets/git/ref/tags/v1.0.0", tag_state)
    result = await service.release_apply(repository, plan["plan_id"])
    assert result["status"] == "applied"
    assert result["tag_created"] is False and result["release_created"] is True
    assert not any(method == "POST" and path.endswith("/git/refs") for method, path, _ in transport.calls)


@pytest.mark.asyncio
async def test_release_plan_rejects_unreachable_target(tmp_path):
    repository = github_repository(tmp_path)
    transport = FakeGitHubTransport()
    service = GitHubHostService(GitRunner(), CapabilityPolicy(), transport)
    add_plan_reads(transport, status="diverged")
    plan = await service.release_plan(
        repository, tag_name="v1.0.0", target_sha="a" * 40, name="Widgets v1.0.0", body="notes"
    )
    assert plan["applicable"] is False
    assert "target_not_reachable_from_default_branch" in plan["reasons"]


@pytest.mark.asyncio
async def test_repository_status_exposes_supported_and_classic_pat_permissions(tmp_path):
    repository = github_repository(tmp_path)
    transport = FakeGitHubTransport()
    service = GitHubHostService(GitRunner(), CapabilityPolicy(), transport)
    transport.add(
        "GET", "/repos/acme/widgets",
        {"default_branch": "main", "visibility": "public", "private": False, "archived": False},
        headers={"X-OAuth-Scopes": "repo"},
    )
    status = await service.repository_status(repository)
    permissions = status["github_permissions"]
    assert permissions["executor_credentials_exposed"] is False
    assert permissions["releases_write"] == {"bridge_support": True, "credential_permission": "allowed"}
    assert permissions["tags_write"] == {"bridge_support": True, "credential_permission": "allowed"}
    assert permissions["workflow_write"] == {"bridge_support": "git_push", "credential_permission": "denied"}
    assert permissions["release_assets_write"]["bridge_support"] is False
