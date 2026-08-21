from __future__ import annotations

import os

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import CapabilityPolicy, CapabilitySet
from app.files import FileService
from app.projects import Repository
from tests.fixtures.repositories import create_git_repository


def configured_repository(root, *, readable=True):
    return Repository(
        project_id="engineering",
        id="service",
        root=root,
        capabilities=CapabilitySet.from_mapping({"read": readable}),
    )


def test_list_read_and_search_are_repository_scoped(tmp_path):
    root = create_git_repository(tmp_path, "service")
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("Hello\nhello again\n", encoding="utf-8")
    service = FileService(CapabilityPolicy())
    repository = configured_repository(root)

    entries = service.list(repository, recursive=True)
    assert [entry.path for entry in entries] == ["README.md", "src", "src/main.py"]
    assert service.read(repository, "src/main.py") == "Hello\nhello again\n"
    assert [match.as_dict() for match in service.search(repository, "hello", case_sensitive=False)] == [
        {"path": "src/main.py", "line": 1, "text": "Hello"},
        {"path": "src/main.py", "line": 2, "text": "hello again"},
    ]


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd", ".git/config"])
def test_repository_boundary_rejects_unsafe_paths(tmp_path, path):
    root = create_git_repository(tmp_path, "service")
    service = FileService(CapabilityPolicy())

    with pytest.raises(BridgeError) as raised:
        service.read(configured_repository(root), path)

    assert raised.value.code is ErrorCode.POLICY_VIOLATION


def test_symlinks_are_not_listed_read_or_searched(tmp_path):
    root = create_git_repository(tmp_path, "service")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret needle\n", encoding="utf-8")
    os.symlink(outside, root / "linked.txt")
    service = FileService(CapabilityPolicy())
    repository = configured_repository(root)

    assert "linked.txt" not in [entry.path for entry in service.list(repository)]
    assert service.search(repository, "secret") == ()
    with pytest.raises(BridgeError) as raised:
        service.read(repository, "linked.txt")
    assert raised.value.code is ErrorCode.POLICY_VIOLATION


def test_read_rejects_binary_and_oversized_files(tmp_path):
    root = create_git_repository(tmp_path, "service")
    service = FileService(CapabilityPolicy())
    repository = configured_repository(root)
    (root / "binary.dat").write_bytes(b"text\0binary")
    (root / "large.txt").write_bytes(b"x" * (service.MAX_FILE_BYTES + 1))

    for path in ("binary.dat", "large.txt"):
        with pytest.raises(BridgeError) as raised:
            service.read(repository, path)
        assert raised.value.code is ErrorCode.POLICY_VIOLATION


def test_read_capability_is_required(tmp_path):
    root = create_git_repository(tmp_path, "service")
    service = FileService(CapabilityPolicy())

    with pytest.raises(BridgeError) as raised:
        service.list(configured_repository(root, readable=False))

    assert raised.value.code is ErrorCode.PERMISSION_DENIED


def test_search_obeys_result_and_output_boundaries(tmp_path):
    root = create_git_repository(tmp_path, "service")
    (root / "matches.txt").write_text(
        "needle " + "x" * 2000 + "\nneedle second\n", encoding="utf-8"
    )
    service = FileService(CapabilityPolicy())

    matches = service.search(configured_repository(root), "needle", max_results=1)

    assert len(matches) == 1
    assert len(matches[0].text) == service.MAX_MATCH_TEXT
