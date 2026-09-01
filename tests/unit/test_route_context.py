from __future__ import annotations

from pathlib import Path

import pytest

from app.api.errors import BridgeError
from app.coordinator.context import RouteContextStore


def test_route_context_update_get_and_bootstrap(tmp_path: Path):
    store = RouteContextStore(tmp_path / "route-contexts.json")
    assert store.get("ad5x") is None
    content = "Role: coordinator\nNext: continue routing"
    first = store.update("ad5x", content)
    assert first["revision"] == 1
    assert store.get("ad5x")["content"] == content

    bootstrap = store.bootstrap({"route_id": "ad5x", "generation": 3})
    assert bootstrap["context"]["revision"] == 1
    assert bootstrap["context"]["content"] == content
    assert bootstrap["bootstrap_message"] == (
        "Canonical Route Context loaded for route ad5x. "
        "Current state is available in context.content, revision 1."
    )
    assert content not in bootstrap["bootstrap_message"]
    assert len(bootstrap["bootstrap_message"]) < 180


def test_route_context_expected_revision_prevents_lost_update(tmp_path: Path):
    store = RouteContextStore(tmp_path / "route-contexts.json")
    store.update("ad5x", "one")
    with pytest.raises(BridgeError):
        store.update("ad5x", "two", expected_revision=0)
    second = store.update("ad5x", "two", expected_revision=1)
    assert second["revision"] == 2
    assert store.get("ad5x")["content"] == "two"


def test_route_context_empty_bootstrap_is_explicit(tmp_path: Path):
    store = RouteContextStore(tmp_path / "route-contexts.json")
    bootstrap = store.bootstrap({"route_id": "bridge-dev", "generation": 0})
    assert bootstrap["context"] is None
    assert bootstrap["bootstrap_message"] == (
        "No canonical Route Context is stored for route bridge-dev."
    )
