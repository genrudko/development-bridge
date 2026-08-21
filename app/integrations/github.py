from __future__ import annotations


def github_status_text(token: str) -> str:
    if not token:
        return "GitHub token missing"

    try:
        from github import Github
    except ImportError:
        return "GitHub integration unavailable"

    client = Github(token)
    user = client.get_user()
    return f"GitHub connected: {user.login}"

