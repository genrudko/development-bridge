from __future__ import annotations

import os
import subprocess
from pathlib import Path


def create_git_repository(root: Path, name: str, branch: str = "main") -> Path:
    """Create a deterministic local Git repository for tests."""
    repository = root / name
    repository.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch", branch],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Development Bridge Tests"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "bridge-tests@example.invalid"],
        cwd=repository,
        check=True,
    )
    (repository / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repository, check=True)
    commit_env = os.environ.copy()
    commit_env.update({
        "GIT_AUTHOR_DATE": "2020-01-01T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2020-01-01T00:00:00+00:00",
    })
    subprocess.run(
        ["git", "commit", "-m", "Initial fixture"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        env=commit_env,
    )
    return repository

