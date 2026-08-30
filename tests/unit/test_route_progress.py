from threading import Event, Thread

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


def test_route_progress_start_creates_unique_operation_ids(tmp_path):
    store = RouteProgressStore(tmp_path / "route-progress.json")

    first = store.start("ad5x", {"title": "First", "total": 2})
    second = store.start("ad5x", {"title": "Second", "total": 3})

    assert first["operation_id"]
    assert second["operation_id"]
    assert first["operation_id"] != second["operation_id"]
    assert store.get("ad5x")["operation_id"] == second["operation_id"]


def test_route_progress_start_keeps_prior_operation_when_replacement_is_invalid(tmp_path):
    path = tmp_path / "route-progress.json"
    store = RouteProgressStore(path)
    prior = store.start("ad5x", {"title": "Prior", "total": 2})

    with pytest.raises(BridgeError):
        store.start("ad5x", {"title": "Invalid", "total": 2, "completed": 3})

    persisted = RouteProgressStore(path).get("ad5x")
    assert persisted["operation_id"] == prior["operation_id"]
    assert persisted["title"] == "Prior"
    assert persisted["revision"] == prior["revision"]


def test_route_progress_rejects_update_for_superseded_operation(tmp_path):
    store = RouteProgressStore(tmp_path / "route-progress.json")
    first = store.start("ad5x", {"title": "First", "total": 2})
    second = store.start("ad5x", {"title": "Second", "total": 3})

    with pytest.raises(BridgeError, match="operation_id"):
        store.update("ad5x", {"operation_id": first["operation_id"], "completed": 1})

    assert store.get("ad5x")["operation_id"] == second["operation_id"]


def test_route_progress_serializes_updates_across_store_instances(tmp_path):
    path = tmp_path / "route-progress.json"
    first_store = RouteProgressStore(path)
    second_store = RouteProgressStore(path)
    first = first_store.start("ad5x", {"title": "First", "total": 2})
    first_save_entered = Event()
    release_first_save = Event()
    second_finished = Event()
    original_save = first_store._save

    def pause_first_save(data):
        first_save_entered.set()
        assert release_first_save.wait(timeout=2)
        original_save(data)

    first_store._save = pause_first_save
    update_thread = Thread(
        target=first_store.update,
        args=("ad5x", {"operation_id": first["operation_id"], "completed": 1}),
    )
    start_thread = Thread(
        target=lambda: (second_store.start("ad5x", {"title": "Second", "total": 3}), second_finished.set()),
    )

    update_thread.start()
    assert first_save_entered.wait(timeout=2)
    start_thread.start()
    try:
        assert not second_finished.wait(timeout=0.2), "a second store entered while the path was locked"
    finally:
        release_first_save.set()
        update_thread.join(timeout=2)
        start_thread.join(timeout=2)

    assert not update_thread.is_alive()
    assert not start_thread.is_alive()
    assert RouteProgressStore(path).get("ad5x")["title"] == "Second"
