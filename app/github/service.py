from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode, urlparse

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import Capability, CapabilityPolicy
from app.git import GitRunner
from app.projects import Repository

from .client import GitHubTransport, _http_error


PULL_REQUEST_PATCH_LIMIT_BYTES = 65_536


@dataclass(frozen=True, slots=True)
class GitHubRepositoryIdentity:
    owner: str
    repository: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repository}"


class GitHubHostService:
    def __init__(
        self,
        runner: GitRunner,
        policy: CapabilityPolicy,
        transport: GitHubTransport | None,
    ) -> None:
        self.runner = runner
        self.policy = policy
        self.transport = transport

    async def identity(self, repository: Repository) -> GitHubRepositoryIdentity:
        self._require(repository, Capability.GIT_READ)
        try:
            result = await self.runner.run(repository, ["remote", "get-url", "origin"])
        except BridgeError as exc:
            if exc.code is not ErrorCode.GIT_COMMAND_FAILED:
                raise
            raise BridgeError(
                ErrorCode.GITHUB_REPOSITORY_UNAVAILABLE,
                "Repository has no available GitHub origin",
            ) from exc
        return resolve_github_origin(result.stdout.strip())

    async def repository_status(self, repository: Repository) -> dict:
        identity = await self.identity(repository)
        if self.transport is None:
            return {"configured": False, "owner": identity.owner, "repository": identity.repository}
        data, headers = await self._request(repository, "GET", self._repo(identity), write=False)
        return {
            "configured": True,
            "owner": identity.owner,
            "repository": identity.repository,
            "default_branch": data.get("default_branch"),
            "visibility": data.get("visibility"),
            "private": data.get("private"),
            "archived": data.get("archived"),
            "url": data.get("html_url"),
            "rate_limit": self._rate(headers),
        }

    async def commit_checks(self, repository: Repository, sha: str) -> dict:
        identity = await self.identity(repository)
        checks, _ = await self._request(repository, "GET", f"{self._repo(identity)}/commits/{sha}/check-runs?per_page=100", write=False)
        statuses, headers = await self._request(repository, "GET", f"{self._repo(identity)}/commits/{sha}/status?per_page=100", write=False)
        return {
            "sha": sha,
            "check_runs": [self._check_run(item) for item in checks.get("check_runs", [])[:100]],
            "status": statuses.get("state"),
            "contexts": [self._status(item) for item in statuses.get("statuses", [])[:100]],
            "rate_limit": self._rate(headers),
        }

    async def issue_list(self, repository, *, state="open", labels=(), limit=50):
        identity = await self.identity(repository)
        query = urlencode({"state": state, "labels": ",".join(labels), "per_page": self._limit(limit)})
        data, _ = await self._request(repository, "GET", f"{self._repo(identity)}/issues?{query}", write=False)
        return {"issues": [self._issue(item) for item in data if "pull_request" not in item][:limit]}

    async def issue_get(self, repository, number):
        identity = await self.identity(repository)
        data, _ = await self._request(repository, "GET", f"{self._repo(identity)}/issues/{number}", write=False)
        return self._issue(data)

    async def issue_comments(self, repository, number, limit=50):
        bounded_limit = self._limit(limit)
        data = await self._repo_request(
            repository,
            "GET",
            f"/issues/{number}/comments?per_page={bounded_limit}",
            None,
            False,
            None,
        )
        return {"comments": [self._comment(item) for item in data[:bounded_limit]]}

    async def issue_create(self, repository, payload):
        return await self._repo_request(repository, "POST", "/issues", payload, True, self._issue)

    async def issue_update(self, repository, number, payload):
        return await self._repo_request(repository, "PATCH", f"/issues/{number}", payload, True, self._issue)

    async def issue_comment(self, repository, number, body):
        return await self._repo_request(repository, "POST", f"/issues/{number}/comments", {"body": body}, True, self._comment)

    async def pull_list(self, repository, filters):
        identity = await self.identity(repository)
        query = urlencode({key: value for key, value in filters.items() if value is not None})
        data, _ = await self._request(repository, "GET", f"{self._repo(identity)}/pulls?{query}", write=False)
        limit = int(filters.get("per_page", 50))
        return {"pull_requests": [self._pull(item) for item in data[:limit]]}

    async def pull_get(self, repository, number):
        return await self._repo_request(repository, "GET", f"/pulls/{number}", None, False, self._pull)

    async def pull_create(self, repository, payload):
        if ":" in payload["head"]:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "fork-style PR heads are not supported")
        return await self._repo_request(repository, "POST", "/pulls", payload, True, self._pull)

    async def pull_update(self, repository, number, payload):
        draft = payload.pop("draft", None)
        current = await self.pull_get(repository, number) if draft is not None else None
        data = await self._repo_request(repository, "PATCH", f"/pulls/{number}", payload, True, self._pull) if payload else current
        if draft is not None and bool(current["draft"]) != draft:
            mutation = "convertPullRequestToDraft" if draft else "markPullRequestReadyForReview"
            graphql, _ = await self._request(repository, "POST", "/graphql", {
                "query": f"mutation($id:ID!){{{mutation}(input:{{pullRequestId:$id}}){{pullRequest{{id}}}}}}",
                "variables": {"id": current["node_id"]},
            }, write=True)
            if graphql.get("errors"):
                raise BridgeError(
                    ErrorCode.GITHUB_CONFLICT,
                    "GitHub did not apply the requested pull request draft state",
                )
            data = await self.pull_get(repository, number)
            if bool(data["draft"]) != draft:
                raise BridgeError(
                    ErrorCode.GITHUB_CONFLICT,
                    "GitHub did not apply the requested pull request draft state",
                )
        return data

    async def pull_comment(self, repository, number, body):
        return await self.issue_comment(repository, number, body)

    async def pull_reviews(self, repository, number, limit=50):
        data = await self._repo_request(repository, "GET", f"/pulls/{number}/reviews?per_page={self._limit(limit)}", None, False, None)
        return {"reviews": [self._review(item) for item in data[:limit]]}

    async def pull_review_comments(self, repository, number, limit=50):
        bounded_limit = self._limit(limit)
        data = await self._repo_request(
            repository,
            "GET",
            f"/pulls/{number}/comments?per_page={bounded_limit}",
            None,
            False,
            None,
        )
        return {
            "comments": [self._review_comment(item) for item in data[:bounded_limit]]
        }

    async def pull_files(self, repository, number, limit=50):
        bounded_limit = self._limit(limit)
        data = await self._repo_request(
            repository,
            "GET",
            f"/pulls/{number}/files?per_page={bounded_limit}",
            None,
            False,
            None,
        )
        return {"files": [self._pull_file(item) for item in data[:bounded_limit]]}

    async def pull_review(self, repository, number, payload):
        return await self._repo_request(repository, "POST", f"/pulls/{number}/reviews", payload, True, self._review)

    async def request_reviewers(self, repository, number, payload):
        return await self._repo_request(repository, "POST", f"/pulls/{number}/requested_reviewers", payload, True, self._pull)

    async def pull_merge(self, repository, number, expected_head, method):
        current = await self.pull_get(repository, number)
        if current["head_sha"] != expected_head:
            raise BridgeError(ErrorCode.GITHUB_CONFLICT, "Pull request head changed")
        return await self._repo_request(repository, "PUT", f"/pulls/{number}/merge", {"sha": expected_head, "merge_method": method}, True, None)

    async def actions_runs(self, repository, filters):
        identity = await self.identity(repository)
        workflow = filters.pop("workflow", None)
        prefix = f"/actions/workflows/{quote(str(workflow), safe='')}/runs" if workflow else "/actions/runs"
        query = urlencode({key: value for key, value in filters.items() if value is not None})
        data, _ = await self._request(repository, "GET", f"{self._repo(identity)}{prefix}?{query}", write=False)
        return {"runs": [self._run(item) for item in data.get("workflow_runs", [])[:filters.get("per_page", 50)]]}

    async def actions_run(self, repository, run_id):
        return await self._repo_request(repository, "GET", f"/actions/runs/{run_id}", None, False, self._run)

    async def actions_jobs(self, repository, run_id, limit=50):
        data = await self._repo_request(repository, "GET", f"/actions/runs/{run_id}/jobs?per_page={self._limit(limit)}", None, False, None)
        return {"jobs": [self._job(item) for item in data.get("jobs", [])[:limit]]}

    async def actions_job_logs(self, repository, job_id, limit_bytes=262144):
        identity = await self.identity(repository)
        self._require(repository, Capability.GIT_READ)
        if self.transport is None:
            raise BridgeError(ErrorCode.GITHUB_NOT_CONFIGURED, "GitHub token is not configured")
        bounded, truncated = await self.transport.download_bytes(
            f"{self._repo(identity)}/actions/jobs/{job_id}/logs", limit_bytes
        )
        return {"text": bounded.decode(errors="replace"), "truncated": truncated, "size_bytes": len(bounded), "limit_bytes": limit_bytes}

    async def actions_artifacts(self, repository, run_id, limit=50):
        data = await self._repo_request(repository, "GET", f"/actions/runs/{run_id}/artifacts?per_page={self._limit(limit)}", None, False, None)
        return {"artifacts": [self._artifact(item) for item in data.get("artifacts", [])[:limit]]}

    async def actions_dispatch(self, repository, workflow, ref, inputs):
        workflow_segment = quote(str(workflow), safe="")
        await self._repo_request(repository, "POST", f"/actions/workflows/{workflow_segment}/dispatches", {"ref": ref, "inputs": inputs}, True, None)
        return {"status": "dispatched", "workflow": workflow, "ref": ref}

    async def actions_rerun(self, repository, run_id, failed_only):
        suffix = "/rerun-failed-jobs" if failed_only else "/rerun"
        await self._repo_request(repository, "POST", f"/actions/runs/{run_id}{suffix}", {}, True, None)
        return {"status": "requested", "run_id": run_id, "failed_only": failed_only}

    async def actions_cancel(self, repository, run_id):
        await self._repo_request(repository, "POST", f"/actions/runs/{run_id}/cancel", {}, True, None)
        return {"status": "cancel_requested", "run_id": run_id}

    async def _repo_request(self, repository, method, suffix, payload, write, normalize):
        identity = await self.identity(repository)
        data, _ = await self._request(repository, method, self._repo(identity) + suffix, payload, write=write)
        return normalize(data) if normalize else data

    async def _request(self, repository, method, path, payload=None, *, write):
        response = await self._raw(repository, method, path, payload, write=write)
        if not 200 <= response.status < 300:
            raise _http_error(response.status, response.headers)
        if not response.body:
            return {}, response.headers
        return response.json(), response.headers

    async def _raw(self, repository, method, path, payload=None, *, write):
        self._require(repository, Capability.GIT_WRITE if write else Capability.GIT_READ)
        if self.transport is None:
            raise BridgeError(ErrorCode.GITHUB_NOT_CONFIGURED, "GitHub token is not configured")
        return await self.transport.request(method, path, payload=payload)

    def _require(self, repository, capability):
        self.policy.require(repository.capabilities, capability, project_id=repository.project_id, repository_id=repository.id)

    @staticmethod
    def _repo(identity): return f"/repos/{identity.owner}/{identity.repository}"
    @staticmethod
    def _limit(value): return max(1, min(int(value), 100))
    @staticmethod
    def _user(value): return None if not value else value.get("login")
    @classmethod
    def _issue(cls, x):
        return {"number": x.get("number"), "title": x.get("title"), "body": x.get("body"), "state": x.get("state"), "state_reason": x.get("state_reason"), "labels": [i.get("name") for i in x.get("labels", [])], "assignees": [cls._user(i) for i in x.get("assignees", [])], "milestone": None if not x.get("milestone") else x["milestone"].get("number"), "author": cls._user(x.get("user")), "created_at": x.get("created_at"), "updated_at": x.get("updated_at"), "closed_at": x.get("closed_at"), "comments": x.get("comments"), "url": x.get("html_url")}
    @classmethod
    def _pull(cls, x):
        result = cls._issue(x); result.update({"draft": x.get("draft"), "merged": x.get("merged", False), "mergeable": x.get("mergeable"), "mergeable_state": x.get("mergeable_state"), "head_branch": x.get("head", {}).get("ref"), "head_sha": x.get("head", {}).get("sha"), "base_branch": x.get("base", {}).get("ref"), "base_sha": x.get("base", {}).get("sha"), "additions": x.get("additions"), "deletions": x.get("deletions"), "changed_files": x.get("changed_files"), "review_comments": x.get("review_comments"), "node_id": x.get("node_id")}); return result
    @classmethod
    def _comment(cls, x): return {"id": x.get("id"), "body": x.get("body"), "author": cls._user(x.get("user")), "created_at": x.get("created_at"), "updated_at": x.get("updated_at"), "url": x.get("html_url")}
    @classmethod
    def _review(cls, x): return {"id": x.get("id"), "author": cls._user(x.get("user")), "state": x.get("state"), "body": x.get("body"), "commit_sha": x.get("commit_id"), "submitted_at": x.get("submitted_at"), "url": x.get("html_url")}
    @classmethod
    def _review_comment(cls, x):
        return {"id": x.get("id"), "body": x.get("body"), "author": cls._user(x.get("user")), "commit_sha": x.get("commit_id"), "original_commit_sha": x.get("original_commit_id"), "path": x.get("path"), "line": x.get("line"), "original_line": x.get("original_line"), "start_line": x.get("start_line"), "side": x.get("side"), "start_side": x.get("start_side"), "in_reply_to_id": x.get("in_reply_to_id"), "created_at": x.get("created_at"), "updated_at": x.get("updated_at"), "url": x.get("html_url")}
    @staticmethod
    def _pull_file(x):
        patch = x.get("patch")
        patch_truncated = False
        if patch is not None:
            encoded = str(patch).encode("utf-8")
            patch_truncated = len(encoded) > PULL_REQUEST_PATCH_LIMIT_BYTES
            if patch_truncated:
                patch = encoded[:PULL_REQUEST_PATCH_LIMIT_BYTES].decode(
                    "utf-8", errors="ignore"
                )
        return {"filename": x.get("filename"), "status": x.get("status"), "previous_filename": x.get("previous_filename"), "additions": x.get("additions"), "deletions": x.get("deletions"), "changes": x.get("changes"), "patch": patch, "patch_truncated": patch_truncated}
    @staticmethod
    def _check_run(x): return {key: x.get(key) for key in ("id", "name", "status", "conclusion", "started_at", "completed_at", "html_url")}
    @staticmethod
    def _status(x): return {key: x.get(key) for key in ("context", "state", "description", "target_url", "created_at", "updated_at")}
    @staticmethod
    def _run(x): return {key: x.get(key) for key in ("id", "name", "event", "status", "conclusion", "head_branch", "head_sha", "run_attempt", "created_at", "updated_at", "html_url", "workflow_id")}
    @staticmethod
    def _job(x): return {key: x.get(key) for key in ("id", "name", "status", "conclusion", "started_at", "completed_at", "runner_name", "runner_group_name")} | {"steps": [{key: step.get(key) for key in ("number", "name", "status", "conclusion")} for step in x.get("steps", [])[:100]]}
    @staticmethod
    def _artifact(x): return {key: x.get(key) for key in ("id", "name", "size_in_bytes", "expired", "created_at", "expires_at")}
    @staticmethod
    def _rate(headers): return {"limit": headers.get("x-ratelimit-limit"), "remaining": headers.get("x-ratelimit-remaining"), "reset": headers.get("x-ratelimit-reset")}


def resolve_github_origin(origin: str) -> GitHubRepositoryIdentity:
    match = re.fullmatch(r"git@github\.com:([^/]+)/(.+)", origin)
    if match:
        owner, repository = match.groups()
    else:
        parsed = urlparse(origin)
        if (
            parsed.scheme not in {"https", "ssh"}
            or parsed.hostname != "github.com"
            or parsed.query
            or parsed.fragment
            or parsed.scheme == "https" and (parsed.username or parsed.password)
            or parsed.scheme == "ssh" and parsed.username not in {None, "git"}
        ):
            raise BridgeError(ErrorCode.GITHUB_REPOSITORY_UNAVAILABLE, "Repository origin is not a supported GitHub URL")
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 2:
            raise BridgeError(ErrorCode.GITHUB_REPOSITORY_UNAVAILABLE, "Repository origin is not a supported GitHub URL")
        owner, repository = parts
    repository = repository.removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repository):
        raise BridgeError(ErrorCode.GITHUB_REPOSITORY_UNAVAILABLE, "Repository origin is not a supported GitHub URL")
    return GitHubRepositoryIdentity(owner, repository)
