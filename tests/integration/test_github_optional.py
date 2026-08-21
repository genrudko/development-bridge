import builtins
import importlib

from app.integrations.github import github_status_text


def test_core_integration_imports_without_github_sdk(monkeypatch):
    original_import = builtins.__import__

    def without_github(name, *args, **kwargs):
        if name == "github" or name.startswith("github."):
            raise ImportError("GitHub SDK intentionally unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_github)
    module = importlib.import_module("app.integrations.github")
    assert module.github_status_text("configured-token") == "GitHub integration unavailable"


def test_github_integration_does_not_require_network_without_token():
    assert github_status_text("") == "GitHub token missing"

