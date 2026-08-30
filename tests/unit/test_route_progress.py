import pytest

from app.api.errors import BridgeError
from app.coordinator.progress import RouteProgressStore


def test_route_progress_is_durable_and_route_scoped(tmp_path):
    path = tmp_path / "route-progress.json"
    store = RouteProgressStore(path)
    first = store.update("ad5x", {
        "title": "Bridge optimization",
        "total": 10,
        "completed": 3,
        "status": "working",
        "current": "Implement progress state",
    })
    assert first["percent"] == 30
    assert RouteProgressStore(path).get("ad5x")["current"] == "Implement progress state"
    assert store.get("eod") is None

    completed = store.update("ad5x", {"status": "completed"})
    assert completed["completed"] == 10
    assert completed["percent"] == 100

    assert store.clear("ad5x")["cleared"] is True
    assert store.get("ad5x") is None


def test_route_progress_rejects_invalid_initial_or_bounds(tmp_path):
    store = RouteProgressStore(tmp_path / "route-progress.json")
    with pytest.raises(BridgeError):
        store.update("ad5x", {"status": "working"})
    with pytest.raises(BridgeError):
        store.update("ad5x", {"title": "x", "total": 2, "completed": 3})
