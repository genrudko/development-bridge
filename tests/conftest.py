"""Shared fixtures for Development Bridge tests."""

import pytest


@pytest.fixture(autouse=True)
def isolated_xdg_data_home(tmp_path, monkeypatch):
    """Keep managed runtime state outside the operator's real data directory."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
