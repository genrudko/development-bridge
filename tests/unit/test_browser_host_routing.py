from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def _module():
    path = Path(__file__).parents[2] / "ops/chatgpt_browser_host/browser_host.py"
    spec = importlib.util.spec_from_file_location("browser_host_test_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    sys.modules.setdefault("requests", types.SimpleNamespace(RequestException=Exception))
    sys.modules.setdefault("websocket", types.SimpleNamespace())
    spec.loader.exec_module(module)
    return module


def _config(module, tmp_path: Path):
    return module.Config(
        chrome="/bin/true", chrome_lib="", xvfb="/bin/true", xvfb_lib="",
        profile=str(tmp_path / "profile"), display=":99", debug_port=9222,
        target_url="https://chatgpt.com/g/g-p-ad5x/c/conv-a", route_id="ad5x",
        channel_id="telegram-supervisor", public_ip="", bridge_unit="bridge.service",
        coordinator_local_url="http://127.0.0.1:8789/mcp/x/coordinator/",
        check_interval=5, startup_timeout=45, poll_window=15, poll_grace=45,
        listener_recovery_timeout=120, state_dir=tmp_path / "state",
        route_registry=tmp_path / "routes.json", chat_registry=tmp_path / "chat-registry.json",
        discovery_interval=60,
    )


def test_browser_host_bootstraps_route_registry(tmp_path: Path):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    assert host.refresh_route_target() is False
    data = __import__("json").loads((tmp_path / "routes.json").read_text())
    assert data["requested_route"] == "ad5x"
    assert data["routes"]["ad5x"]["channel_id"] == "telegram-supervisor"


def test_browser_host_follows_requested_route_generation(tmp_path: Path):
    module = _module()
    cfg = _config(module, tmp_path)
    (tmp_path / "routes.json").write_text(
        '{"version":1,"default_route":"ad5x","requested_route":"bridge-dev","routes":'
        '{"ad5x":{"url":"https://chatgpt.com/g/g-p-ad5x/c/conv-a","channel_id":"telegram-supervisor","generation":0},'
        '"bridge-dev":{"url":"https://chatgpt.com/g/g-p-bridge/c/conv-b","channel_id":"telegram-bridge-dev-g3","generation":3}}}',
        encoding="utf-8",
    )
    host = module.BrowserHost(cfg)
    assert host.refresh_route_target() is True
    assert host.route_id == "bridge-dev"
    assert host.target_url.endswith("/c/conv-b")
    assert host.channel_id == "telegram-bridge-dev-g3"
    assert host.route_generation == 3


def test_browser_host_reload_route_target_refreshes_same_conversation(tmp_path: Path, monkeypatch):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    page = {"id": "page-1", "url": host.target_url}
    calls = []
    host.pages = lambda: [page]
    host.navigate = lambda selected, url: calls.append((selected["id"], url))
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    host.reload_route_target()
    assert calls == [("page-1", host.target_url)]


def test_browser_host_accepts_versioned_coordinator_iframes(tmp_path: Path, monkeypatch):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    seen = {}
    class FakeWS:
        def send(self, payload):
            seen["request"] = __import__("json").loads(payload)
        def recv(self):
            rid = seen["request"]["id"]
            return __import__("json").dumps({"id": rid, "result": {"result": {"value": 1}}})
        def close(self):
            pass
    monkeypatch.setattr(module.websocket, "create_connection", lambda *a, **k: FakeWS(), raising=False)
    assert host.coordinator_iframe_count({"webSocketDebuggerUrl": "ws://test"}) == 1
    expression = seen["request"]["params"]["expression"]
    assert "coordinator-x-v" in expression
    assert "startsWith" in expression
    assert "coordinator-x-v1.html'" not in expression


def test_browser_host_treats_iframe_probe_timeout_as_transient(tmp_path: Path, monkeypatch):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))

    class TimeoutWS:
        def send(self, payload):
            pass
        def recv(self):
            raise TimeoutError("Connection timed out")
        def close(self):
            pass

    monkeypatch.setattr(module.websocket, "create_connection", lambda *a, **k: TimeoutWS(), raising=False)
    count, error = host.safe_coordinator_iframe_count({"webSocketDebuggerUrl": "ws://test"})
    assert count is None
    assert error == "Connection timed out"


def test_browser_host_rate_limit_backoff_is_bounded_and_persisted(tmp_path: Path, monkeypatch):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    clock = [1000.0]
    monkeypatch.setattr(module.time, "time", lambda: clock[0])
    assert host.activate_web_backoff() == 120.0
    data = __import__("json").loads(host.cfg.web_backoff_file.read_text())
    assert data["until"] == 1120.0
    assert data["attempt"] == 1
    clock[0] = 1050.0
    assert host.activate_web_backoff() == 70.0
    assert host.rate_limit_count == 1
    clock[0] = 1121.0
    assert host.activate_web_backoff() == 240.0
    assert host.rate_limit_count == 2


def test_browser_host_model_turn_observer_baselines_before_ack(tmp_path: Path):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    host.safe_bridge_turn_state = lambda page: ({"turn_id": 26, "turn_key": "turn-26", "generating": False}, None)
    called = []
    host.coordinator_local_status = lambda: called.append(True) or {}
    assert host.sync_model_turn_observation({}) is None
    assert host.last_bridge_turn_id == 26
    assert host.bridge_turn_baselined is True
    assert called == []


def test_browser_host_observes_new_completed_bridge_turn(tmp_path: Path):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    host.last_bridge_turn_id = 25
    host.last_bridge_turn_key = "turn-25"
    host.bridge_turn_baselined = True
    host.safe_bridge_turn_state = lambda page: ({"turn_id": 26, "turn_key": "turn-26", "generating": False}, None)
    host.coordinator_local_status = lambda: {
        "state": "waiting_model_ack",
        "transport_delivered": True,
        "continuation_id": "cont_abcdefghij",
    }
    calls = []
    host.observe_model_turn_local = lambda continuation_id: calls.append(continuation_id) or {"observed": True}
    observed = host.sync_model_turn_observation({})
    assert observed == {"observed": True}
    assert calls == ["cont_abcdefghij"]
    assert host.last_bridge_turn_id == 26
    assert host.model_turn_observation_count == 1


def test_browser_host_does_not_observe_while_generating(tmp_path: Path):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    host.last_bridge_turn_id = 25
    host.last_bridge_turn_key = "turn-25"
    host.bridge_turn_baselined = True
    host.safe_bridge_turn_state = lambda page: ({"turn_id": 26, "turn_key": "turn-26", "generating": True}, None)
    called = []
    host.coordinator_local_status = lambda: called.append(True) or {}
    assert host.sync_model_turn_observation({}) is None
    assert called == []
    assert host.last_bridge_turn_id == 25


def test_browser_host_zero_baseline_does_not_swallow_first_real_wake(tmp_path: Path):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    host.safe_bridge_turn_state = lambda page: ({"turn_id": 0, "turn_key": None, "generating": False}, None)
    assert host.sync_model_turn_observation({}) is None
    assert host.bridge_turn_baselined is True
    host.safe_bridge_turn_state = lambda page: ({"turn_id": 1, "turn_key": "turn-1", "generating": False}, None)
    host.coordinator_local_status = lambda: {
        "transport_delivered": True, "continuation_id": "cont_abcdefghij"
    }
    host.observe_model_turn_local = lambda continuation_id: {"observed": True}
    assert host.sync_model_turn_observation({}) == {"observed": True}
    assert host.last_bridge_turn_id == 1


def test_browser_host_observer_uses_turn_key_not_numeric_order(tmp_path: Path):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    host.last_bridge_turn_id = 28
    host.last_bridge_turn_key = "stable-old-uuid"
    host.bridge_turn_baselined = True
    host.safe_bridge_turn_state = lambda page: (
        {"turn_id": 12, "turn_key": "stable-new-uuid", "generating": False}, None
    )
    host.coordinator_local_status = lambda: {
        "transport_delivered": True, "continuation_id": "cont_abcdefghij"
    }
    host.observe_model_turn_local = lambda continuation_id: {"observed": True}
    assert host.sync_model_turn_observation({}) == {"observed": True}
    assert host.last_bridge_turn_id == 12
    assert host.last_bridge_turn_key == "stable-new-uuid"
