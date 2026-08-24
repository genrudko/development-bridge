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
