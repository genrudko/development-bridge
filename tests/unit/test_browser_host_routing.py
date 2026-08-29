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
        discovery_interval=60, rollover_branch_enabled=True,
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



def test_browser_host_rollover_is_safety_locked_by_default(tmp_path: Path):
    module = _module()
    import dataclasses
    cfg = dataclasses.replace(_config(module, tmp_path), rollover_branch_enabled=False)
    host = module.BrowserHost(cfg)
    host.route_generation = 5
    rollover = {
        "token": "roll_locked", "state": "prepared", "source_generation": 5,
        "target_generation": 6, "source_url": host.target_url,
        "channel_id": "telegram-ad5x-g6",
        "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    host.pending_rollover = lambda: dict(rollover)
    created = []
    host.create_project_successor = lambda *args: created.append(args)
    result = host.process_pending_rollover()
    assert result["state"] == "safety_locked"
    assert created == []


def test_browser_host_rollover_aborts_ghost_candidate_before_control(tmp_path: Path):
    module = _module()
    module.TRANSIENT_CDP_ERRORS = (OSError, TimeoutError)
    host = module.BrowserHost(_config(module, tmp_path))
    host.route_generation = 5
    rollover = {
        "token": "roll_ghost", "state": "candidate", "source_generation": 5,
        "target_generation": 6, "source_url": host.target_url,
        "candidate_url": "https://chatgpt.com/g/g-p-ad5x/c/ghost-b",
        "channel_id": "telegram-ad5x-g6",
        "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    candidate_page = {"id": "candidate", "url": rollover["candidate_url"]}
    host.pending_rollover = lambda: dict(rollover)
    host.pages = lambda: [candidate_page]
    host.validate_candidate_conversation = lambda page, url, timeout=30: {"ok": False, "current_url": "https://chatgpt.com/g/g-p-ad5x/project", "composer_visible": False}
    control_calls = []
    host.wait_for_control_channel = lambda *a, **k: control_calls.append((a, k))
    host.restore_source_after_rollover = lambda url: None
    actions = []
    host.rollover_control = lambda action, current, **payload: actions.append(action) or {"aborted": True}
    result = host.process_pending_rollover()
    assert result["state"] == "aborted"
    assert "stable URL" in result["error"]
    assert control_calls == []
    assert actions == ["abort"]


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
    host.create_project_successor = lambda url, channel, token: (candidate_page, candidate_url)
    host.validate_candidate_conversation = lambda page, url, timeout=30: {"ok": True, "current_url": url, "composer_visible": True}
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


def test_browser_host_rollover_creates_fresh_successor_without_source_control(tmp_path: Path):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    host.route_generation = 5
    source_url = host.target_url
    candidate_url = "https://chatgpt.com/g/g-p-ad5x/c/conv-fresh-successor"
    rollover = {
        "token": "roll_fresh_token", "state": "prepared", "source_generation": 5,
        "target_generation": 6, "source_url": source_url,
        "source_conversation_id": "conv-a", "project_id": "g-p-ad5x",
        "channel_id": "telegram-ad5x-g6", "created_at": "2026-08-26T10:00:00+00:00",
    }
    source_page = {"id": "source", "url": source_url}
    candidate_page = {"id": "candidate", "url": candidate_url}
    host.pending_rollover = lambda: dict(rollover)
    host.pages = lambda: [source_page]
    source_control_calls = []
    host.coordinator_app_control = lambda page, action, **payload: (
        source_control_calls.append((page.get("id"), action)) or
        {"ok": True, "channel_id": payload.get("channel_id", "telegram-ad5x-g6")}
    )
    created = []
    host.create_project_successor = lambda url, channel, token: (
        created.append((url, channel, token)) or (candidate_page, candidate_url)
    )
    host.validate_candidate_conversation = lambda page, url, timeout=30: {
        "ok": True, "current_url": url, "composer_visible": True
    }
    host.wait_for_control_channel = lambda page, channel_id, timeout=30: {
        "ok": True, "channel_id": channel_id
    }
    host.wait_for_polling = lambda channel_id, timeout=35: (True, "matches=3")
    host.wait_for_rollover_preflight = lambda page, token, timeout=75: {
        "ready": True, "iframe_count": 1
    }
    calls=[]
    def control(action,current,**payload):
        calls.append(action)
        if action=="candidate": return {**current,"state":"candidate","candidate_url":payload["url"],"candidate_conversation_id":"conv-fresh-successor"}
        if action=="commit": return {"route_id":"ad5x","generation":6,"channel_id":"telegram-ad5x-g6","conversation_id":"conv-fresh-successor","url":candidate_url}
        raise AssertionError(action)
    host.rollover_control=control
    result=host.process_pending_rollover()
    assert result["state"]=="committed"
    assert created == [(source_url, "telegram-ad5x-g6", "roll_fresh_token")]
    assert all(page_id != "source" for page_id, _ in source_control_calls)
    assert calls == ["candidate", "commit"]


def test_browser_host_rollover_does_not_probe_stale_source_listener(tmp_path: Path):
    module = _module()
    module.TRANSIENT_CDP_ERRORS = (OSError, TimeoutError)
    host = module.BrowserHost(_config(module, tmp_path))
    host.route_generation = 5
    rollover = {
        "token": "roll_no_source_probe", "state": "prepared", "source_generation": 5,
        "target_generation": 6, "source_url": host.target_url,
        "source_conversation_id": "conv-a", "project_id": "g-p-ad5x",
        "channel_id": "telegram-ad5x-g6",
        "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    host.pending_rollover=lambda:dict(rollover)
    host.pages=lambda:[{"id":"source","url":host.target_url}]
    host.safe_bridge_turn_state=lambda *a,**k: (_ for _ in ()).throw(AssertionError("source turn probe must not run"))
    host.safe_coordinator_iframe_count=lambda *a,**k: (_ for _ in ()).throw(AssertionError("source iframe probe must not run"))
    host.polling_ok=lambda *a,**k: (_ for _ in ()).throw(AssertionError("source polling probe must not run"))
    host.create_project_successor=lambda *a,**k: (_ for _ in ()).throw(RuntimeError("fresh successor stopped for test"))
    host.restore_source_after_rollover=lambda url: None
    host.rollover_control=lambda action,current,**payload:{"aborted":True}
    result=host.process_pending_rollover()
    assert result["state"]=="aborted"
    assert "fresh successor stopped for test" in result["error"]


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
    host.validate_candidate_conversation = lambda page, url, timeout=30: {"ok": True, "current_url": url, "composer_visible": True}
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


def test_browser_host_candidate_validator_requires_stable_hydrated_chat(tmp_path: Path):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    seen = {}
    def evaluate(page, expression, **kwargs):
        seen["expression"] = expression
        return {
            "ok": True,
            "current_url": "https://chatgpt.com/g/g-p-ad5x/c/conv-b",
            "ready_state": "complete",
            "composer_visible": True,
            "error_visible": False,
        }
    host.runtime_evaluate = evaluate
    result = host.validate_candidate_conversation(
        {"id": "candidate"}, "https://chatgpt.com/g/g-p-ad5x/c/conv-b", timeout=1
    )
    assert result["ok"] is True
    assert "#prompt-textarea" in seen["expression"]
    assert "current===target" in seen["expression"]


def test_browser_host_candidate_validator_rejects_project_redirect(tmp_path: Path):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    host.runtime_evaluate = lambda *a, **k: {
        "ok": False,
        "current_url": "https://chatgpt.com/g/g-p-ad5x/project",
        "ready_state": "complete",
        "composer_visible": False,
        "error_visible": False,
    }
    result = host.validate_candidate_conversation(
        {"id": "candidate"}, "https://chatgpt.com/g/g-p-ad5x/c/ghost-b", timeout=1
    )
    assert result["ok"] is False
    assert result["current_url"].endswith("/project")


def test_browser_host_creates_successor_from_project_home(tmp_path: Path, monkeypatch):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    page = {"id": "fresh", "url": "about:blank", "webSocketDebuggerUrl": "ws://fresh"}
    candidate_url = "https://chatgpt.com/g/g-p-ad5x/c/conv-fresh"
    host.create_blank_page = lambda: dict(page)
    navigated = []
    host.navigate = lambda selected, url: navigated.append(url)
    submitted = []
    host.submit_native_prompt = lambda selected, message: submitted.append(message)
    states = iter([
        {"url": "https://chatgpt.com/g/g-p-ad5x/project", "ready": "complete", "composer": True},
        {"url": candidate_url, "generating": True},
    ])
    host.runtime_evaluate = lambda *a, **k: next(states)
    host.validate_candidate_conversation = lambda selected, url, timeout=30: {
        "ok": True, "current_url": url, "composer_visible": True
    }
    host.wait_for_rollover_preflight = lambda selected, token, timeout=75: {
        "ready": True, "iframe_count": 1
    }
    selected, url = host.create_project_successor(
        host.target_url, "telegram-ad5x-g6", "roll_fresh", timeout=5
    )
    assert navigated == ["https://chatgpt.com/g/g-p-ad5x/project"]
    assert "coordinator_x_mount" in submitted[0]
    assert "telegram-ad5x-g6" in submitted[0]
    assert "ROLLOVER_READY roll_fresh" in submitted[0]
    assert url == candidate_url
    assert selected["url"] == candidate_url


def test_browser_host_branch_uses_supported_turn_action(tmp_path: Path, monkeypatch):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    source = {"id": "source", "url": host.target_url}
    popup = {
        "id": "popup",
        "url": "https://chatgpt.com/branch/conv-a/msg-1",
        "webSocketDebuggerUrl": "ws://popup",
    }
    expressions = []
    values = iter([
        {"ok": True},
        {"ok": True, "x": 640.0, "y": 320.0},
    ])
    host.runtime_evaluate = lambda page, expression, **kwargs: expressions.append(expression) or next(values)
    pages = iter([[source], [source, popup]])
    host.pages = lambda: next(pages)
    clicks = []
    host.dispatch_mouse_click = lambda page, x, y: clicks.append((page["id"], x, y))
    host.materialize_branch_popup = lambda page, branch_url, source_url: (
        {"id": "popup", "url": "https://chatgpt.com/g/g-p-ad5x/c/conv-b"},
        "https://chatgpt.com/g/g-p-ad5x/c/conv-b",
    )
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    page, url = host.branch_in_new_chat(source, host.target_url)
    assert page["id"] == "popup"
    assert url.endswith("/c/conv-b")
    assert clicks == [("source", 640.0, 320.0)]
    assert "More actions" in expressions[0]
    assert "scrollIntoView" in expressions[0]
    assert "Branch in new chat" in expressions[1]


def test_browser_host_materializes_branch_response_to_stable_project_url(tmp_path: Path, monkeypatch):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    page = {
        "id": "popup",
        "url": "https://chatgpt.com/branch/conv-a/msg-1",
        "webSocketDebuggerUrl": "ws://popup",
    }
    queue = []
    sent = []

    class FakeWS:
        def send(self, raw):
            request = __import__("json").loads(raw)
            sent.append(request)
            rid = request["id"]
            method = request["method"]
            if method == "Network.enable":
                queue.append({"id": rid, "result": {}})
            elif method == "Page.navigate":
                queue.extend([
                    {"method": "Network.requestWillBeSent", "params": {
                        "requestId": "branch-request",
                        "request": {"url": "https://chatgpt.com/backend-api/conversation/new_branch"},
                    }},
                    {"id": rid, "result": {"frameId": "frame"}},
                    {"method": "Network.responseReceived", "params": {
                        "requestId": "branch-request", "response": {"status": 200},
                    }},
                    {"method": "Network.loadingFinished", "params": {
                        "requestId": "branch-request",
                    }},
                ])
            elif method == "Network.getResponseBody":
                queue.append({"id": rid, "result": {"body": __import__("json").dumps({
                    "conversation": {"conversation_id": "conv-b"}
                })}})
            else:
                raise AssertionError(request)

        def recv(self):
            return __import__("json").dumps(queue.pop(0))

        def close(self):
            pass

    monkeypatch.setattr(module.websocket, "create_connection", lambda *a, **k: FakeWS(), raising=False)
    navigated = []
    host.navigate = lambda selected, url: navigated.append((selected["id"], url))
    candidate, url = host.materialize_branch_popup(
        page,
        "https://chatgpt.com/branch/conv-a/msg-1",
        host.target_url,
        timeout=1,
    )
    assert url == "https://chatgpt.com/g/g-p-ad5x/c/conv-b"
    assert candidate["url"] == url
    assert navigated == [("popup", url)]
    assert any(item["method"] == "Network.getResponseBody" for item in sent)



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



def test_browser_host_scopes_coordinator_oopifs_to_top_level_page(tmp_path: Path, monkeypatch):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))

    class FakeResponse:
        def raise_for_status(self):
            pass
        def json(self):
            return [
                {"id": "a", "type": "iframe", "parentId": "source", "url": "https://one.web-sandbox.oaiusercontent.com/", "webSocketDebuggerUrl": "ws://a"},
                {"id": "b", "type": "iframe", "parentId": "candidate", "url": "https://two.web-sandbox.oaiusercontent.com/", "webSocketDebuggerUrl": "ws://b"},
                {"id": "c", "type": "iframe", "parentId": "candidate", "url": "https://example.com/", "webSocketDebuggerUrl": "ws://c"},
            ]

    monkeypatch.setattr(module.requests, "get", lambda *a, **k: FakeResponse(), raising=False)
    assert [item["id"] for item in host.coordinator_app_targets({"id": "candidate"})] == ["b"]
    assert [item["id"] for item in host.coordinator_app_targets({"id": "source"})] == ["a"]


def test_browser_host_controls_inner_mcp_app_execution_context(tmp_path: Path, monkeypatch):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    host.coordinator_app_targets = lambda page=None: [{"webSocketDebuggerUrl": "ws://inner"}]
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
    host.validate_candidate_conversation = lambda page, url, timeout=30: {"ok": True, "current_url": url, "composer_visible": True}
    host.wait_for_control_channel = lambda *a, **k: (_ for _ in ()).throw(TimeoutError("Connection timed out"))
    aborted = []
    host.abort_pending_rollover = lambda current, reason: aborted.append(reason) or {"aborted": True}
    result = host.process_pending_rollover()
    assert result["state"] == "waiting_transient"
    assert "timed out" in result["error"]
    assert aborted == []


def test_browser_host_supervisor_keeps_chrome_alive_during_listener_recovery():
    source = (Path(__file__).parents[2] / "ops/chatgpt_browser_host/browser_host.py").read_text()
    assert "listener history recovery exhausted; reloading current chat in-process" in source
    assert "MCP X polling not observed for route={self.route_id}; reloading current chat" in source
    assert "raise RuntimeError(\n                            \"coordinator MCP App iframe could not be recovered" not in source
    assert "raise RuntimeError(\n                        f\"MCP X polling not observed for route=" not in source


def _final_snapshot(message_id: str = "message-current") -> dict:
    return {
        "ok": True,
        "current_node": "message-internal",
        "current_role": "tool",
        "current_status": "finished_successfully",
        "current_end_turn": None,
        "current_recipient": "all",
        "current_channel": "commentary",
        "latest_user_id": "message-user",
        "latest_final_id": message_id,
        "latest_turn_complete": True,
    }


def test_browser_host_preflight_uses_fresh_current_chat_before_authorizing(tmp_path: Path):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    page = {"id": "page-stale", "url": host.target_url}
    fresh = {"id": "page-fresh", "url": "about:blank"}
    calls = []
    host.create_blank_page = lambda: fresh
    host.refresh_conversation_snapshot = lambda selected, timeout=30: (
        calls.append(("snapshot", selected["id"])) or _final_snapshot()
    )
    host.wait_for_settled_conversation = lambda selected, timeout=30, expected_message_id=None: {
        "settled": True, "current": expected_message_id == "message-current",
        "last_key": "leaf-ready", "last_message_id": "message-current", "assistant_chars": 42
    }
    host.safe_coordinator_iframe_count = lambda selected: (0, None)
    host.recover_listener = lambda selected: calls.append(("recover", selected["id"])) or True
    host.close_page = lambda page_id: calls.append(("close", page_id))
    host.wait_for_polling = lambda channel_id, timeout=20: (True, "matches=4")
    host.authorize_browser_preflight_local = lambda continuation_id: calls.append(
        ("authorize", continuation_id)
    ) or {"authorized": True, "continuation_id": continuation_id}
    result = host.prepare_browser_preflight(page, "cont_abcdefghij")
    assert result["authorized"] is True
    assert result["leaf"]["last_key"] == "leaf-ready"
    assert result["fresh_page_id"] == "page-fresh"
    assert calls == [
        ("snapshot", "page-fresh"),
        ("recover", "page-fresh"),
        ("close", "page-stale"),
        ("authorize", "cont_abcdefghij"),
    ]


def test_browser_host_preflight_refuses_unsettled_leaf_and_closes_fresh_page(tmp_path: Path):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    page = {"id": "page-stale", "url": host.target_url}
    fresh = {"id": "page-fresh", "url": "about:blank"}
    host.create_blank_page = lambda: fresh
    host.refresh_conversation_snapshot = lambda selected, timeout=30: _final_snapshot()
    host.wait_for_settled_conversation = lambda selected, timeout=30, expected_message_id=None: {
        "settled": False, "current": False, "has_user": True, "has_assistant": False
    }
    closed = []
    host.close_page = lambda page_id: closed.append(page_id)
    authorized = []
    host.authorize_browser_preflight_local = lambda continuation_id: authorized.append(continuation_id)
    result = host.prepare_browser_preflight(page, "cont_abcdefghij")
    assert result["authorized"] is False
    assert result["error"] == "conversation_leaf_not_settled"
    assert closed == ["page-fresh"]
    assert authorized == []


def test_browser_host_prioritizes_browser_preflight_before_generic_iframe_recovery():
    source = (Path(__file__).parents[2] / "ops/chatgpt_browser_host/browser_host.py").read_text()
    run_source = source[source.index("    def run(self) -> int:"):]
    early = run_source.index("early_status = self.coordinator_local_status()")
    iframe_probe = run_source.index("iframe_count, iframe_error = self.safe_coordinator_iframe_count(page)")
    assert early < iframe_probe
    assert "prepare_browser_preflight(page, early_continuation_id)" in run_source[early:iframe_probe]


def test_browser_host_preflight_refuses_stale_dom_leaf(tmp_path: Path):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    page = {"id": "page-stale", "url": host.target_url}
    fresh = {"id": "page-fresh", "url": "about:blank"}
    host.create_blank_page = lambda: fresh
    authorized = []
    host.refresh_conversation_snapshot = lambda selected, timeout=30: _final_snapshot("message-server-current")
    host.wait_for_settled_conversation = lambda selected, timeout=30, expected_message_id=None: {
        "settled": True, "current": False, "last_message_id": "message-stale",
    }
    closed = []
    host.close_page = lambda page_id: closed.append(page_id)
    host.authorize_browser_preflight_local = lambda continuation_id: authorized.append(continuation_id)
    result = host.prepare_browser_preflight(page, "cont_abcdefghij")
    assert result["authorized"] is False
    assert result["error"] == "conversation_leaf_not_current"
    assert result["snapshot"]["latest_final_id"] == "message-server-current"
    assert closed == ["page-fresh"]
    assert authorized == []


def test_browser_host_preflight_refuses_nonfinal_server_leaf(tmp_path: Path):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    page = {"id": "page-stale", "url": host.target_url}
    fresh = {"id": "page-fresh", "url": "about:blank"}
    host.create_blank_page = lambda: fresh
    host.refresh_conversation_snapshot = lambda selected, timeout=30: {
        "ok": True, "current_node": "message-tool-call",
        "current_role": "assistant", "current_status": "finished_successfully",
        "current_end_turn": False, "current_recipient": "api_tool.call_tool",
        "current_channel": None, "latest_user_id": "message-user",
        "latest_final_id": None, "latest_turn_complete": False,
    }
    closed = []
    host.close_page = lambda page_id: closed.append(page_id)
    result = host.prepare_browser_preflight(page, "cont_abcdefghij")
    assert result["authorized"] is False
    assert result["error"] == "conversation_latest_turn_not_final"
    assert closed == ["page-fresh"]


def test_browser_host_parses_current_server_message_from_compact_conversation():
    module = _module()
    result = module.BrowserHost.parse_conversation_snapshot({
        "current_node": "message-b",
        "messages": [
            {"id": "message-a", "author": {"role": "user"}, "status": "finished_successfully"},
            {"id": "message-tool", "author": {"role": "tool"}, "status": "finished_successfully"},
            {
                "id": "message-b", "author": {"role": "assistant"},
                "status": "finished_successfully", "end_turn": True,
                "recipient": "all", "channel": "final",
            },
        ],
    })
    assert result == {
        "ok": True,
        "current_node": "message-b",
        "current_role": "assistant",
        "current_status": "finished_successfully",
        "current_end_turn": True,
        "current_recipient": "all",
        "current_channel": "final",
        "latest_user_id": "message-a",
        "latest_final_id": "message-b",
        "latest_turn_complete": True,
        "message_count": 3,
    }


def test_browser_host_rejects_snapshot_without_current_message():
    module = _module()
    result = module.BrowserHost.parse_conversation_snapshot({
        "current_node": "missing",
        "messages": [{"id": "other", "author": {"role": "assistant"}}],
    })
    assert result["ok"] is False
    assert result["error"] == "conversation_current_node_missing"


def test_browser_host_listener_recovery_yields_to_pending_preflight(tmp_path: Path, monkeypatch):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    host.coordinator_local_status = lambda: {"state": "browser_preflight"}
    sent = []
    class FakeWS:
        def send(self, payload):
            sent.append(payload)
        def close(self):
            pass
    monkeypatch.setattr(module.websocket, "create_connection", lambda *a, **k: FakeWS(), raising=False)
    result = host.recover_listener({"webSocketDebuggerUrl": "ws://fake"})
    assert result is False
    assert sent == []


def test_browser_host_snapshot_completion_uses_final_after_latest_user_not_current_node():
    module = _module()
    result = module.BrowserHost.parse_conversation_snapshot({
        "current_node": "message-tool",
        "messages": [
            {"id": "message-user", "author": {"role": "user"}, "status": "finished_successfully"},
            {"id": "message-final", "author": {"role": "assistant"}, "status": "finished_successfully", "end_turn": True, "recipient": "all", "channel": "final"},
            {"id": "message-tool", "author": {"role": "tool"}, "status": "finished_successfully", "recipient": "all", "channel": "commentary"},
        ],
    })
    assert result["current_role"] == "tool"
    assert result["latest_user_id"] == "message-user"
    assert result["latest_final_id"] == "message-final"
    assert result["latest_turn_complete"] is True


def test_browser_host_chrome_launch_bounds_disk_cache(tmp_path: Path, monkeypatch):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    seen = {}
    class Proc:
        def poll(self): return None
    def fake_popen(argv, **kwargs):
        seen["argv"] = argv
        return Proc()
    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    host.start_chrome()
    assert "--disk-cache-size=268435456" in seen["argv"]
    assert "--media-cache-size=67108864" in seen["argv"]


def test_browser_host_pages_filters_closing_json_list_ghosts(tmp_path: Path, monkeypatch):
    module = _module()
    host = module.BrowserHost(_config(module, tmp_path))
    class Response:
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): pass
        def json(self): return self.payload
    rows = [
        {"id": "live", "type": "page", "url": host.target_url, "webSocketDebuggerUrl": "ws://live"},
        {"id": "ghost", "type": "page", "url": host.target_url, "webSocketDebuggerUrl": "ws://ghost"},
    ]
    monkeypatch.setattr(module.requests, "get", lambda *a, **k: Response(rows), raising=False)
    host.live_page_ids = lambda: {"live"}
    assert [item["id"] for item in host.pages()] == ["live"]


def test_browser_host_clears_only_tab_restore_state(tmp_path: Path):
    module = _module()
    cfg = _config(module, tmp_path)
    host = module.BrowserHost(cfg)
    default = Path(cfg.profile) / "Default"
    (default / "Sessions").mkdir(parents=True)
    (default / "Sessions" / "Tabs_1").write_text("tabs")
    (default / "Sessions_Encrypted").mkdir(parents=True)
    (default / "Sessions_Encrypted" / "Session_1").write_text("session")
    (default / "Current Tabs").write_text("legacy")
    (default / "Cookies").write_text("auth-must-stay")

    host.clear_session_restore_state()

    assert not (default / "Sessions").exists()
    assert not (default / "Sessions_Encrypted").exists()
    assert not (default / "Current Tabs").exists()
    assert (default / "Cookies").read_text() == "auth-must-stay"


def test_browser_host_terminate_has_bounded_waits(tmp_path: Path, monkeypatch):
    module = _module()
    waits = []
    kills = []
    class Proc:
        pid = 12345
        def poll(self): return None
        def wait(self, timeout):
            waits.append(timeout)
            if timeout == 4: raise TimeoutError("still alive")
            return 0
    monkeypatch.setattr(module.os, "killpg", lambda pid, sig: kills.append((pid, sig)))
    module.terminate(Proc())
    assert waits == [4, 1]
    assert kills == [(12345, module.signal.SIGTERM), (12345, module.signal.SIGKILL)]


def test_browser_host_parks_listener_recovery_while_coordinator_idle():
    module = _module()
    source = __import__("inspect").getsource(module.BrowserHost.run)
    idle = source.index('early_status.get("state") == "idle"')
    iframe_probe = source.index("iframe_count, iframe_error = self.safe_coordinator_iframe_count(page)")
    assert idle < iframe_probe
    assert "listener recovery parked" in source[idle:iframe_probe]


def test_browser_host_healthcheck_accepts_fresh_idle_park(tmp_path: Path, monkeypatch, capsys):
    module = _module()
    cfg = _config(module, tmp_path)
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.state_file.write_text(__import__("json").dumps({
        "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "status": "idle",
        "cdp_ok": True,
        "target_ok": True,
        "coordinator_iframes": 0,
        "polling_ok": False,
    }))
    assert module.healthcheck(cfg) == 0
    payload = __import__("json").loads(capsys.readouterr().out)
    assert payload["healthy"] is True
