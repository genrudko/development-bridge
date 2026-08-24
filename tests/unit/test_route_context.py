from __future__ import annotations

from pathlib import Path

import pytest

from app.api.errors import BridgeError
from app.coordinator.context import RouteContextStore


def test_route_context_update_get_and_bootstrap(tmp_path: Path):
    store = RouteContextStore(tmp_path / "route-contexts.json")
    assert store.get("ad5x") is None
    first = store.update("ad5x", "Role: coordinator\nNext: continue routing")
    assert first["revision"] == 1
    assert store.get("ad5x")["content"].startswith("Role:")
    bootstrap = store.bootstrap({"route_id": "ad5x", "generation": 3})
    assert bootstrap["context"]["revision"] == 1
    assert "canonical Route Context" in bootstrap["bootstrap_message"]
    assert "continue routing" in bootstrap["bootstrap_message"]


def test_route_context_expected_revision_prevents_lost_update(tmp_path: Path):
    store = RouteContextStore(tmp_path / "route-contexts.json")
    store.update("ad5x", "one")
    with pytest.raises(BridgeError):
        store.update("ad5x", "two", expected_revision=0)
    second = store.update("ad5x", "two", expected_revision=1)
    assert second["revision"] == 2


def test_route_context_empty_bootstrap_is_explicit(tmp_path: Path):
    store = RouteContextStore(tmp_path / "route-contexts.json")
    bootstrap = store.bootstrap({"route_id": "bridge-dev", "generation": 0})
    assert bootstrap["context"] is None
    assert "no canonical Route Context" in bootstrap["bootstrap_message"]
