from __future__ import annotations

from pathlib import Path


def write_bridge_config(path: Path, repositories: dict[str, Path]) -> Path:
    """Write a minimal Bridge configuration without external services."""
    entries = "\n".join(
        (
            f"      - id: {repository_id}\n"
            f"        path: {repository_path}\n"
            "        capabilities:\n"
            "          read: true\n"
            "          git_read: true"
        )
        for repository_id, repository_path in repositories.items()
    )
    path.write_text(
        "version: 1\n"
        "server:\n"
        "  name: development-bridge\n"
        "projects:\n"
        "  - id: test-project\n"
        "    name: Test Project\n"
        "    repositories:\n"
        f"{entries}\n",
        encoding="utf-8",
    )
    return path

