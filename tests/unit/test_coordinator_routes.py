

def test_route_for_channel_resolves_active_and_pending_generation(tmp_path):
    from app.coordinator.routes import RouteRegistry
    registry = RouteRegistry(tmp_path / "routes.json")
    route = registry.bootstrap(
        "ad5x",
        "https://chatgpt.com/c/00000000-0000-0000-0000-000000000001",
        "telegram-ad5x-g0",
        "AD5X",
    )
    active = registry.route_for_channel(route["channel_id"])
    assert active["route_id"] == "ad5x"
    assert active["route_state"] == "active"

    pending = registry.prepare_rollover("ad5x")
    candidate = registry.route_for_channel(pending["channel_id"])
    assert candidate["route_id"] == "ad5x"
    assert candidate["route_state"] == "pending"
    assert candidate["generation"] == pending["target_generation"]
