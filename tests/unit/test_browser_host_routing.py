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



def test_browser_host_rollover_commits_only_after_successor_verification(tmp_path: Path):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    host.route_generation = 5
    host.channel_id = "telegram-ad5x-g5"
    source_url = host.target_url
    candidate_url = "https://chatgpt.com/g/g-p-ad5x/c/conv-b"
    rollover = {
        "token": "roll_test_token",
        "state": "prepared",
        "source_generation": 5,
        "target_generation": 6,
        "source_url": source_url,
        "source_conversation_id": "conv-a",
        "project_id": "g-p-ad5x",
        "channel_id": "telegram-ad5x-g6",
        "created_at": "2026-08-26T10:00:00+00:00",
    }
    source_page = {"id": "source", "url": source_url}
    candidate_page = {"id": "candidate", "url": candidate_url}
    host.pending_rollover = lambda: dict(rollover)
    host.pages = lambda: [source_page]
    host.safe_bridge_turn_state = lambda page: ({"generating": False}, None)
    host.coordinator_app_control = lambda page, action, **payload: {
        "ok": True, "channel_id": "telegram-ad5x-g5"
    }
    host.branch_in_new_chat = lambda page, url: (candidate_page, candidate_url)
    host.wait_for_control_channel = lambda page, channel_id, timeout=30: {
        "ok": True, "channel_id": channel_id
    }
    host.wait_for_polling = lambda channel_id, timeout=35: (True, "matches=3")
    host.wait_for_rollover_preflight = lambda page, token, timeout=75: {
        "ready": True, "iframe_count": 1
    }
    calls = []
    def control(action, current, **payload):
        calls.append((action, payload))
        if action == "candidate":
            return {
                **current,
                "state": "candidate",
                "candidate_url": payload["url"],
                "candidate_conversation_id": "conv-b",
            }
        if action == "commit":
            return {
                "route_id": "ad5x", "generation": 6,
                "channel_id": "telegram-ad5x-g6", "conversation_id": "conv-b",
                "url": candidate_url,
            }
        raise AssertionError(action)
    host.rollover_control = control
    result = host.process_pending_rollover()
    assert result["state"] == "committed"
    assert [item[0] for item in calls] == ["candidate", "commit"]
    assert host.rollover_count == 1


def test_browser_host_rollover_aborts_before_commit_on_successor_failure(tmp_path: Path):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    module.TRANSIENT_CDP_ERRORS = (OSError, TimeoutError)
    host.route_generation = 5
    rollover = {
        "token": "roll_test_token",
        "state": "candidate",
        "source_generation": 5,
        "target_generation": 6,
        "source_url": host.target_url,
        "candidate_url": "https://chatgpt.com/g/g-p-ad5x/c/conv-b",
        "channel_id": "telegram-ad5x-g6",
    }
    candidate_page = {"id": "candidate", "url": rollover["candidate_url"]}
    host.pending_rollover = lambda: dict(rollover)
    host.pages = lambda: [candidate_page]
    host.wait_for_control_channel = lambda page, channel_id, timeout=30: {
        "ok": False, "error": "template_missing"
    }
    restored = []
    host.restore_source_after_rollover = lambda url: restored.append(url)
    calls = []
    host.rollover_control = lambda action, current, **payload: calls.append((action, payload)) or {
        "aborted": True
    }
    result = host.process_pending_rollover()
    assert result["state"] == "aborted"
    assert [item[0] for item in calls] == ["abort"]
    assert restored == [host.target_url]
    assert host.rollover_abort_count == 1


def test_browser_host_completes_durable_rollover_bootstrap(tmp_path: Path):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    host.route_generation = 6
    host.channel_id = "telegram-ad5x-g6"
    record = {
        "token": "roll_durable_token",
        "state": "committed",
        "bootstrap_sent": False,
        "target_generation": 6,
        "candidate_url": host.target_url,
    }
    host.active_rollover_record = lambda: dict(record)
    host.wait_for_control_channel = lambda page, channel_id, timeout=15: {
        "ok": True, "channel_id": channel_id
    }
    sent = []
    def app_control(page, action, **payload):
        sent.append((action, payload))
        return {"ok": True, "channel_id": payload.get("channel_id")}
    host.coordinator_app_control = app_control
    completed = []
    host.rollover_control = lambda action, current, **payload: completed.append(action) or {
        **current, "state": "complete", "bootstrap_sent": True
    }
    result = host.complete_rollover_bootstrap({"id": "candidate"})
    assert result["state"] == "complete"
    assert sent[0][0] == "bootstrap"
    assert sent[0][1]["operation_id"] == "roll_durable_token"
    assert "coordinator_route_context_get" in sent[0][1]["message"]
    assert completed == ["complete"]


def test_browser_host_branch_uses_supported_turn_action(tmp_path: Path, monkeypatch):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    expressions = []
    def evaluate(page, expression, **kwargs):
        expressions.append(expression)
        return {"ok": True}
    host.runtime_evaluate = evaluate
    candidate = {
        "id": "candidate",
        "url": "https://chatgpt.com/g/g-p-ad5x/c/conv-b",
    }
    host.pages = lambda: [candidate]
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    page, url = host.branch_in_new_chat({"id": "source"}, host.target_url)
    assert page == candidate
    assert url.endswith("/c/conv-b")
    assert "More actions" in expressions[0]
    assert "Branch in new chat" in expressions[0]
    assert "Branch in new chat" in expressions[1]



def test_browser_host_preflight_requires_native_iframe_in_ready_turn(tmp_path: Path, monkeypatch):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    expressions = []
    host.runtime_evaluate = lambda page, expression, **kwargs: expressions.append(expression) or {
        "ready": True, "generating": False, "iframe_count": 1
    }
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    result = host.wait_for_rollover_preflight({}, "roll_test", timeout=1)
    assert result["ready"] is True
    assert "ROLLOVER_READY roll_test" in expressions[0]
    assert "coordinator-x-v" in expressions[0]
    assert "data-message-author-role" in expressions[0]



def test_browser_host_controls_inner_mcp_app_execution_context(tmp_path: Path, monkeypatch):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    host.coordinator_app_targets = lambda: [{"webSocketDebuggerUrl": "ws://inner"}]
    sent = []
    queue = []
    class FakeWS:
        def send(self, raw):
            request = __import__("json").loads(raw)
            sent.append(request)
            rid = request["id"]
            method = request["method"]
            if method == "Runtime.enable":
                queue.extend([
                    {"method": "Runtime.executionContextCreated", "params": {"context": {"id": 3}}},
                    {"method": "Runtime.executionContextCreated", "params": {"context": {"id": 1}}},
                    {"id": rid, "result": {}},
                ])
            elif "__developmentBridgeControlV1==='function'" in request["params"]["expression"]:
                capable = request["params"]["contextId"] == 3
                queue.append({"id": rid, "result": {"result": {"value": capable}}})
            elif "window.__developmentBridgeControlV1(" in request["params"]["expression"]:
                queue.append({"id": rid, "result": {"result": {"value": {
                    "ok": True, "channel_id": "telegram-ad5x-g5"
                }}}})
            else:
                raise AssertionError(request)
        def recv(self):
            return __import__("json").dumps(queue.pop(0))
        def close(self):
            pass
    monkeypatch.setattr(module.websocket, "create_connection", lambda *a, **k: FakeWS(), raising=False)
    result = host.coordinator_app_control({}, "ping")
    assert result == {"ok": True, "channel_id": "telegram-ad5x-g5"}
    call = next(item for item in sent if "window.__developmentBridgeControlV1(" in item.get("params", {}).get("expression", ""))
    assert call["params"]["contextId"] == 3
    assert call["params"]["awaitPromise"] is True


def test_browser_host_rollover_retries_transient_cdp_failure(tmp_path: Path):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    host.route_generation = 5
    rollover = {
        "token": "roll_transient",
        "state": "candidate",
        "source_generation": 5,
        "target_generation": 6,
        "source_url": host.target_url,
        "candidate_url": "https://chatgpt.com/g/g-p-ad5x/c/conv-b",
        "channel_id": "telegram-ad5x-g6",
        "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    host.pending_rollover = lambda: dict(rollover)
    host.pages = lambda: [{"id": "candidate", "url": rollover["candidate_url"]}]
    host.wait_for_control_channel = lambda *a, **k: (_ for _ in ()).throw(TimeoutError("Connection timed out"))
    aborted = []
    host.abort_pending_rollover = lambda current, reason: aborted.append(reason) or {"aborted": True}
    result = host.process_pending_rollover()
    assert result["state"] == "waiting_transient"
    assert "timed out" in result["error"]
    assert aborted == []
