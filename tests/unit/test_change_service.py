from __future__ import annotations

import hashlib
import os
import subprocess

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import CapabilityPolicy, CapabilitySet
from app.changes import ChangeRevisionCalculator, ChangeService
from app.git import GitRunner
from app.projects import Repository
from tests.fixtures.repositories import create_git_repository


def configured_repository(root, *, writable=True):
    return Repository(
        project_id="engineering",
        id="service",
        root=root,
        capabilities=CapabilitySet.from_mapping({"write": writable}),
    )


def digest(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def service():
    runner = GitRunner()
    return ChangeService(CapabilityPolicy(), ChangeRevisionCalculator(runner))


@pytest.mark.asyncio
async def test_plan_is_normalized_and_self_contained(tmp_path):
    root = create_git_repository(tmp_path, "service")
    change_service = service()

    plan = await change_service.plan(
        configured_repository(root),
        [{"type": "create", "path": "new.txt", "content": "new\n"}],
    )
    payload = plan.as_dict()

    assert payload["project_id"] == "engineering"
    assert payload["repository_id"] == "service"
    assert payload["plan_id"].startswith("sha256:")
    assert payload["base_revision"].startswith("sha256:")
    assert payload["operations"] == [
        {"type": "create", "path": "new.txt", "content": "new\n"}
    ]
    assert payload["summary"]["create"] == 1


@pytest.mark.asyncio
async def test_apply_supports_all_operations_without_writing_git_state(tmp_path):
    root = create_git_repository(tmp_path, "service")
    (root / "delete.txt").write_text("delete\n", encoding="utf-8")
    (root / "rename.txt").write_text("rename\n", encoding="utf-8")
    subprocess.run(["git", "add", "delete.txt", "rename.txt"], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Add fixtures"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    change_service = service()
    repository = configured_repository(root)
    operations = [
        {"type": "create", "path": "created.txt", "content": "created\n"},
        {
            "type": "update",
            "path": "README.md",
            "expected_sha256": digest("# service\n"),
            "content": "updated\n",
        },
        {
            "type": "delete",
            "path": "delete.txt",
            "expected_sha256": digest("delete\n"),
        },
        {
            "type": "rename",
            "source": "rename.txt",
            "destination": "renamed.txt",
            "expected_sha256": digest("rename\n"),
        },
    ]
    plan = await change_service.plan(repository, operations)

    result = await change_service.apply(
        repository,
        plan_id=plan.plan_id,
        base_revision=plan.base_revision,
        operations=[operation.as_dict() for operation in plan.operations],
    )

    assert result.status == "applied"
    assert result.operations_applied == 4
    assert (root / "created.txt").read_text(encoding="utf-8") == "created\n"
    assert (root / "README.md").read_text(encoding="utf-8") == "updated\n"
    assert not (root / "delete.txt").exists()
    assert not (root / "rename.txt").exists()
    assert (root / "renamed.txt").read_text(encoding="utf-8") == "rename\n"
    assert subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip() == head
    assert subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root).returncode == 0


@pytest.mark.asyncio
async def test_apply_is_idempotent_across_service_instances(tmp_path):
    root = create_git_repository(tmp_path, "service")
    repository = configured_repository(root)
    first_service = service()
    plan = await first_service.plan(
        repository,
        [{"type": "create", "path": "once.txt", "content": "once\n"}],
    )
    arguments = {
        "plan_id": plan.plan_id,
        "base_revision": plan.base_revision,
        "operations": [operation.as_dict() for operation in plan.operations],
    }

    first = await first_service.apply(repository, **arguments)
    second = await service().apply(repository, **arguments)

    assert first.status == "applied"
    assert second.status == "already_applied"
    assert second.operations_applied == 0
    receipts = list((root / ".git" / "development-bridge" / "receipts").iterdir())
    assert len(receipts) == 1


@pytest.mark.asyncio
async def test_plan_checks_optional_revision_when_supplied(tmp_path):
    root = create_git_repository(tmp_path, "service")

    with pytest.raises(BridgeError) as raised:
        await service().plan(
            configured_repository(root),
            [{"type": "create", "path": "new.txt", "content": "new\n"}],
            base_revision="sha256:" + "0" * 64,
        )

    assert raised.value.code is ErrorCode.REVISION_CONFLICT


@pytest.mark.asyncio
async def test_apply_rejects_repository_drift(tmp_path):
    root = create_git_repository(tmp_path, "service")
    repository = configured_repository(root)
    change_service = service()
    plan = await change_service.plan(
        repository,
        [{"type": "create", "path": "new.txt", "content": "new\n"}],
    )
    (root / "drift.txt").write_text("drift\n", encoding="utf-8")

    with pytest.raises(BridgeError) as raised:
        await change_service.apply(
            repository,
            plan_id=plan.plan_id,
            base_revision=plan.base_revision,
            operations=[operation.as_dict() for operation in plan.operations],
        )

    assert raised.value.code is ErrorCode.REVISION_CONFLICT
    assert not (root / "new.txt").exists()


@pytest.mark.asyncio
async def test_plan_rejects_wrong_content_hash_and_duplicate_paths(tmp_path):
    root = create_git_repository(tmp_path, "service")
    repository = configured_repository(root)
    change_service = service()

    with pytest.raises(BridgeError) as wrong_hash:
        await change_service.plan(
            repository,
            [
                {
                    "type": "delete",
                    "path": "README.md",
                    "expected_sha256": "sha256:" + "0" * 64,
                }
            ],
        )
    with pytest.raises(BridgeError) as duplicate:
        await change_service.plan(
            repository,
            [
                {"type": "create", "path": "same.txt", "content": "one"},
                {"type": "create", "path": "same.txt", "content": "two"},
            ],
        )

    assert wrong_hash.value.code is ErrorCode.CHANGE_PRECONDITION_FAILED
    assert duplicate.value.code is ErrorCode.CHANGE_PLAN_INVALID


@pytest.mark.asyncio
@pytest.mark.parametrize("operation_type", ["update", "delete", "rename"])
async def test_destructive_operations_reject_untracked_files(
    tmp_path, operation_type
):
    root = create_git_repository(tmp_path, "service")
    (root / "untracked.txt").write_text("untracked\n", encoding="utf-8")
    operation = {
        "type": operation_type,
        "expected_sha256": digest("untracked\n"),
    }
    if operation_type == "rename":
        operation.update(
            {"source": "untracked.txt", "destination": "renamed.txt"}
        )
    else:
        operation["path"] = "untracked.txt"
        if operation_type == "update":
            operation["content"] = "updated\n"

    with pytest.raises(BridgeError) as raised:
        await service().plan(configured_repository(root), [operation])

    assert raised.value.code is ErrorCode.CHANGE_PRECONDITION_FAILED
    assert "tracked" in raised.value.message


@pytest.mark.asyncio
async def test_plan_rejects_unsafe_and_symlink_paths(tmp_path):
    root = create_git_repository(tmp_path, "service")
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, root / "linked")
    repository = configured_repository(root)

    for path in ("../outside.txt", ".git/config", "linked/new.txt"):
        with pytest.raises(BridgeError) as raised:
            await service().plan(
                repository,
                [{"type": "create", "path": path, "content": "new\n"}],
            )
        assert raised.value.code is ErrorCode.CHANGE_PLAN_INVALID


@pytest.mark.asyncio
async def test_write_capability_is_required(tmp_path):
    root = create_git_repository(tmp_path, "service")

    with pytest.raises(BridgeError) as raised:
        await service().plan(
            configured_repository(root, writable=False),
            [{"type": "create", "path": "new.txt", "content": "new\n"}],
        )

    assert raised.value.code is ErrorCode.PERMISSION_DENIED
