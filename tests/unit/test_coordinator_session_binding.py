from app.coordinator.service import CoordinatorService


def test_session_binding_is_ephemeral_and_rebindable():
    service = CoordinatorService()
    assert service.session_binding("session-a") is None
    first = service.bind_session("session-a", "route-g1", route_id="route", generation=1)
    assert first["generation"] == 1
    second = service.bind_session("session-a", "route-g2", route_id="route", generation=2)
    assert second["channel_id"] == "route-g2"
    assert service.session_binding("session-a")["generation"] == 2


def test_stale_generation_binding_remains_stale(tmp_path):
    from app.coordinator.service import CoordinatorService

    service = CoordinatorService(tmp_path / "wakes.json")
    service.bind_session(
        "session-old", "telegram-ad5x-g5", route_id="ad5x", generation=5, route_state="active"
    )
    binding = service.session_binding("session-old")
    assert binding["route_id"] == "ad5x"
    assert binding["generation"] == 5
    assert binding["channel_id"] == "telegram-ad5x-g5"
